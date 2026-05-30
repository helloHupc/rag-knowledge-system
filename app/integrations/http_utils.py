from __future__ import annotations


def build_openai_compatible_url(base_url: str, endpoint: str) -> str:
    normalized_base = base_url.rstrip("/")
    if normalized_base.endswith(endpoint):
        return normalized_base
    return f"{normalized_base}/{endpoint.lstrip('/')}"
