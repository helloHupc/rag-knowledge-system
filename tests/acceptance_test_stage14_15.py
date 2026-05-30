"""Stage 14/15 acceptance test script for OA RAG PoC."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    test_db_path = Path("/tmp/oa_rag_stage14_15_test.sqlite3")
    test_storage_root = Path("/tmp/oa_rag_stage14_15_test_data")

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

    def record(name: str, passed: bool, details: str = "") -> None:
        status = "PASS" if passed else "FAIL"
        results.append((name, status, details))
        print(f"[{status}] {name}")
        if details and not passed:
            print(f"       {details}")

    pdf_path = project_root / "test_knowledge_docs" / "OA功能说明文档.pdf"
    if not pdf_path.exists():
        record("Stage14/15 sample file exists", False, str(pdf_path))
        return 1

    upload_resp = client.post(
        "/api/v1/documents/upload",
        data={"title": "Stage14 Document", "source_type": "rule_doc", "source_module": "oa"},
        files={"file": ("OA功能说明文档.pdf", pdf_path.read_bytes(), "application/pdf")},
    )
    upload_body = upload_resp.json()
    record("S14-01 upload returns 200", upload_resp.status_code == 200)
    if upload_resp.status_code != 200:
        return 1

    doc_uuid = upload_body["data"]["doc_uuid"]

    detail_resp = client.get(f"/api/v1/documents/{doc_uuid}")
    detail_body = detail_resp.json()
    record("S14-02 detail returns file_path", bool(detail_body["data"].get("file_path")))
    record("S14-03 detail returns file_exists=true", detail_body["data"].get("file_exists") is True)

    download_resp = client.get(f"/api/v1/documents/{doc_uuid}/download")
    record("S14-04 download returns 200", download_resp.status_code == 200)
    record("S14-05 download returns bytes", bool(download_resp.content))

    delete_resp = client.delete(f"/api/v1/documents/{doc_uuid}")
    record("S14-06 delete returns 200", delete_resp.status_code == 200)
    missing_download_resp = client.get(f"/api/v1/documents/{doc_uuid}/download")
    record("S14-07 download after delete returns 404", missing_download_resp.status_code == 404)

    configs_resp = client.get("/api/v1/configs")
    configs_body = configs_resp.json()
    record("S15-01 configs returns 200", configs_resp.status_code == 200)
    for key in (
        "provider_timeout_seconds",
        "provider_retry_count",
        "health_probe_external_services",
        "embedding_vector_size",
    ):
        record(f"S15 configs exposes {key}", key in configs_body.get("data", {}))

    failed = [item for item in results if item[1] == "FAIL"]
    print(f"\nSummary: {len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
