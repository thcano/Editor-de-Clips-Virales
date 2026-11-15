"""Aplicación FastAPI del Editor de Clips Virales."""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.staticfiles import NotModifiedResponse
from starlette.types import Scope

from .. import __version__
from ..assets import (
    ASSET_VERSION_COOKIE,
    CLEAR_CACHE_HEADER,
    INDEX_HTML,
    VERSIONED_ASSETS,
    WEB_DIR,
    AssetVersion,
    versioned_url,
)
from ..config import Settings
from ..errors import ViralClipError
from ..llm.ollama import OllamaClient
from ..storage import Storage
from .errors import (
    unhandled_error_handler,
    validation_error_handler,
    viralclip_error_handler,
)
from .renders import router as renders_router
from .routes import router
from .transcriptions import router as transcriptions_router

#: Política de caché de los assets del frontend.
#:
#: Sin ``Cache-Control`` el navegador aplica *caché heurística* (10 % de la
#: antigüedad del fichero) y puede servir durante días una versión antigua de
#: ``styles.css`` sin siquiera consultar al servidor. Como la app sirve siempre
#: desde ``127.0.0.1``, el EXE y el clon del repositorio comparten origen y URL,
#: de modo que un CSS obsoleto se quedaba pegado en ambos.
#:
#: ``no-cache`` no desactiva la caché: obliga a *revalidar* contra el servidor.
#: El ``ETag`` sigue evitando transferir el cuerpo cuando el fichero no ha
#: cambiado (respuesta 304), así que el coste es mínimo.
STATIC_CACHE_CONTROL = "no-cache"


class RevalidatingStaticFiles(StaticFiles):
    """Sirve los assets del frontend garantizando siempre la versión vigente.

    Resuelve dos problemas que dejaban al navegador con el diseño anterior:

    1. **Caché heurística.** ``StaticFiles`` no envía ``Cache-Control``, así que
       el navegador fija la vigencia a partir de ``Last-Modified`` y puede
       devolver una copia antigua de ``styles.css`` sin preguntar al servidor.
       Aquí se envía ``Cache-Control: no-cache`` para forzar la revalidación.

    2. **304 por fecha.** Starlette acepta ``If-Modified-Since`` y responde 304
       cuando la fecha cacheada es igual o posterior a ``Last-Modified`` del
       fichero. Tras reinstalar o clonar el repositorio la fecha del fichero
       puede ser *anterior* a la de la copia ya cacheada, de modo que el
       servidor confirmaba como "no modificado" un ``styles.css`` obsoleto.
       Aquí la revalidación solo se acepta por ``ETag``, que se calcula sobre
       el **hash del contenido**: solo un 304 cuando los bytes son realmente
       los mismos.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # ruta -> ((mtime_ns, tamaño), etag)
        self._etag_cache: dict[str, tuple[tuple[int, int], str]] = {}

    def _content_etag(self, full_path: Any) -> str:
        """ETag derivado del hash del contenido, no de la fecha del fichero."""

        path = Path(full_path)
        key = str(path)
        stat_result = path.stat()
        stamp = (stat_result.st_mtime_ns, stat_result.st_size)
        cached = self._etag_cache.get(key)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        etag = f'"{digest[:32]}"'
        self._etag_cache[key] = (stamp, etag)
        return etag

    def is_not_modified(self, response_headers: Headers, request_headers: Headers) -> bool:
        """Solo ``If-None-Match`` decide; ``If-Modified-Since`` se ignora.

        Ignorar la fecha es lo que garantiza que el cliente nunca conserve un
        asset obsoleto: si no puede comparar por ETag, recibe el fichero
        completo (200) en lugar de un 304 engañoso.
        """

        if_none_match = request_headers.get("if-none-match")
        if not if_none_match:
            return False
        etag = response_headers.get("etag")
        if not etag:
            return False
        if if_none_match.strip() == "*":
            return True
        candidates = [tag.strip().removeprefix("W/") for tag in if_none_match.split(",")]
        return etag in candidates

    def file_response(
        self,
        full_path: Any,
        stat_result: Any,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        request_headers = Headers(scope=scope)

        response = FileResponse(full_path, status_code=status_code, stat_result=stat_result)
        response.headers["etag"] = self._content_etag(full_path)
        response.headers["cache-control"] = STATIC_CACHE_CONTROL
        response.headers["pragma"] = "no-cache"
        response.headers["expires"] = "0"
        if self.is_not_modified(response.headers, request_headers):
            return NotModifiedResponse(response.headers)
        return response


def create_app(
    *,
    settings: Settings | None = None,
    storage: Storage | None = None,
    ollama_client: OllamaClient | None = None,
    transcriber_factory=None,
    renderer_factory=None,
) -> FastAPI:
    """Crea la app con dependencias inyectables (útil para pruebas)."""

    settings = settings or Settings.from_env()
    owns_storage = storage is None
    storage = storage or Storage(settings.db_path)
    storage.mark_interrupted_jobs()
    storage.mark_interrupted_transcriptions()
    storage.mark_interrupted_renders()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if app.state.owns_storage:
            app.state.storage.close()

    app = FastAPI(
        title="Editor de Clips Virales API",
        version=__version__,
        description=(
            "API local para analizar transcripciones y generar clips con ganchos, "
            "subtítulos y hashtags. Local-first: sin nube por defecto."
        ),
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.storage = storage
    app.state.owns_storage = owns_storage
    app.state.ollama_client = ollama_client
    app.state.transcriber_factory = transcriber_factory
    app.state.renderer_factory = renderer_factory

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    app.add_exception_handler(ViralClipError, viralclip_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(router)
    app.include_router(transcriptions_router)
    app.include_router(renders_router)

    if WEB_DIR.is_dir():
        app.mount(
            "/static",
            RevalidatingStaticFiles(directory=WEB_DIR),
            name="static",
        )

    asset_version = AssetVersion(WEB_DIR)

    @app.get("/", include_in_schema=False)
    def root(request: Request) -> Response:
        version = asset_version.get()
        html = INDEX_HTML.read_text(encoding="utf-8")
        for name in VERSIONED_ASSETS:
            html = html.replace(
                f"/static/{name}",
                versioned_url(f"/static/{name}", version),
            )

        headers = {
            "Cache-Control": "no-cache",
            "Content-Security-Policy": (
                "default-src 'self'; img-src 'self' data:; "
                "style-src 'self'; script-src 'self'; "
                "connect-src 'self'; base-uri 'none'; "
                "form-action 'self'; frame-ancestors 'none'"
            ),
        }

        # Si el navegador todavía no ha visto esta versión de los assets, se le
        # pide que vacíe su caché HTTP del origen. Así desaparece cualquier
        # copia del diseño anterior que hubiera quedado guardada (por ejemplo,
        # tras actualizar el ejecutable o clonar el repositorio).
        if request.cookies.get(ASSET_VERSION_COOKIE) != version:
            headers[CLEAR_CACHE_HEADER] = '"cache"'
            headers["Set-Cookie"] = (
                f"{ASSET_VERSION_COOKIE}={version}; Path=/; SameSite=Lax; Max-Age=31536000"
            )

        return HTMLResponse(html, headers=headers)

    return app
