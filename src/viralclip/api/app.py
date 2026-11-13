"""Aplicación FastAPI del Editor de Clips Virales."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
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

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
INDEX_HTML = WEB_DIR / "index.html"


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
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return FileResponse(
            INDEX_HTML,
            media_type="text/html",
            headers={
                "Cache-Control": "no-cache",
                "Content-Security-Policy": (
                    "default-src 'self'; img-src 'self' data:; "
                    "style-src 'self'; script-src 'self'; "
                    "connect-src 'self'; base-uri 'none'; "
                    "form-action 'self'; frame-ancestors 'none'"
                ),
            },
        )

    return app
