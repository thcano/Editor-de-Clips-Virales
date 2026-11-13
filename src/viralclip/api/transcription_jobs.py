"""Ejecución de trabajos de transcripción en segundo plano."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from ..config import Settings
from ..errors import ErrorCode, ViralClipError
from ..storage import Storage, TranscriptionRecord
from ..transcription import WhisperTranscriber

logger = logging.getLogger("viralclip.transcription.jobs")

TranscriberFactory = Callable[[TranscriptionRecord, Settings], object]

# Whisper en CPU usa todos los hilos; serializar evita competir por RAM y CPU.
_TRANSCRIBE_LOCK = threading.Lock()


def build_transcriber(
    record: TranscriptionRecord, settings: Settings
) -> WhisperTranscriber:
    """Crea el transcriptor real a partir del registro y los ajustes."""

    return WhisperTranscriber(
        model_size=record.model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        language=record.language or settings.whisper_language,
        model_dir=settings.whisper_model_dir,
        ffmpeg_path=settings.ffmpeg_path,
        beam_size=settings.whisper_beam_size,
        vad=settings.whisper_vad,
        max_segments=settings.max_segments,
    )


def run_transcription_job(
    *,
    storage: Storage,
    settings: Settings,
    transcription_id: str,
    transcriber_factory: TranscriberFactory | None = None,
) -> None:
    """Ejecuta una transcripción ya persistida y guarda el resultado o el error."""

    record = storage.get_transcription(transcription_id)
    if record is None:
        logger.warning("Transcripción inexistente: %s", transcription_id)
        return

    storage.mark_transcription_running(transcription_id)
    try:
        factory = transcriber_factory or build_transcriber
        transcriber = factory(record, settings)

        def on_stage(progress: int, stage: str) -> None:
            storage.update_transcription_progress(transcription_id, progress, stage)

        with _TRANSCRIBE_LOCK:
            transcript = transcriber.transcribe(
                record.source_path,
                language=record.language,
                on_stage=on_stage,
            )
        storage.complete_transcription(
            transcription_id,
            transcript,
            language=transcript.language,
            duration=transcript.duration,
        )
    except ViralClipError as exc:
        storage.fail_transcription(transcription_id, exc.code.value, exc.message)
    except Exception:
        logger.exception("Fallo inesperado en la transcripción %s", transcription_id)
        storage.fail_transcription(
            transcription_id,
            ErrorCode.TRANSCRIPTION_FAILED.value,
            "Error interno durante la transcripción",
        )
