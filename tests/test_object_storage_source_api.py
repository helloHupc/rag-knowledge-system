from __future__ import annotations

import httpx


class _FakeObjectStorageClient:
    def __init__(self, *args, **kwargs) -> None:
        self.requests: list[tuple[str, str]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def request(self, method: str, url: str, headers=None):
        self.requests.append((method, url))
        if "list-type=2" in url:
            return httpx.Response(
                200,
                content=b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>knowledge</Name>
  <Prefix>hr/</Prefix>
  <IsTruncated>false</IsTruncated>
  <Contents>
    <Key>hr/policy.md</Key>
    <LastModified>2026-05-21T00:00:00.000Z</LastModified>
    <ETag>"etag-policy"</ETag>
    <Size>24</Size>
  </Contents>
  <Contents>
    <Key>hr/ignore.exe</Key>
    <LastModified>2026-05-21T00:00:01.000Z</LastModified>
    <ETag>"etag-ignore"</ETag>
    <Size>3</Size>
  </Contents>
</ListBucketResult>""",
            )
        if url.endswith("/knowledge/hr/policy.md"):
            return httpx.Response(200, content="# 请假规则\n请假需要审批。")
        return httpx.Response(404, content=b"not found")


def test_object_storage_source_syncs_supported_objects_and_writes_history(client, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeObjectStorageClient)

    response = client.post(
        "/api/v1/sources/object-storage/sync",
        json={
            "endpoint_url": "https://storage.example.test",
            "bucket": "knowledge",
            "prefix": "hr/",
            "region": "us-east-1",
            "access_key": "ak-test",
            "secret_key": "sk-test",
            "source_type": "object_storage",
            "source_module": "hr",
            "version": "object-v1",
            "access_level": "internal",
            "tags": ["object", "sync"],
            "extra_meta": {"chunking_strategy": "structural"},
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source_name"] == "object_storage"
    assert payload["run_uuid"]
    assert payload["bucket"] == "knowledge"
    assert payload["prefix"] == "hr/"
    assert payload["success_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["skipped_count"] == 1
    assert payload["items"][0]["relative_path"] == "policy.md"
    assert payload["skipped"][0]["relative_path"] == "ignore.exe"

    history = client.get("/api/v1/sources/sync-runs?page=1&page_size=10&source_type=object_storage")
    assert history.status_code == 200
    history_payload = history.json()["data"]
    assert history_payload["total"] == 1
    assert history_payload["items"][0]["run_uuid"] == payload["run_uuid"]
    assert history_payload["items"][0]["source_name"] == "object_storage"

    detail = client.get(f"/api/v1/sources/sync-runs/{payload['run_uuid']}")
    assert detail.status_code == 200
    detail_payload = detail.json()["data"]
    assert detail_payload["request_json"]["secret_key"] == "***"
    assert detail_payload["request_json"]["access_key"] == "ak-test"
    assert {item["status"] for item in detail_payload["items"]} == {"success", "skipped"}
    assert detail_payload["items"][0]["metadata_json"]["bucket"] == "knowledge"
    assert detail_payload["items"][0]["metadata_json"]["object_key"] == "hr/policy.md"
