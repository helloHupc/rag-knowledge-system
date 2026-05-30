"""Manual acceptance test script for OA RAG 企业知识库平台."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    test_db_path = Path("/tmp/oa_rag_acceptance_test.sqlite3")
    test_storage_root = Path("/tmp/oa_rag_acceptance_test_data")

    if test_db_path.exists():
        test_db_path.unlink()
    if test_storage_root.exists():
        import shutil

        shutil.rmtree(test_storage_root)

    os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"
    os.environ["STORAGE_ROOT"] = str(test_storage_root)
    os.environ["RAW_DATA_DIR"] = str(test_storage_root / "raw")
    os.environ["PROCESSED_DATA_DIR"] = str(test_storage_root / "processed")
    os.environ["APP_API_KEY"] = "test-api-key"
    os.environ["INTERNAL_TOKEN"] = "test-internal-token"
    # Keep manual acceptance deterministic and isolated from real provider credentials in .env.
    os.environ["VECTOR_STORE_PROVIDER"] = "local"
    os.environ["EMBEDDING_PROVIDER"] = "local"
    os.environ["EMBEDDING_API_BASE"] = ""
    os.environ["EMBEDDING_API_KEY"] = ""
    os.environ["EMBEDDING_MODEL"] = ""
    os.environ["LLM_API_BASE"] = ""
    os.environ["LLM_API_KEY"] = ""
    os.environ["LLM_MODEL"] = ""
    os.environ["ZILLIZ_URI"] = ""
    os.environ["ZILLIZ_TOKEN"] = ""

    from app.core.config import get_settings, reset_settings_cache
    from app.db.base import Base
    from app.db.runtime import get_engine, reset_db_runtime
    from app.main import create_app

    reset_settings_cache()
    reset_db_runtime()
    settings = get_settings()
    settings.ensure_storage_dirs()
    Base.metadata.create_all(bind=get_engine())

    app = create_app()
    client = TestClient(app)
    results = []

    def record_test(name, passed, details=""):
        status = "PASS" if passed else "FAIL"
        results.append({"name": name, "status": status, "details": details})
        symbol = "✅" if passed else "❌"
        print(f"  {symbol} {name}: {status}")
        if details and not passed:
            print(f"     Details: {details}")

    def sync_acceptance_identity() -> bool:
        source_resp = client.post(
            "/api/v1/admin/identity-sources",
            json={
                "source_id": "acceptance-directory",
                "source_type": "custom_api",
                "name": "Acceptance Directory",
                "field_mapping_json": {
                    "user_id": "employee_no",
                    "external_id": "directory_id",
                    "display_name": "full_name",
                    "email": "mail",
                    "department_codes": "dept_codes",
                    "status": "state",
                },
            },
        )
        if source_resp.status_code not in {200, 409}:
            record_test("Identity source created", False, f"Status: {source_resp.status_code}")
            return False
        sync_resp = client.post(
            "/api/v1/admin/identity-sources/acceptance-directory/sync",
            json={
                "records": [
                    {
                        "employee_no": "u1001",
                        "directory_id": "acceptance-u1001",
                        "full_name": "Acceptance User",
                        "mail": "u1001@example.com",
                        "dept_codes": ["hr"],
                        "state": "active",
                    }
                ]
            },
        )
        ok = sync_resp.status_code == 200 and sync_resp.json().get("data", {}).get("success_count") == 1
        record_test("Identity source sync creates u1001", ok, f"Status: {sync_resp.status_code}")
        return ok

    print("=" * 70)
    print("OA RAG 企业知识库平台阶段性验收测试")
    print("=" * 70)

    print("\n[1] Health Check - GET /api/v1/health")
    resp = client.get("/api/v1/health")
    data = resp.json()
    record_test("Health check returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
    record_test(
        "Health has app/postgres/redis/zilliz statuses",
        all(k in data.get("data", {}) for k in ["app", "postgres", "redis", "zilliz"]),
        f"Keys: {list(data.get('data', {}).keys())}",
    )

    print("\n[2] Configs - GET /api/v1/configs")
    resp = client.get("/api/v1/configs")
    data = resp.json()
    record_test("Configs returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
    record_test("Configs returns non-empty data", bool(data.get("data")), f"Data: {data.get('data')}")

    sync_acceptance_identity()

    print("\n[3] Document Upload - POST /api/v1/documents/upload")
    pdf_path = project_root / "test_knowledge_docs" / "OA功能说明文档.pdf"
    doc_uuid = None
    job_uuid = None
    if pdf_path.exists():
        pdf_bytes = pdf_path.read_bytes()
        resp = client.post(
            "/api/v1/documents/upload",
            data={
                "title": "OA功能说明文档",
                "source_type": "rule_doc",
                "source_module": "oa",
                "access_level": "internal",
                "owner_dept": "hr",
            },
            files={"file": ("OA功能说明文档.pdf", pdf_bytes, "application/pdf")},
        )
        data = resp.json()
        record_test(
            "PDF upload returns 200",
            resp.status_code == 200,
            f"Status: {resp.status_code}, Response: {json.dumps(data, ensure_ascii=False)[:200]}",
        )
        if resp.status_code == 200 and data.get("data"):
            doc_uuid = data["data"]["doc_uuid"]
            job_uuid = data["data"]["job_uuid"]
            record_test("Upload returns doc_uuid", bool(doc_uuid), f"doc_uuid: {doc_uuid}")
            record_test("Upload returns job_uuid", bool(job_uuid), f"job_uuid: {job_uuid}")
            record_test(
                "Upload status is success",
                data["data"].get("status") == "success",
                f"Status: {data['data'].get('status')}",
            )
            record_test(
                "Chunk count >= 1",
                data["data"].get("chunk_count", 0) >= 1,
                f"Chunk count: {data['data'].get('chunk_count')}",
            )
    else:
        record_test("PDF file exists", False, f"Path: {pdf_path}")

    print("\n[4] Job Status - GET /api/v1/jobs/{job_uuid}")
    if job_uuid:
        resp = client.get(f"/api/v1/jobs/{job_uuid}")
        data = resp.json()
        record_test("Job query returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        record_test(
            "Job has status field",
            "status" in data.get("data", {}),
            f"Data keys: {list(data.get('data', {}).keys())}",
        )
    else:
        record_test("Job query skipped", False, "No job_uuid from upload")

    print("\n[5] Reindex Document - POST /api/v1/documents/{doc_uuid}/reindex")
    if doc_uuid:
        resp = client.post(f"/api/v1/documents/{doc_uuid}/reindex")
        data = resp.json()
        record_test("Reindex returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        record_test(
            "Reindex status is success",
            data.get("data", {}).get("status") == "success",
            f"Status: {data.get('data', {}).get('status')}",
        )
        record_test(
            "Reindex chunk_count >= 1",
            data.get("data", {}).get("chunk_count", 0) >= 1,
            f"Chunk count: {data.get('data', {}).get('chunk_count')}",
        )
    else:
        record_test("Reindex skipped", False, "No doc_uuid from upload")

    print("\n[6] Retrieval Search - POST /api/v1/retrieval/search")
    if doc_uuid:
        resp = client.post(
            "/api/v1/retrieval/search",
            json={
                "query": "OA 功能 审批",
                "top_k": 5,
                "filters": {"source_module": ["oa"]},
                "user_context": {"user_id": "u1001"},
            },
        )
        data = resp.json()
        record_test("Authorized search returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        record_test(
            "Authorized search returns hits",
            len(data.get("data", {}).get("hits", [])) >= 1,
            f"Hits count: {len(data.get('data', {}).get('hits', []))}",
        )

        resp = client.post(
            "/api/v1/retrieval/search",
            json={
                "query": "OA 功能 审批",
                "top_k": 5,
                "filters": {"source_module": ["oa"]},
                "user_context": {"user_id": "u9999"},
            },
        )
        data = resp.json()
        record_test(
            "Unauthorized search returns empty hits",
            data.get("data", {}).get("hits", []) == [],
            f"Hits: {data.get('data', {}).get('hits')}",
        )
    else:
        record_test("Search skipped", False, "No doc_uuid from upload")

    print("\n[7] Debug Search - POST /api/v1/retrieval/debug-search")
    if doc_uuid:
        resp = client.post(
            "/api/v1/retrieval/debug-search",
            json={
                "query": "OA 功能 审批",
                "top_k": 5,
                "filters": {"source_module": ["oa"]},
                "user_context": {"user_id": "u1001"},
            },
        )
        data = resp.json()
        record_test("Debug search returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        record_test(
            "Debug search returns hits",
            len(data.get("data", {}).get("hits", [])) >= 1,
            f"Hits count: {len(data.get('data', {}).get('hits', []))}",
        )
        record_test(
            "Debug search returns ranking_debug info",
            "ranking_debug" in data.get("data", {}),
            f"Keys: {list(data.get('data', {}).keys())}",
        )
    else:
        record_test("Debug search skipped", False, "No doc_uuid from upload")

    print("\n[8] QA Answer - POST /api/v1/qa/answer")
    if doc_uuid:
        resp = client.post(
            "/api/v1/qa/answer",
            headers={"X-Internal-Token": "test-internal-token"},
            json={
                "question": "OA 功能 审批",
                "top_k": 5,
                "filters": {"source_module": ["oa"]},
                "user_context": {"user_id": "u1001"},
                "generation_options": {"temperature": 0.1, "max_tokens": 300},
            },
        )
        data = resp.json()
        record_test("QA answer returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        record_test(
            "QA answer has citations",
            bool(data.get("data", {}).get("citations")),
            f"Citations count: {len(data.get('data', {}).get('citations', []))}",
        )
        record_test(
            "QA answer has grounded answer text",
            "基于命中的引用片段" in str(data.get("data", {}).get("answer", "")),
            f"Answer preview: {str(data.get('data', {}).get('answer', ''))[:100]}",
        )

        resp = client.post(
            "/api/v1/qa/answer",
            headers={"X-Internal-Token": "wrong-token"},
            json={
                "question": "OA 功能 审批",
                "top_k": 5,
                "user_context": {"user_id": "u1001"},
            },
        )
        record_test("QA rejects bad internal token with 401", resp.status_code == 401, f"Status: {resp.status_code}")
    else:
        record_test("QA skipped", False, "No doc_uuid from upload")

    print("\n[9] Upload Validation - unsupported extension")
    resp = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr"},
        files={"file": ("notes.exe", b"some binary content", "application/octet-stream")},
    )
    record_test("Rejects unsupported file with 400", resp.status_code == 400, f"Status: {resp.status_code}")

    print("\n[10] Spoofed Super Admin - request body must not grant access")
    if doc_uuid:
        resp = client.post(
            "/api/v1/retrieval/search",
            json={
                "query": "OA 功能",
                "top_k": 5,
                "user_context": {
                    "user_id": "u0001",
                    "roles": ["super_admin"],
                    "departments": [],
                    "is_super_admin": True,
                },
            },
        )
        data = resp.json()
        record_test(
            "Spoofed super admin does not access internal document",
            data.get("data", {}).get("hits", []) == [],
            f"Hits: {len(data.get('data', {}).get('hits', []))}",
        )
    else:
        record_test("Super admin test skipped", False, "No doc_uuid")

    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    total = len(results)
    print(f"验收结果: {passed}/{total} 通过, {failed}/{total} 失败")
    print("=" * 70)

    if failed > 0:
        print("\n失败项:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  ❌ {r['name']}: {r['details']}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
