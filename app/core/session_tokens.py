from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode


@dataclass(frozen=True)
class SessionTokenIssue:
    access_token: str
    expires_in: int
    token_id: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class SessionTokenPayload:
    user_id: str
    token_id: str | None
    issued_at: datetime | None
    expires_at: datetime


def create_session_token(user_id: str, settings: Settings) -> SessionTokenIssue:
    if not settings.auth_session_secret:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="auth session secret is not configured",
            status_code=401,
        )

    issued_at = int(time.time())
    expires_at = issued_at + settings.auth_session_ttl_seconds
    token_id = secrets.token_urlsafe(32)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": settings.auth_session_issuer,
        "sub": user_id,
        "jti": token_id,
        "iat": issued_at,
        "exp": expires_at,
    }
    signing_input = ".".join(
        (
            _base64url_json(header),
            _base64url_json(payload),
        )
    )
    signature = _sign(signing_input, settings.auth_session_secret)
    return SessionTokenIssue(
        access_token=f"{signing_input}.{signature}",
        expires_in=settings.auth_session_ttl_seconds,
        token_id=token_id,
        issued_at=datetime.fromtimestamp(issued_at, UTC),
        expires_at=datetime.fromtimestamp(expires_at, UTC),
    )


def verify_session_token(token: str, settings: Settings) -> SessionTokenPayload:
    if not settings.auth_session_secret:
        raise _invalid_token("auth session secret is not configured")

    parts = token.split(".")
    if len(parts) != 3:
        raise _invalid_token("invalid session token")

    signing_input = f"{parts[0]}.{parts[1]}"
    expected_signature = _sign(signing_input, settings.auth_session_secret)
    if not hmac.compare_digest(expected_signature, parts[2]):
        raise _invalid_token("invalid session token signature")

    try:
        header = _base64url_decode_json(parts[0])
        payload = _base64url_decode_json(parts[1])
    except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise _invalid_token("invalid session token payload") from exc

    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise _invalid_token("unsupported session token")
    if payload.get("iss") != settings.auth_session_issuer:
        raise _invalid_token("invalid session token issuer")

    user_id = payload.get("sub")
    token_id = payload.get("jti")
    issued_at = payload.get("iat")
    expires_at = payload.get("exp")
    if not isinstance(user_id, str) or not user_id.strip():
        raise _invalid_token("session token subject is missing")
    if token_id is not None and (not isinstance(token_id, str) or not token_id.strip()):
        raise _invalid_token("session token id is invalid")
    if not isinstance(expires_at, int) or expires_at <= int(time.time()):
        raise _invalid_token("session token expired")

    return SessionTokenPayload(
        user_id=user_id.strip(),
        token_id=token_id.strip() if isinstance(token_id, str) else None,
        issued_at=datetime.fromtimestamp(issued_at, UTC) if isinstance(issued_at, int) else None,
        expires_at=datetime.fromtimestamp(expires_at, UTC),
    )


def _base64url_json(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _base64url_encode(raw)


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64url_decode_json(value: str) -> dict:
    padding = "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("expected json object")
    return decoded


def _sign(signing_input: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return _base64url_encode(digest)


def _invalid_token(message: str) -> AppError:
    return AppError(
        code=ErrorCode.AUTHENTICATION_FAILED,
        message=message,
        status_code=401,
    )
