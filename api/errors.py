from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from uuid import uuid4

from services.protocol.error_response import anthropic_error_response, openai_error_response
from utils.log import logger


def _is_openai_compatible_path(path: str) -> bool:
    return path == "/v1" or path.startswith("/v1/")


def _is_anthropic_messages_path(path: str) -> bool:
    return path == "/v1/messages"


def _compatible_error_response(
    request: Request,
    detail: object,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    if _is_anthropic_messages_path(request.url.path):
        return anthropic_error_response(detail, status_code, headers=headers)
    return openai_error_response(detail, status_code, headers=headers)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if _is_openai_compatible_path(request.url.path):
            return _compatible_error_response(request, exc.detail, exc.status_code, exc.headers)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": jsonable_encoder(exc.detail)},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        if _is_openai_compatible_path(request.url.path):
            return _compatible_error_response(request, exc.errors(), 422)
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        error_id = uuid4().hex[:12]
        logger.error({
            "event": "unhandled_exception",
            "error_id": error_id,
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        if _is_openai_compatible_path(request.url.path):
            return _compatible_error_response(
                request,
                {"error": f"服务器内部错误，错误编号：{error_id}"},
                500,
            )
        return JSONResponse(
            status_code=500,
            content={"detail": {"error": f"服务器内部错误，错误编号：{error_id}"}},
        )
