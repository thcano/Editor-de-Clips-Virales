"""Rutas HTTP de la API local."""

from __future__ import annotations

import asyncio
import json
import time
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
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from .. import __version__
from ..errors import (
    AnalysisNotFoundError,
    AnalysisNotReadyError,
    FeatureDisabledError,
    InvalidParameterError,
    PayloadTooLargeError,
)
from ..llm.ollama import OllamaClient
from ..models import AnalysisRequest, FeatureFlag
from ..platforms import SUPPORTED_PLATFORMS
from ..render import ffprobe_available
from ..storage import JobRecord, Storage
from ..subtitles import to_srt, to_vtt
from ..transcript import normalize_transcript
from ..transcription import (
    SUPPORTED_MODELS,
    detect_device,
    ffmpeg_available,
)
from .jobs import run_analysis_job
from .schemas import (
    AnalysisListResponse,
    AnalysisResponse,
    ConfigResponse,
    ErrorPayload,
    ExportFormat,
    FeatureFlagUpdate,
    HealthResponse,
    JobAccepted,
    OllamaStatus,
)
from .security import require_api_key

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

SSE_HEARTBEAT_SECONDS = 15.0
SSE_MAX_SECONDS = 600.0
SSE_POLL_SECONDS = 0.5


def _get_job(storage: Storage, analysis_id: str) -> JobRecord:
    job = storage.get_job(analysis_id)
    if job is None:
        raise AnalysisNotFoundError(f"No existe el análisis {analysis_id}")
    return job


def _job_response(
    job: JobRecord, storage: Storage, *, include_clips: bool
) -> AnalysisResponse:
    result = storage.result_for(job)
    error = None
    if job.error_code:
        error = ErrorPayload(
            code=job.error_code,
            message=job.error_message or "Error durante el análisis",
        )

    return AnalysisResponse(
        id=job.id,
        status=job.status,  # type: ignore[arg-type]
        created_at=job.created_at,
        updated_at=job.updated_at,
        platform=job.platform,  # type: ignore[arg-type]
        progress=job.progress,
        stage=job.stage,
        source_path=job.source_path,
        engine=result.engine if result else None,
        error=error,
        clips=list(result.clips) if result and include_clips else [],
    )


def _combined_subtitles(result):
    lines = []
    for clip in result.clips:
        for line in clip.subtitles:
            lines.append(line.model_copy(update={"index": len(lines) + 1}))
    return lines


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _format_sse(event: str, data: dict[str, Any], event_id: int) -> str:
    """Serializa un evento SSE con id, tipo y payload JSON compacto."""

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event_id}\nevent: {event}\ndata: {payload}\n\n"


def _flag_enabled(storage: Storage, name: str) -> bool:
    return name in storage.active_flags()


# ---------------------------------------------------------------------------
# Sistema
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    storage: Storage = request.app.state.storage

    try:
        storage.ping()
        database = "ok"
    except Exception:
        database = "error"

    injected: OllamaClient | None = request.app.state.ollama_client
    if not settings.llm_enabled:
        ollama = OllamaStatus(
            available=False,
            model=settings.ollama_model,
            message="Ollama está desactivado por configuración.",
        )
    elif injected is not None:
        health_info = injected.health()
        ollama = OllamaStatus(
            available=health_info.available,
            model=health_info.model,
            message=health_info.message,
        )
    else:
        with OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            health_timeout=settings.ollama_health_timeout,
        ) as client:
            health_info = client.health()
        ollama = OllamaStatus(
            available=health_info.available,
            model=health_info.model,
            message=health_info.message,
        )

    status = (
        "ok"
        if database == "ok" and (not settings.llm_enabled or ollama.available)
        else "degraded"
    )
    return HealthResponse(
        status=status,
        version=__version__,
        database=database,  # type: ignore[arg-type]
        ollama=ollama,
    )


@router.get("/config", response_model=ConfigResponse)
def config(request: Request) -> ConfigResponse:
    settings = request.app.state.settings
    storage: Storage = request.app.state.storage

    return ConfigResponse(
        max_clips=settings.max_clips,
        max_input_bytes=settings.max_input_bytes,
        platforms=list(SUPPORTED_PLATFORMS),
        llm_enabled=settings.llm_enabled,
        flags=storage.active_flags(),
        whisper_models=list(SUPPORTED_MODELS),
        whisper_model=settings.whisper_model,
        whisper_device=detect_device(settings.whisper_device),
        whisper_language=settings.whisper_language,
        upload_max_bytes=settings.upload_max_bytes,
        ffmpeg_available=ffmpeg_available(settings.ffmpeg_path),
        ffprobe_available=ffprobe_available(settings.ffprobe_path),
        render_width=settings.render_width,
        render_height=settings.render_height,
        render_fps=settings.render_fps,
        render_crf=settings.render_crf,
        render_preset=settings.render_preset,
        render_zoom=settings.render_zoom,
        render_font=settings.render_font,
        render_font_size=settings.render_font_size,
    )


# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------


@router.post("/analyses", status_code=202, response_model=JobAccepted)
def create_analysis(
    payload: AnalysisRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> JobAccepted:
    settings = request.app.state.settings
    storage: Storage = request.app.state.storage

    if payload.max_clips > settings.max_clips:
        raise InvalidParameterError(
            f"max_clips no puede superar el límite configurado ({settings.max_clips})"
        )

    raw_size = len(
        json.dumps(payload.transcript, ensure_ascii=False).encode("utf-8")
    )
    if raw_size > settings.max_input_bytes:
        raise PayloadTooLargeError(
            f"La transcripción supera el límite de {settings.max_input_bytes} bytes"
        )

    transcript = normalize_transcript(
        payload.transcript,
        max_segments=settings.max_segments,
        max_bytes=settings.max_input_bytes,
    )

    job_id = str(uuid4())
    request_id = getattr(request.state, "request_id", None)
    storage.create_job(
        job_id=job_id,
        transcript_json=transcript.model_dump_json(),
        platform=payload.platform,
        max_clips=payload.max_clips,
        min_duration=payload.min_duration,
        max_duration=payload.max_duration,
        use_llm=payload.use_llm,
        request_id=request_id,
    )
    storage.audit(
        action="analysis.create",
        resource="analysis",
        resource_id=job_id,
        request_id=request_id,
        detail=f"platform={payload.platform}; use_llm={payload.use_llm}",
    )

    background_tasks.add_task(
        run_analysis_job,
        storage=storage,
        settings=settings,
        job_id=job_id,
        ollama_client=request.app.state.ollama_client,
    )

    return JobAccepted(
        id=job_id,
        status="queued",
        events_url=f"/api/analyses/{job_id}/events",
    )


@router.get("/analyses", response_model=AnalysisListResponse)
def list_analyses(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AnalysisListResponse:
    storage: Storage = request.app.state.storage
    jobs, total = storage.list_jobs(limit=limit, offset=offset)

    return AnalysisListResponse(
        items=[
            _job_response(job, storage, include_clips=False) for job in jobs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str, request: Request) -> AnalysisResponse:
    storage: Storage = request.app.state.storage
    job = _get_job(storage, analysis_id)
    return _job_response(job, storage, include_clips=True)


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, request: Request) -> Response:
    storage: Storage = request.app.state.storage
    job = _get_job(storage, analysis_id)
    storage.delete_job(job.id)
    storage.audit(
        action="analysis.delete",
        resource="analysis",
        resource_id=job.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=204)


@router.get("/analyses/{analysis_id}/events")
def analysis_events(
    analysis_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream SSE con snapshot, ids, heartbeats y reconexión.

    Emite el estado actual al conectar y luego cada cambio de estado, progreso o
    etapa. En reconexión continúa la numeración desde ``Last-Event-ID``.
    """

    storage: Storage = request.app.state.storage
    job = _get_job(storage, analysis_id)

    try:
        start_id = int(last_event_id) + 1 if last_event_id else 1
    except (TypeError, ValueError):
        start_id = 1
    if start_id < 1:
        start_id = 1

    async def event_stream():
        current = job
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
                data = {
                    "id": current.id,
                    "status": current.status,
                    "progress": current.progress,
                    "stage": current.stage,
                    "updated_at": current.updated_at,
                }
                yield _format_sse(event, data, event_id)
                event_id += 1
                signature = current_signature
                last_emit = time.monotonic()

            if current.is_terminal:
                break

            if time.monotonic() - started >= SSE_MAX_SECONDS:
                break

            await asyncio.sleep(SSE_POLL_SECONDS)
            refreshed = storage.get_job(analysis_id)
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


@router.get("/analyses/{analysis_id}/export")
def export_analysis(
    analysis_id: str,
    request: Request,
    format: ExportFormat = "json",
):
    storage: Storage = request.app.state.storage
    job = _get_job(storage, analysis_id)
    result = storage.result_for(job)
    if result is None:
        raise AnalysisNotReadyError(
            "El análisis todavía no terminó; consulta su estado antes de exportar"
        )

    if format in {"srt", "vtt"} and not _flag_enabled(storage, "export_srt"):
        raise FeatureDisabledError(
            "La exportación SRT/VTT está desactivada por el flag export_srt"
        )

    if format == "json":
        return JSONResponse(content=json.loads(result.model_dump_json()))
    if format == "spec":
        return JSONResponse(content=result.to_spec())

    lines = _combined_subtitles(result)
    if format == "srt":
        return PlainTextResponse(
            to_srt(lines),
            media_type="application/x-subrip",
            headers=_attachment(f"analisis-{job.id}.srt"),
        )
    return PlainTextResponse(
        to_vtt(lines),
        media_type="text/vtt",
        headers=_attachment(f"analisis-{job.id}.vtt"),
    )


@router.get("/analyses/{analysis_id}/clips/{clip_id}/srt")
def export_clip_srt(analysis_id: str, clip_id: str, request: Request):
    storage: Storage = request.app.state.storage
    job = _get_job(storage, analysis_id)
    result = storage.result_for(job)
    if result is None:
        raise AnalysisNotReadyError("El análisis todavía no terminó")

    if not _flag_enabled(storage, "export_srt"):
        raise FeatureDisabledError(
            "La exportación SRT está desactivada por el flag export_srt"
        )

    clip = next((item for item in result.clips if item.id == clip_id), None)
    if clip is None:
        raise AnalysisNotFoundError(f"No existe el clip {clip_id}")

    return PlainTextResponse(
        to_srt(clip.subtitles),
        media_type="application/x-subrip",
        headers=_attachment(f"{clip.id}.srt"),
    )


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------


@router.get("/flags", response_model=list[FeatureFlag])
def list_flags(request: Request) -> list[FeatureFlag]:
    storage: Storage = request.app.state.storage
    return [FeatureFlag(**flag) for flag in storage.list_flags()]


@router.patch("/flags", response_model=FeatureFlag)
def update_flag(payload: FeatureFlagUpdate, request: Request) -> FeatureFlag:
    storage: Storage = request.app.state.storage
    flag = storage.set_flag(payload.name, payload.enabled)
    storage.audit(
        action="flag.update",
        resource="feature_flag",
        resource_id=payload.name,
        request_id=getattr(request.state, "request_id", None),
        detail=f"enabled={payload.enabled}",
    )
    return FeatureFlag(**flag)
