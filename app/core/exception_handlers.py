from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from app.core.errors import AppError, ErrorCode
from app.core.responses import error_response


logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", "-")
        logger.warning("Application error: %s", exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                code=exc.code,
                message=exc.message,
                data=exc.data,
                trace_id=trace_id,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", "-")
        logger.warning("Request validation failed: %s", exc)
        return JSONResponse(
            status_code=422,
            content=error_response(
                code=ErrorCode.INVALID_REQUEST,
                message="invalid request",
                data=jsonable_encoder(exc.errors()),
                trace_id=trace_id,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", "-")
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content=error_response(
                code=ErrorCode.INTERNAL_ERROR,
                message=str(exc) or "internal error",
                trace_id=trace_id,
            ),
        )
