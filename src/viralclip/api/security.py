"""Seguridad local basada en API key opcional."""

from __future__ import annotations

import secrets

from fastapi import Request

from ..errors import UnauthorizedError


def require_api_key(request: Request) -> None:
    """Exige ``X-API-Key`` solo si hay una clave configurada."""

    settings = request.app.state.settings
    if not settings.api_key:
        return

    provided = request.headers.get("X-API-Key")
    if not provided or not secrets.compare_digest(provided, settings.api_key):
        raise UnauthorizedError("La API key es obligatoria y debe coincidir")
