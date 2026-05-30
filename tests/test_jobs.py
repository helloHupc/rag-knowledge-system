from __future__ import annotations


def test_get_missing_job_returns_not_found(client):
    response = client.get("/api/v1/jobs/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == 40402
    assert payload["message"] == "job not found"
