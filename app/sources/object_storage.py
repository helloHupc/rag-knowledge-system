from __future__ import annotations

import hashlib
import hmac
import mimetypes
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode, urlsplit
from xml.etree import ElementTree

import httpx

from app.core.errors import AppError, ErrorCode
from app.sources.types import SourceDocument, SourceReadResult


class ObjectStorageSourceConnector:
    name = "object_storage"

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        prefix: str = "",
        allowed_extensions: set[str] | None = None,
        max_files: int = 100,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region or "us-east-1"
        self.prefix = prefix.lstrip("/")
        self.allowed_extensions = {item.lower().lstrip(".") for item in allowed_extensions or set()}
        self.max_files = max_files

    async def read(self) -> SourceReadResult:
        if self.max_files <= 0:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message="max_files must be greater than 0",
            )
        if not self.endpoint_url or not self.bucket or not self.access_key or not self.secret_key:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message="object storage endpoint, bucket, access_key and secret_key are required",
            )

        documents: list[SourceDocument] = []
        skipped: list[dict] = []
        continuation_token: str | None = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(documents) < self.max_files:
                objects, next_token = await self._list_objects(client, continuation_token)
                if not objects:
                    break

                for object_info in objects:
                    key = object_info["key"]
                    if key.endswith("/"):
                        skipped.append(self._skip_info(key, "folder_marker", object_info))
                        continue

                    extension = PurePosixPath(key).suffix.lower().lstrip(".")
                    if self.allowed_extensions and extension not in self.allowed_extensions:
                        skipped.append(self._skip_info(key, "unsupported_extension", object_info))
                        continue

                    try:
                        content = await self._get_object(client, key)
                    except AppError as exc:
                        skipped.append(self._skip_info(key, "read_failed", {**object_info, "message": exc.message}))
                        continue

                    documents.append(
                        SourceDocument(
                            file_name=PurePosixPath(key).name,
                            content=content,
                            mime_type=mimetypes.guess_type(key)[0],
                            metadata={
                                "source_connector": self.name,
                                "bucket": self.bucket,
                                "object_key": key,
                                "relative_path": self._relative_path(key),
                                "endpoint_url": self.endpoint_url,
                                "etag": object_info.get("etag"),
                                "source_mtime": object_info.get("last_modified"),
                                "source_size": object_info.get("size"),
                            },
                        )
                    )
                    if len(documents) >= self.max_files:
                        break

                if len(documents) >= self.max_files or not next_token:
                    break
                continuation_token = next_token

        return SourceReadResult(
            source_name=self.name,
            documents=documents,
            metadata={
                "endpoint_url": self.endpoint_url,
                "bucket": self.bucket,
                "prefix": self.prefix,
                "max_files": self.max_files,
                "skipped": skipped,
            },
        )

    async def _list_objects(
        self,
        client: httpx.AsyncClient,
        continuation_token: str | None,
    ) -> tuple[list[dict], str | None]:
        params: dict[str, str] = {
            "list-type": "2",
            "max-keys": "1000",
        }
        if self.prefix:
            params["prefix"] = self.prefix
        if continuation_token:
            params["continuation-token"] = continuation_token

        response = await self._request(client, "GET", "", params=params)
        root = ElementTree.fromstring(response.content)
        namespace = self._xml_namespace(root)
        contents = []
        for item in root.findall(f"{namespace}Contents"):
            key = self._xml_text(item, namespace, "Key")
            if not key:
                continue
            contents.append(
                {
                    "key": key,
                    "etag": self._xml_text(item, namespace, "ETag"),
                    "last_modified": self._xml_text(item, namespace, "LastModified"),
                    "size": int(self._xml_text(item, namespace, "Size") or 0),
                }
            )

        next_token = self._xml_text(root, namespace, "NextContinuationToken")
        is_truncated = (self._xml_text(root, namespace, "IsTruncated") or "").lower() == "true"
        return contents, next_token if is_truncated else None

    async def _get_object(self, client: httpx.AsyncClient, key: str) -> bytes:
        response = await self._request(client, "GET", key)
        return response.content

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        object_key: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = self._build_url(object_key, params or {})
        headers = self._signed_headers(method, object_key, params or {})
        response = await client.request(method, url, headers=headers)
        if response.status_code >= 400:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message=f"object storage request failed: HTTP {response.status_code}",
            )
        return response

    def _build_url(self, object_key: str, params: dict[str, str]) -> str:
        path = f"/{quote(self.bucket, safe='')}"
        if object_key:
            path += f"/{quote(object_key, safe='/')}"
        query = urlencode(sorted(params.items()), quote_via=quote)
        return f"{self.endpoint_url}{path}{'?' + query if query else ''}"

    def _signed_headers(self, method: str, object_key: str, params: dict[str, str]) -> dict[str, str]:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        parsed = urlsplit(self.endpoint_url)
        host = parsed.netloc
        canonical_uri = f"/{quote(self.bucket, safe='')}"
        if object_key:
            canonical_uri += f"/{quote(object_key, safe='/')}"
        canonical_query = urlencode(sorted(params.items()), quote_via=quote)
        payload_hash = "UNSIGNED-PAYLOAD"

        canonical_headers = (
            f"host:{host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )

        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = self._signing_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "Authorization": authorization,
            "Host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }

    def _signing_key(self, date_stamp: str) -> bytes:
        date_key = self._hmac(f"AWS4{self.secret_key}".encode("utf-8"), date_stamp)
        region_key = self._hmac(date_key, self.region)
        service_key = self._hmac(region_key, "s3")
        return self._hmac(service_key, "aws4_request")

    @staticmethod
    def _hmac(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

    @staticmethod
    def _xml_namespace(root: ElementTree.Element) -> str:
        if root.tag.startswith("{"):
            return root.tag.split("}", 1)[0] + "}"
        return ""

    @staticmethod
    def _xml_text(root: ElementTree.Element, namespace: str, tag: str) -> str | None:
        element = root.find(f"{namespace}{tag}")
        return element.text if element is not None else None

    def _relative_path(self, key: str) -> str:
        if self.prefix and key.startswith(self.prefix):
            return key[len(self.prefix) :].lstrip("/")
        return key

    def _skip_info(self, key: str, reason: str, metadata: dict) -> dict:
        return {
            "file_name": PurePosixPath(key).name,
            "relative_path": self._relative_path(key),
            "object_key": key,
            "reason": reason,
            **metadata,
        }
