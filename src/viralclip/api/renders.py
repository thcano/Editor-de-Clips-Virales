"""Rutas HTTP para renderizar clips verticales con FFmpeg."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    Query,
    Request,
    Response,
)
from fastapi.responses import FileResponse, StreamingResponse

from ..errors import (
    AnalysisNotFoundError,
    AnalysisNotReadyError,
    InvalidSourceError,
    RenderConflictError,
    RenderNotFoundError,
)
from ..models import Clip
from ..render import validate_source
from ..storage import RenderRecord, Storage
from .render_jobs import run_render_job
from .schemas import (
    ErrorPayload,
    RenderAccepted,
    RenderListResponse,
    RenderRequest,
    RenderResponse,
)
from .security import require_api_key

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

SSE_HEARTBEAT_SECONDS = 15.0
SSE_MAX_SECONDS = 3600.0
SSE_POLL_SECONDS = 0.5


def _format_sse(event: str, data: dict[str, Any], event_id: int) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event_id}\nevent: {event}\ndata: {payload}\n\n"


def _get_render(storage: Storage, render_id: str) -> RenderRecord:
    record = storage.get_render(render_id)
    if record is None:
        raise RenderNotFoundError(f"No existe el render {render_id}")
    return record


def _render_response(record: RenderRecord) -> RenderResponse:
    error = None
    if record.error_code:
        error = ErrorPayload(
            code=record.error_code,
            message=record.error_message or "Error durante el renderizado",
        )

    base = f"/api/renders/{record.id}"
    return RenderResponse(
        id=record.id,
        job_id=record.job_id,
        clip_id=record.clip_id,
        transcription_id=record.transcription_id,
        status=record.status,  # type: ignore[arg-type]
        created_at=record.created_at,
        updated_at=record.updated_at,
        progress=record.progress,
        stage=record.stage,
        source_path=record.source_path,
        width=record.width,
        height=record.height,
        duration=record.duration,
        size_bytes=record.size_bytes,
        error=error,
        events_url=f"{base}/events",
        download_url=(
            f"{base}/download"
            if record.status == "done" and record.output_path
            else None
        ),
        thumbnail_url=(
            f"{base}/thumbnail"
            if record.status == "done" and record.thumbnail_path
            else None
        ),
    )


def _find_clip(storage: Storage, analysis_id: str, clip_id: str) -> Clip:
    job = storage.get_job(analysis_id)
    if job is None:
        raise AnalysisNotFoundError(f"No existe el análisis {analysis_id}")
    result = storage.result_for(job)
    if result is None:
        raise AnalysisNotReadyError(
            "El análisis todavía no terminó; espera antes de renderizar"
        )
    clip = next((item for item in result.clips if item.id == clip_id), None)
    if clip is None:
        raise AnalysisNotFoundError(
            f"El análisis {analysis_id} no contiene el clip {clip_id}"
        )
    return clip


@router.post(
    "/analyses/{analysis_id}/clips/{clip_id}/render",
    status_code=202,
    response_model=RenderAccepted,
)
def create_render(
    analysis_id: str,
    clip_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: RenderRequest | None = None,
) -> RenderAccepted:
    """Encola el renderizado de un clip del análisis."""

    settings = request.app.state.settings
    storage: Storage = request.app.state.storage
    job = storage.get_job(analysis_id)
    if job is None:
        raise AnalysisNotFoundError(f"No existe el análisis {analysis_id}")

    clip = _find_clip(storage, analysis_id, clip_id)

    requested = payload.video_path.strip() if payload and payload.video_path else None
    source_path = requested or job.source_path
    if not source_path:
        raise InvalidSourceError(
            "Indica el video de origen: este análisis no viene de una transcripción"
        )
    validate_source(source_path)

    active = storage.find_active_render(job_id=analysis_id, clip_id=clip_id)
    if active is not None and not (payload and payload.force):
        raise RenderConflictError(
            f"El clip {clip_id} ya tiene un render en curso ({active.id})"
        )

    render_id = str(uuid4())
    request_id = getattr(request.state, "request_id", None)
    storage.create_render(
        render_id=render_id,
        job_id=analysis_id,
        clip_id=clip_id,
        source_path=str(Path(source_path).expanduser()),
        transcription_id=job.transcription_id,
        request_id=request_id,
    )
    storage.audit(
        action="render.create",
        resource="render",
        resource_id=render_id,
        request_id=request_id,
        detail=f"analysis={analysis_id}; clip={clip_id}",
    )

    background_tasks.add_task(
        run_render_job,
        storage=storage,
        settings=settings,
        render_id=render_id,
        clip=clip,
        renderer_factory=request.app.state.renderer_factory,
    )

    return RenderAccepted(
        id=render_id,
        status="queued",
        events_url=f"/api/renders/{render_id}/events",
    )


@router.get("/renders", response_model=RenderListResponse)
def list_renders(
    request: Request,
    job_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RenderListResponse:
    storage: Storage = request.app.state.storage
    records, total = storage.list_renders(
        job_id=job_id, limit=limit, offset=offset
    )
    return RenderListResponse(
        items=[_render_response(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/renders/{render_id}", response_model=RenderResponse)
def get_render(render_id: str, request: Request) -> RenderResponse:
    storage: Storage = request.app.state.storage
    return _render_response(_get_render(storage, render_id))


@router.get("/renders/{render_id}/events")
def render_events(
    render_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """SSE con el progreso del render y reconexión por ``Last-Event-ID``."""

    storage: Storage = request.app.state.storage
    record = _get_render(storage, render_id)

    try:
        start_id = int(last_event_id) + 1 if last_event_id else 1
    except (TypeError, ValueError):
        start_id = 1
    if start_id < 1:
        start_id = 1

    async def event_stream():
        current = record
        signature: tuple[Any, ...] | None = None
        event_id = start_id
        started = time.monotonic()
        last_emit = started

        yield "retry: 3000\n\n"

        while True:
            current_signature = (
                current.status,
                current.progress,
                current.stage,
                current.error_code,
            )
            if current_signature != signature:
                event = (
                    "done"
                    if current.status == "done"
                    else "error"
                    if current.status == "error"
                    else "progress"
                )
                response = _render_response(current)
                data = response.model_dump(mode="json")
                yield _format_sse(event, data, event_id)
                event_id += 1
                signature = current_signature
                last_emit = time.monotonic()

            if current.is_terminal:
                break
            if time.monotonic() - started >= SSE_MAX_SECONDS:
                break

            await asyncio.sleep(SSE_POLL_SECONDS)
            refreshed = storage.get_render(render_id)
            if refreshed is None:
                break
            current = refreshed

            if time.monotonic() - last_emit >= SSE_HEARTBEAT_SECONDS:
                yield ": ping\n\n"
                last_emit = time.monotonic()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/renders/{render_id}/download")
def download_render(render_id: str, request: Request) -> FileResponse:
    storage: Storage = request.app.state.storage
    record = _get_render(storage, render_id)
    if record.status != "done" or not record.output_path:
        raise RenderNotFoundError("El render todavía no está listo")
    path = Path(record.output_path)
    if not path.is_file():
        raise RenderNotFoundError("El archivo del render ya no existe")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"{record.clip_id}-{record.id[:8]}.mp4",
    )


@router.get("/renders/{render_id}/thumbnail")
def download_thumbnail(render_id: str, request: Request) -> FileResponse:
    storage: Storage = request.app.state.storage
    record = _get_render(storage, render_id)
    if record.status != "done" or not record.thumbnail_path:
        raise RenderNotFoundError("El render no tiene miniatura")
    path = Path(record.thumbnail_path)
    if not path.is_file():
        raise RenderNotFoundError("La miniatura ya no existe")
    return FileResponse(
        path,
        media_type="image/jpeg",
        filename=f"{record.clip_id}-{record.id[:8]}.jpg",
    )


@router.delete("/renders/{render_id}", status_code=204)
def delete_render(render_id: str, request: Request) -> Response:
    storage: Storage = request.app.state.storage
    record = _get_render(storage, render_id)
    if record.status in {"queued", "running"}:
        raise RenderConflictError(
            "No se puede borrar un render en curso; espera a que termine"
        )

    for raw in (record.output_path, record.thumbnail_path):
        if raw:
            Path(raw).unlink(missing_ok=True)
    storage.delete_render(render_id)
    storage.audit(
        action="render.delete",
        resource="render",
        resource_id=render_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=204)
