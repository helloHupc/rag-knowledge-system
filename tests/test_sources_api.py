from __future__ import annotations

from app.core.config import reset_settings_cache
from app.models.document import Document


def test_folder_source_is_disabled_by_default(client, tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    response = client.post(
        "/api/v1/sources/folder/sync",
        json={
            "folder_path": str(source_dir),
            "source_type": "folder",
            "source_module": "hr",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == 40301


def test_folder_source_rejects_paths_outside_allowed_roots(client, tmp_path, monkeypatch):
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    monkeypatch.setenv("ENABLE_FOLDER_SOURCE", "true")
    monkeypatch.setenv("FOLDER_SOURCE_ALLOWED_ROOTS", str(allowed_root))
    reset_settings_cache()

    response = client.post(
        "/api/v1/sources/folder/sync",
        json={
            "folder_path": str(outside_root),
            "source_type": "folder",
            "source_module": "hr",
        },
    )

    assert response.status_code == 403
    assert response.json()["message"] == "folder path is outside allowed roots"


def test_folder_source_syncs_supported_files_and_skips_unsupported(client, db_session, tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)
    (source_dir / "policy.md").write_text("# 调休规则\n自助调休需要提交申请。", encoding="utf-8")
    (nested_dir / "faq.txt").write_text("调休余额可以在OA系统查看。", encoding="utf-8")
    (source_dir / "ignore.exe").write_bytes(b"ignored")
    monkeypatch.setenv("ENABLE_FOLDER_SOURCE", "true")
    monkeypatch.setenv("FOLDER_SOURCE_ALLOWED_ROOTS", str(tmp_path))
    reset_settings_cache()

    response = client.post(
        "/api/v1/sources/folder/sync",
        json={
            "folder_path": str(source_dir),
            "recursive": True,
            "source_type": "folder",
            "source_module": "hr",
            "version": "folder-v1",
            "access_level": "internal",
            "owner_dept": "hr",
            "tags": ["folder", "sync"],
            "extra_meta": {"chunking_strategy": "structural"},
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source_name"] == "folder"
    assert payload["run_uuid"]
    assert payload["total"] == 2
    assert payload["success_count"] == 2
    assert payload["failed_count"] == 0
    assert payload["skipped_count"] == 1
    assert payload["skipped"][0]["file_name"] == "ignore.exe"
    assert {item["relative_path"] for item in payload["items"]} == {"policy.md", "nested/faq.txt"}

    documents = db_session.query(Document).order_by(Document.file_name.asc()).all()
    assert len(documents) == 2
    assert {document.extra_meta["source_connector"] for document in documents} == {"folder"}
    assert all(document.owner_dept == "hr" for document in documents)

    history = client.get("/api/v1/sources/sync-runs?page=1&page_size=10&source_type=folder")
    assert history.status_code == 200
    history_payload = history.json()["data"]
    assert history_payload["total"] == 1
    assert history_payload["items"][0]["run_uuid"] == payload["run_uuid"]
    assert history_payload["items"][0]["status"] == "success"
    assert history_payload["items"][0]["success_count"] == 2
    assert history_payload["items"][0]["skipped_count"] == 1

    detail = client.get(f"/api/v1/sources/sync-runs/{payload['run_uuid']}")
    assert detail.status_code == 200
    detail_payload = detail.json()["data"]
    assert detail_payload["run_uuid"] == payload["run_uuid"]
    assert detail_payload["folder_path"] == str(source_dir.resolve())
    assert {item["status"] for item in detail_payload["items"]} == {"success", "skipped"}
    assert {item["relative_path"] for item in detail_payload["items"]} == {
        "policy.md",
        "nested/faq.txt",
        "ignore.exe",
    }


def test_folder_source_duplicate_file_is_reported_per_item(client, tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "policy.txt").write_text("同一文件重复同步会被判重。", encoding="utf-8")
    monkeypatch.setenv("ENABLE_FOLDER_SOURCE", "true")
    monkeypatch.setenv("FOLDER_SOURCE_ALLOWED_ROOTS", str(tmp_path))
    reset_settings_cache()
    request_payload = {
        "folder_path": str(source_dir),
        "source_type": "folder",
        "source_module": "hr",
        "version": "duplicate-v1",
    }

    first = client.post("/api/v1/sources/folder/sync", json=request_payload)
    assert first.status_code == 200
    assert first.json()["data"]["success_count"] == 1

    second = client.post("/api/v1/sources/folder/sync", json=request_payload)
    assert second.status_code == 200
    payload = second.json()["data"]
    assert payload["success_count"] == 0
    assert payload["failed_count"] == 1
    assert payload["items"][0]["success"] is False
    assert payload["items"][0]["message"] == "document already exists"

    history = client.get("/api/v1/sources/sync-runs?page=1&page_size=10&status=failed")
    assert history.status_code == 200
    history_payload = history.json()["data"]
    assert history_payload["total"] == 1
    assert history_payload["items"][0]["run_uuid"] == payload["run_uuid"]
