from __future__ import annotations

from http import HTTPStatus


class ErrorCode:
    SUCCESS = 0
    INVALID_REQUEST = 40001
    UNSUPPORTED_FILE_TYPE = 40002
    EMPTY_OR_CORRUPTED_FILE = 40003
    USER_CONTEXT_MISSING = 40004
    DIFY_APP_KEY_MISSING = 40005
    AUTHENTICATION_FAILED = 40101
    PERMISSION_DENIED = 40301
    DOCUMENT_NOT_FOUND = 40401
    JOB_NOT_FOUND = 40402
    DOCUMENT_DUPLICATED = 40901
    DOCUMENT_PARSE_FAILED = 42201
    CHUNKING_FAILED = 42202
    EMBEDDING_FAILED = 42203
    VECTOR_WRITE_FAILED = 42204
    RETRIEVAL_FAILED = 42205
    LLM_GENERATION_FAILED = 42206
    IMAGE_RECOGNITION_FAILED = 42207
    INTERNAL_ERROR = 50001


class AppError(Exception):
    def __init__(
        self,
        *,
        code: int,
        message: str,
        status_code: int = HTTPStatus.BAD_REQUEST,
        data: object | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.data = data
