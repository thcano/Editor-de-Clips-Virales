"""Pipeline de extremo a extremo: Transcript → AnalysisResult."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from .analyzer import ClipCandidate, analyze_transcript
from .config import Settings
from .errors import OllamaUnavailableError
from .hooks import generate_hook, is_valid_hook
from .llm.ollama import (
    DEFAULT_BASE_URL,
    DEFAULT_HEALTH_TIMEOUT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    OllamaClient,
)
from .llm.prompts import SYSTEM_PROMPT, build_hook_prompt, parse_hook_response
from .models import AnalysisResult, Clip, EngineInfo, SourceInfo, Transcript
from .platforms import build_metadata
from .subtitles import build_subtitles

HEURISTIC_NOTES = "Análisis heurístico local; LLM desactivado explícitamente."

StageCallback = Callable[[int, str], None]


def build_clip(
    candidate: ClipCandidate,
    transcript: Transcript,
    platform: str = "tiktok",
    rank: int = 1,
    hook: str | None = None,
) -> Clip:
    """Convierte un candidato en un ``Clip`` completo.

    ``hook`` permite inyectar un gancho ya validado (por ejemplo, el del LLM).
    Si falta o no cumple las reglas, se genera el heurístico.
    """

    chosen_hook = hook if hook and is_valid_hook(hook) else generate_hook(
        candidate.text, candidate.keywords, platform
    )
    subtitles = build_subtitles(
        transcript, candidate, highlight_keywords=candidate.keywords
    )
    metadata = build_metadata(candidate, chosen_hook, platform)

    return Clip(
        id=f"clip_{rank:03d}",
        rank=rank,
        start_time=candidate.start_time,
        end_time=candidate.end_time,
        start_seconds=candidate.start_seconds,
        end_seconds=candidate.end_seconds,
        duration_seconds=candidate.duration,
        platform=platform,
        hook=chosen_hook,
        title=metadata.title,
        description=metadata.description,
        caption_text=candidate.text,
        hashtags=metadata.hashtags,
        score=candidate.score,
        reason=candidate.reason,
        keywords=list(candidate.keywords),
        subtitles=subtitles,
    )


def _request_llm_hooks(
    candidates: list[ClipCandidate],
    client: OllamaClient,
    platform: str,
) -> tuple[list[str | None], int]:
    """Pide un gancho por candidato; devuelve ganchos válidos y cuántos hubo."""

    hooks: list[str | None] = []
    used = 0

    for candidate in candidates:
        prompt = build_hook_prompt(candidate.text, candidate.keywords, platform)
        try:
            raw = client.generate(prompt, system=SYSTEM_PROMPT)
        except OllamaUnavailableError:
            hooks.append(None)
            continue

        hook = parse_hook_response(raw)
        if hook:
            used += 1
        hooks.append(hook)

    return hooks, used


def _resolve_engine(
    candidates: list[ClipCandidate],
    *,
    platform: str,
    use_llm: bool,
    settings: Settings | None,
    ollama_client: OllamaClient | None,
) -> tuple[EngineInfo, list[str | None]]:
    """Decide el motor y los ganchos, aplicando degradación explícita."""

    hooks: list[str | None] = [None] * len(candidates)

    if not use_llm:
        return (
            EngineInfo(
                name="heuristic",
                model=None,
                degraded=False,
                notes=HEURISTIC_NOTES,
            ),
            hooks,
        )

    if settings is not None and not settings.llm_enabled:
        return (
            EngineInfo(
                name="heuristic",
                model=None,
                degraded=False,
                notes=(
                    "Ollama está desactivado por configuración "
                    "(VIRALCLIP_LLM_ENABLED=false)."
                ),
            ),
            hooks,
        )

    owns_client = ollama_client is None
    client = ollama_client
    if client is None:
        client = OllamaClient(
            base_url=settings.ollama_base_url if settings else DEFAULT_BASE_URL,
            model=settings.ollama_model if settings else DEFAULT_MODEL,
            timeout=settings.ollama_timeout if settings else DEFAULT_TIMEOUT,
            health_timeout=(
                settings.ollama_health_timeout
                if settings
                else DEFAULT_HEALTH_TIMEOUT
            ),
            failure_threshold=(
                settings.ollama_circuit_failures if settings else 3
            ),
            cooldown_seconds=(
                settings.ollama_circuit_cooldown if settings else 60.0
            ),
        )

    try:
        health = client.health()
        if not health.available:
            return (
                EngineInfo(
                    name="heuristic",
                    model=None,
                    degraded=True,
                    notes=health.message or "Ollama no está disponible.",
                ),
                hooks,
            )

        llm_hooks, used = _request_llm_hooks(candidates, client, platform)
        if used:
            return (
                EngineInfo(
                    name="heuristic+ollama",
                    model=health.model or client.model,
                    degraded=False,
                    notes=(
                        f"{used} de {len(candidates)} ganchos refinados con Ollama."
                    ),
                ),
                llm_hooks,
            )

        return (
            EngineInfo(
                name="heuristic",
                model=None,
                degraded=True,
                notes=(
                    "Ollama respondió, pero ningún gancho superó la validación; "
                    "se usó el motor heurístico."
                ),
            ),
            hooks,
        )
    finally:
        if owns_client:
            client.close()


def analyze(
    transcript: Transcript,
    *,
    platform: str = "tiktok",
    max_clips: int = 5,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    use_llm: bool = False,
    ollama_client: OllamaClient | None = None,
    settings: Settings | None = None,
    generated_at: datetime | None = None,
    on_stage: StageCallback | None = None,
) -> AnalysisResult:
    """Ejecuta el pipeline completo y devuelve el contrato ``v1.0``.

    ``use_llm=False`` es una decisión explícita de usar solo heurísticas, por lo
    que el resultado no se marca como degradado. Si se solicita el LLM y Ollama
    falla, se devuelve el resultado heurístico con ``degraded=True``.

    ``on_stage`` permite reportar avance (0–100) y una etapa legible sin acoplar
    el dominio a la persistencia.
    """

    def report(progress: int, stage: str) -> None:
        if on_stage is not None:
            on_stage(progress, stage)

    report(10, "preparando")
    candidates = analyze_transcript(
        transcript,
        min_duration=min_duration,
        max_duration=max_duration,
        max_clips=max_clips,
    )
    report(40, "candidatos")

    report(55, "ganchos")
    engine, hooks = _resolve_engine(
        candidates,
        platform=platform,
        use_llm=use_llm,
        settings=settings,
        ollama_client=ollama_client,
    )
    report(75, "ganchos")

    clips = [
        build_clip(
            candidate,
            transcript,
            platform=platform,
            rank=rank,
            hook=hooks[rank - 1] if rank - 1 < len(hooks) else None,
        )
        for rank, candidate in enumerate(candidates, start=1)
    ]
    report(90, "clips")

    return AnalysisResult(
        generated_at=generated_at or datetime.now(UTC),
        source=SourceInfo(
            language=transcript.language,
            duration=transcript.duration,
            segment_count=len(transcript.segments),
        ),
        engine=engine,
        clips=clips,
    )
