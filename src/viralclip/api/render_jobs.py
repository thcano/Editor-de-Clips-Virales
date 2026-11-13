"""Ejecución de renderizados en segundo plano."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from ..config import Settings
from ..errors import ErrorCode, ViralClipError
from ..models import Clip
from ..render import FFmpegRenderer
from ..storage import Storage

logger = logging.getLogger("viralclip.render.jobs")

RendererFactory = Callable[[Settings], object]

# FFmpeg satura la CPU; serializar mantiene el equipo usable y el progreso predecible.
_RENDER_LOCK = threading.Lock()


def build_renderer(settings: Settings) -> FFmpegRenderer:
    """Crea el renderizador real a partir de los ajustes."""

    return FFmpegRenderer(settings)


def run_render_job(
    *,
    storage: Storage,
    settings: Settings,
    render_id: str,
    clip: Clip,
    renderer_factory: RendererFactory | None = None,
) -> None:
    """Ejecuta un render ya persistido y guarda el resultado o el error."""

    record = storage.get_render(render_id)
    if record is None:
        logger.warning("Render inexistente: %s", render_id)
        return

    storage.mark_render_running(render_id)
    try:
        factory = renderer_factory or build_renderer
        renderer = factory(settings)

        def on_progress(progress: int, stage: str) -> None:
            storage.update_render_progress(render_id, progress, stage)

        with _RENDER_LOCK:
            result = renderer.render(
                source_path=record.source_path,
                clip=clip,
                render_id=render_id,
                job_id=record.job_id,
                progress=on_progress,
            )
        storage.complete_render(
            render_id,
            output_path=str(result.output_path),
            thumbnail_path=(
                str(result.thumbnail_path)
                if result.thumbnail_path is not None
                else None
            ),
            width=result.width,
            height=result.height,
            duration=result.duration,
            size_bytes=result.size_bytes,
        )
    except ViralClipError as exc:
        storage.fail_render(render_id, exc.code.value, exc.message)
    except Exception:
        logger.exception("Fallo inesperado en el render %s", render_id)
        storage.fail_render(
            render_id,
            ErrorCode.RENDER_FAILED.value,
            "Error interno durante el renderizado",
        )
