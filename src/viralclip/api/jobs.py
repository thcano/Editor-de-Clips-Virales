"""Ejecución de trabajos de análisis en segundo plano."""

from __future__ import annotations

import logging

from ..config import Settings
from ..errors import ErrorCode, ViralClipError
from ..llm.ollama import OllamaClient
from ..models import Transcript
from ..pipeline import analyze
from ..storage import Storage

logger = logging.getLogger("viralclip.jobs")


def run_analysis_job(
    *,
    storage: Storage,
    settings: Settings,
    job_id: str,
    ollama_client: OllamaClient | None = None,
) -> None:
    """Ejecuta un trabajo ya persistido y guarda el resultado o el error."""

    job = storage.get_job(job_id)
    if job is None:
        logger.warning("Trabajo inexistente: %s", job_id)
        return

    storage.mark_running(job_id)
    try:
        transcript = Transcript.model_validate_json(job.transcript_json)

        def on_stage(progress: int, stage: str) -> None:
            storage.update_progress(job_id, progress, stage)

        result = analyze(
            transcript,
            platform=job.platform,
            max_clips=job.max_clips,
            min_duration=job.min_duration,
            max_duration=job.max_duration,
            use_llm=job.use_llm,
            ollama_client=ollama_client,
            settings=settings,
            on_stage=on_stage,
        )
        storage.complete_job(job_id, result)
    except ViralClipError as exc:
        storage.fail_job(job_id, exc.code.value, exc.message)
    except Exception:
        logger.exception("Fallo inesperado en el trabajo %s", job_id)
        storage.fail_job(
            job_id,
            ErrorCode.INTERNAL.value,
            "Error interno durante el análisis",
        )
