"""Manejadores de error que traducen el dominio a respuestas HTTP."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..errors import ErrorCode, ViralClipError

logger = logging.getLogger("viralclip.api")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def viralclip_error_handler(
    request: Request, exc: ViralClipError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_payload(_request_id(request)),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = str(error.get("msg", "valor inválido"))
        parts.append(f"{location}: {message}" if location else message)

    return JSONResponse(
        status_code=422,
        content={
            "code": ErrorCode.INVALID_PARAMETERS.value,
            "message": "Los parámetros de la solicitud no son válidos",
            "detail": "; ".join(parts)[:500],
            "request_id": _request_id(request),
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Error no controlado",
        extra={"request_id": _request_id(request), "path": request.url.path},
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": ErrorCode.INTERNAL.value,
            "message": "Error interno del servidor",
            "request_id": _request_id(request),
        },
    )
