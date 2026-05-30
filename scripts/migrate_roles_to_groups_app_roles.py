"""将旧 roles 表数据迁移拆分到 groups 和 app_roles。

用法:
    # 预览模式（不写入数据）
    .venv/bin/python scripts/migrate_roles_to_groups_app_roles.py --dry-run

    # 执行迁移
    .venv/bin/python scripts/migrate_roles_to_groups_app_roles.py

    # 自定义角色映射
    .venv/bin/python scripts/migrate_roles_to_groups_app_roles.py \\
        --group-roles hr_policy_readers,tech_policy_readers,security_team \\
        --app-roles platform_admin,data_admin

默认行为：
  - 所有旧 role_code 均被映射到 groups（group_type=security_group），不做 app_role 拆分。
  - 显式指定 --app-roles 后，匹配的 role_code 映射到 app_roles；其余映射到 groups。
  - 迁移是幂等的：已存在于目标表的记录会跳过。
  - 旧 user_roles 中关系会迁移到 user_memberships (group) 或 user_app_roles。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.runtime import get_engine, get_session_factory, reset_db_runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="迁移旧 roles 表到 groups 和 app_roles")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式：只打印将要迁移的内容，不写入数据库",
    )
    parser.add_argument(
        "--group-roles",
        type=str,
        default="",
        help="逗号分隔的 role_code 列表，映射到 groups（默认：所有未指定为 app_role 的）",
    )
    parser.add_argument(
        "--app-roles",
        type=str,
        default="",
        help="逗号分隔的 role_code 列表，映射到 app_roles",
    )
    return parser.parse_args()


def get_role_list(value: str) -> list[str]:
    return [role.strip() for role in value.split(",") if role.strip()]


def migrate(session: Session, dry_run: bool, group_role_codes: list[str], app_role_codes: list[str]) -> dict:
    """执行迁移，返回统计信息。"""
    stats: dict[str, int] = {
        "roles_total": 0,
        "roles_to_groups": 0,
        "roles_to_app_roles": 0,
        "groups_created": 0,
        "app_roles_created": 0,
        "memberships_created": 0,
        "user_app_roles_created": 0,
    }

    # 查询所有旧 role
    rows = session.execute(text("SELECT role_code, role_name, permissions FROM roles")).mappings().all()
    existing_role_codes = {row["role_code"] for row in rows}
    stats["roles_total"] = len(existing_role_codes)

    if not existing_role_codes:
        print("没有需要迁移的旧 role 记录。")
        return stats

    # 决定哪些去 groups、哪些去 app_roles
    app_role_set = set(app_role_codes) if app_role_codes else set()
    group_role_set = set(group_role_codes) if group_role_codes else existing_role_codes - app_role_set

    # 如果指定了 --app-roles，未指定的全部去 groups
    if app_role_codes:
        group_role_set = existing_role_codes - app_role_set

    print(f"\n{'[DRY RUN] ' if dry_run else ''}角色分配:")
    print(f"  → groups:     {sorted(group_role_set)}")
    print(f"  → app_roles:  {sorted(app_role_set)}")

    # 查询已有 groups 和 app_roles
    existing_groups = {
        row["group_code"]
        for row in session.execute(text("SELECT group_code FROM groups")).mappings().all()
    }
    existing_app_roles = {
        row["role_code"]
        for row in session.execute(text("SELECT role_code FROM app_roles")).mappings().all()
    }

    # 迁移到 groups
    for row in rows:
        role_code = row["role_code"]
        if role_code not in group_role_set:
            continue
        stats["roles_to_groups"] += 1
        if role_code in existing_groups:
            print(f"  [skip] group {role_code} 已存在")
            continue
        print(f"  [create] group: {role_code} ({row['role_name']})")
        if not dry_run:
            session.execute(
                text(
                    "INSERT INTO groups (group_code, group_name, group_type, status) "
                    "VALUES (:code, :name, :type, :status)"
                ),
                {
                    "code": role_code,
                    "name": row["role_name"] or role_code,
                    "type": "security_group",
                    "status": "active",
                },
            )
            stats["groups_created"] += 1

    # 迁移到 app_roles
    for row in rows:
        role_code = row["role_code"]
        if role_code not in app_role_set:
            continue
        stats["roles_to_app_roles"] += 1
        if role_code in existing_app_roles:
            print(f"  [skip] app_role {role_code} 已存在")
            continue
        permissions = row["permissions"]
        if isinstance(permissions, str):
            import json
            try:
                permissions = json.loads(permissions)
            except (json.JSONDecodeError, TypeError):
                pass
        print(f"  [create] app_role: {role_code} ({row['role_name']})")
        if not dry_run:
            session.execute(
                text(
                    "INSERT INTO app_roles (role_code, role_name, permissions, status) "
                    "VALUES (:code, :name, :perms, :status)"
                ),
                {
                    "code": role_code,
                    "name": row["role_name"] or role_code,
                    "perms": permissions or None,
                    "status": "active",
                },
            )
            stats["app_roles_created"] += 1

    if dry_run:
        if not dry_run:
            session.commit()
        return stats

    session.flush()

    # 迁移 user_roles 关系到 user_memberships (group) 或 user_app_roles
    user_roles_rows = (
        session.execute(
            text("SELECT ur.user_id, ur.role_code, u.status FROM user_roles ur JOIN users u ON ur.user_id = u.user_id")
        )
        .mappings()
        .all()
    )

    existing_memberships = {
        (row["user_id"], row["principal_type"], row["principal_id"])
        for row in session.execute(
            text("SELECT user_id, principal_type, principal_id FROM user_memberships")
        ).mappings().all()
    }
    existing_user_app_roles = {
        (row["user_id"], row["role_code"])
        for row in session.execute(
            text("SELECT user_id, role_code FROM user_app_roles")
        ).mappings().all()
    }

    for ur in user_roles_rows:
        role_code = ur["role_code"]
        user_id = ur["user_id"]
        user_status = ur["status"]

        if user_status != "active":
            continue

        if role_code in group_role_set:
            key = (user_id, "group", role_code)
            if key in existing_memberships:
                continue
            print(f"  [create] membership: {user_id} → group:{role_code}")
            if not dry_run:
                session.execute(
                    text(
                        "INSERT INTO user_memberships (user_id, principal_type, principal_id) "
                        "VALUES (:uid, :ptype, :pid)"
                    ),
                    {"uid": user_id, "ptype": "group", "pid": role_code},
                )
                stats["memberships_created"] += 1

        elif role_code in app_role_set:
            key = (user_id, role_code)
            if key in existing_user_app_roles:
                continue
            print(f"  [create] user_app_role: {user_id} → {role_code}")
            if not dry_run:
                session.execute(
                    text(
                        "INSERT INTO user_app_roles (user_id, role_code) "
                        "VALUES (:uid, :code)"
                    ),
                    {"uid": user_id, "code": role_code},
                )
                stats["user_app_roles_created"] += 1

    if not dry_run:
        session.commit()

    return stats


def main() -> None:
    args = parse_args()
    group_role_codes = get_role_list(args.group_roles)
    app_role_codes = get_role_list(args.app_roles)

    reset_db_runtime()
    engine = get_engine()
    session = Session(get_session_factory()())

    try:
        stats = migrate(session, args.dry_run, group_role_codes, app_role_codes)
        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}统计:")
        print(f"  旧 role 总数:        {stats['roles_total']}")
        print(f"  迁入 groups:         {stats['roles_to_groups']}")
        print(f"  迁入 app_roles:      {stats['roles_to_app_roles']}")
        print(f"  新建 groups:         {stats['groups_created']}")
        print(f"  新建 app_roles:      {stats['app_roles_created']}")
        print(f"  新建 memberships:    {stats['memberships_created']}")
        print(f"  新建 user_app_roles: {stats['user_app_roles_created']}")
        if args.dry_run:
            print("\n提示: 这是预览模式，未写入数据。去掉 --dry-run 参数后执行实际迁移。")
    finally:
        session.close()


if __name__ == "__main__":
    main()
