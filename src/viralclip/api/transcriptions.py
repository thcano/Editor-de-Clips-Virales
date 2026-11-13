"""Rutas HTTP para transcribir video/audio localmente."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse

from ..config import Settings
from ..errors import (
    AnalysisNotReadyError,
    InvalidMediaError,
    InvalidParameterError,
    MediaTooLargeError,
    TranscriptionNotFoundError,
)
from ..storage import Storage, TranscriptionRecord
from ..transcription import (
    SUPPORTED_EXTENSIONS,
    detect_device,
    normalize_language,
    normalize_model,
    validate_media,
)
from .jobs import run_analysis_job
from .schemas import (
    ErrorPayload,
    JobAccepted,
    TranscriptionAccepted,
    TranscriptionAnalyzeRequest,
    TranscriptionListResponse,
    TranscriptionPathRequest,
    TranscriptionResponse,
)
from .security import require_api_key
from .transcription_jobs import TranscriberFactory, run_transcription_job

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

SSE_HEARTBEAT_SECONDS = 15.0
SSE_MAX_SECONDS = 3600.0
SSE_POLL_SECONDS = 0.5
UPLOAD_CHUNK_BYTES = 1024 * 1024


def _get_transcription(
    storage: Storage, transcription_id: str
) -> TranscriptionRecord:
    record = storage.get_transcription(transcription_id)
    if record is None:
        raise TranscriptionNotFoundError(
            f"No existe la transcripción {transcription_id}"
        )
    return record


def _transcription_response(
    record: TranscriptionRecord,
    storage: Storage,
    *,
    include_transcript: bool,
) -> TranscriptionResponse:
    error = None
    if record.error_code:
        error = ErrorPayload(
            code=record.error_code,
            message=record.error_message or "Error durante la transcripción",
        )
    return TranscriptionResponse(
        id=record.id,
        status=record.status,  # type: ignore[arg-type]
        created_at=record.created_at,
        updated_at=record.updated_at,
        progress=record.progress,
        stage=record.stage,
        filename=record.filename,
        model=record.model,
        device=record.device,
        language=record.language,
        duration=record.duration,
        error=error,
        transcript=storage.transcript_for(record) if include_transcript else None,
    )


def _validate_options(
    settings: Settings, model: str, language: str
) -> tuple[str, str, str]:
    normalized_model = normalize_model(model)
    normalized_language = normalize_language(language)
    device = detect_device(settings.whisper_device)
    return normalized_model, normalized_language, device


def _enqueue(
    *,
    storage: Storage,
    settings: Settings,
    request: Request,
    background_tasks: BackgroundTasks,
    transcription_id: str,
    source_path: str,
    filename: str,
    model: str,
    language: str,
    device: str,
) -> TranscriptionAccepted:
    request_id = getattr(request.state, "request_id", None)
    storage.create_transcription(
        transcription_id=transcription_id,
        source_path=source_path,
        filename=filename,
        model=model,
        device=device,
        language=language,
        request_id=request_id,
    )
    storage.audit(
        action="transcription.create",
        resource="transcription",
        resource_id=transcription_id,
        request_id=request_id,
        detail=f"model={model}; language={language}; source={source_path}",
    )
    factory: TranscriberFactory | None = request.app.state.transcriber_factory
    background_tasks.add_task(
        run_transcription_job,
        storage=storage,
        settings=settings,
        transcription_id=transcription_id,
        transcriber_factory=factory,
    )
    return TranscriptionAccepted(
        id=transcription_id,
        status="queued",
        events_url=f"/api/transcriptions/{transcription_id}/events",
    )


def _format_sse(event: str, data: dict[str, Any], event_id: int) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event_id}\nevent: {event}\ndata: {payload}\n\n"


# ---------------------------------------------------------------------------
# Crear transcripciones
# ---------------------------------------------------------------------------


@router.post(
    "/transcriptions/upload",
    status_code=202,
    response_model=TranscriptionAccepted,
)
async def upload_transcription(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    model: Annotated[str, Form()] = "small",
    language: Annotated[str, Form()] = "auto",
) -> TranscriptionAccepted:
    """Recibe un video/audio por multipart y lo transcribe en segundo plano."""

    settings: Settings = request.app.state.settings
    storage: Storage = request.app.state.storage
    normalized_model, normalized_language, device = _validate_options(
        settings, model, language
    )

    original = Path(file.filename or "video").name
    suffix = Path(original).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise InvalidMediaError(
            f"Formato no soportado: {suffix or '(sin extensión)'}. "
            f"Formatos: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    transcription_id = str(uuid4())
    upload_dir = settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / f"{transcription_id}{suffix}"

    size = 0
    too_large = False
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > settings.upload_max_bytes:
                    too_large = True
                    break
                output.write(chunk)
    finally:
        await file.close()

    if too_large:
        destination.unlink(missing_ok=True)
        raise MediaTooLargeError(
            f"El video supera el límite de {settings.upload_max_bytes} bytes"
        )
    if size == 0:
        destination.unlink(missing_ok=True)
        raise InvalidMediaError("El archivo subido está vacío")

    return _enqueue(
        storage=storage,
        settings=settings,
        request=request,
        background_tasks=background_tasks,
        transcription_id=transcription_id,
        source_path=str(destination),
        filename=original,
        model=normalized_model,
        language=normalized_language,
        device=device,
    )


@router.post(
    "/transcriptions",
    status_code=202,
    response_model=TranscriptionAccepted,
)
def create_transcription_from_path(
    payload: TranscriptionPathRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> TranscriptionAccepted:
    """Transcribe un video/audio que ya existe en el equipo."""

    settings: Settings = request.app.state.settings
    storage: Storage = request.app.state.storage
    normalized_model, normalized_language, device = _validate_options(
        settings, payload.model, payload.language
    )
    media = validate_media(payload.path, max_bytes=settings.upload_max_bytes)

    return _enqueue(
        storage=storage,
        settings=settings,
        request=request,
        background_tasks=background_tasks,
        transcription_id=str(uuid4()),
        source_path=str(media.resolve()),
        filename=media.name,
        model=normalized_model,
        language=normalized_language,
        device=device,
    )


# ---------------------------------------------------------------------------
# Consultar y borrar
# ---------------------------------------------------------------------------


@router.get("/transcriptions", response_model=TranscriptionListResponse)
def list_transcriptions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TranscriptionListResponse:
    storage: Storage = request.app.state.storage
    records, total = storage.list_transcriptions(limit=limit, offset=offset)
    return TranscriptionListResponse(
        items=[
            _transcription_response(record, storage, include_transcript=False)
            for record in records
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/transcriptions/{transcription_id}",
    response_model=TranscriptionResponse,
)
def get_transcription(
    transcription_id: str, request: Request
) -> TranscriptionResponse:
    storage: Storage = request.app.state.storage
    record = _get_transcription(storage, transcription_id)
    return _transcription_response(record, storage, include_transcript=True)


@router.delete("/transcriptions/{transcription_id}", status_code=204)
def delete_transcription(transcription_id: str, request: Request) -> Response:
    settings: Settings = request.app.state.settings
    storage: Storage = request.app.state.storage
    record = _get_transcription(storage, transcription_id)
    storage.delete_transcription(record.id)

    source = Path(record.source_path)
    try:
        inside_uploads = source.resolve().is_relative_to(
            settings.upload_dir.resolve()
        )
    except (OSError, ValueError):
        inside_uploads = False
    if inside_uploads:
        source.unlink(missing_ok=True)

    storage.audit(
        action="transcription.delete",
        resource="transcription",
        resource_id=record.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=204)


@router.get("/transcriptions/{transcription_id}/events")
def transcription_events(
    transcription_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """SSE con el progreso de la transcripción y reconexión por ``Last-Event-ID``."""

    storage: Storage = request.app.state.storage
    record = _get_transcription(storage, transcription_id)

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
            refreshed = storage.get_transcription(transcription_id)
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


# ---------------------------------------------------------------------------
# Analizar la transcripción
# ---------------------------------------------------------------------------


@router.post(
    "/transcriptions/{transcription_id}/analyze",
    status_code=202,
    response_model=JobAccepted,
)
def analyze_transcription(
    transcription_id: str,
    payload: TranscriptionAnalyzeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> JobAccepted:
    """Crea un análisis de clips usando una transcripción ya terminada."""

    settings: Settings = request.app.state.settings
    storage: Storage = request.app.state.storage
    record = _get_transcription(storage, transcription_id)

    if record.status != "done" or not record.transcript_json:
        raise AnalysisNotReadyError(
            "La transcripción todavía no terminó; consulta su estado antes de analizar"
        )
    if payload.max_clips > settings.max_clips:
        raise InvalidParameterError(
            f"max_clips no puede superar el límite configurado ({settings.max_clips})"
        )

    job_id = str(uuid4())
    request_id = getattr(request.state, "request_id", None)
    storage.create_job(
        job_id=job_id,
        transcript_json=record.transcript_json,
        platform=payload.platform,
        max_clips=payload.max_clips,
        min_duration=payload.min_duration,
        max_duration=payload.max_duration,
        use_llm=payload.use_llm,
        request_id=request_id,
        source_path=record.source_path,
        transcription_id=record.id,
    )
    storage.audit(
        action="transcription.analyze",
        resource="analysis",
        resource_id=job_id,
        request_id=request_id,
        detail=f"transcription={record.id}; platform={payload.platform}",
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


__all__ = ["router"]
