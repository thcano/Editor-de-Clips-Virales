"""Modelos Pydantic de entrada, salida y API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .timeutils import MAX_SECONDS


class Word(BaseModel):
    """Palabra con marcas de tiempo."""

    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1, max_length=100)
    start: float = Field(ge=0, le=MAX_SECONDS)
    end: float = Field(ge=0, le=MAX_SECONDS)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _check_range(self) -> Word:
        if self.end <= self.start:
            raise ValueError("end debe ser mayor que start")
        return self


class Segment(BaseModel):
    """Fragmento de transcripción con texto y palabras opcionales."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0, le=MAX_SECONDS)
    end: float = Field(ge=0, le=MAX_SECONDS)
    text: str = Field(min_length=1, max_length=5000)
    words: list[Word] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def _check_segment(self) -> Segment:
        if self.end <= self.start:
            raise ValueError("end debe ser mayor que start")
        if not self.text.strip():
            raise ValueError("text no puede estar vacío")

        previous_end: float | None = None
        for word in self.words:
            if word.start < self.start - 0.5 or word.end > self.end + 0.5:
                raise ValueError(
                    f"la palabra {word.word!r} queda fuera del segmento "
                    f"[{self.start}, {self.end}]"
                )
            if previous_end is not None and word.start < previous_end - 0.5:
                raise ValueError("las palabras deben estar ordenadas por start")
            previous_end = word.end
        return self


class Transcript(BaseModel):
    """Transcripción normalizada, lista para el motor de análisis."""

    model_config = ConfigDict(extra="forbid")

    language: str = Field(default="es", max_length=10)
    duration: float = Field(gt=0, le=MAX_SECONDS)
    segments: list[Segment] = Field(min_length=1, max_length=20_000)
    source_format: str = Field(default="document", max_length=20)

    @model_validator(mode="after")
    def _check_transcript(self) -> Transcript:
        previous_start = -1.0
        for segment in self.segments:
            if segment.start < previous_start:
                raise ValueError("los segmentos deben estar ordenados por start")
            previous_start = segment.start
        if self.duration + 0.5 < self.segments[-1].end:
            raise ValueError("duration no puede ser menor que el último end")
        return self


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------


class SubtitleWord(BaseModel):
    """Palabra dentro de una línea de subtítulo."""

    model_config = ConfigDict(extra="forbid")

    word: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    highlight: bool = False


class SubtitleLine(BaseModel):
    """Línea de subtítulo dinámico (máximo 5 palabras por regla de producto)."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    words: list[SubtitleWord] = Field(default_factory=list)


class EngineInfo(BaseModel):
    """Motor que produjo el análisis."""

    model_config = ConfigDict(extra="forbid")

    name: Literal["heuristic", "heuristic+ollama"] = "heuristic"
    model: str | None = None
    degraded: bool = True
    notes: str | None = None


class SourceInfo(BaseModel):
    """Metadatos de la transcripción de origen."""

    model_config = ConfigDict(extra="forbid")

    language: str
    duration: float = Field(ge=0)
    segment_count: int = Field(ge=1)


class Clip(BaseModel):
    """Clip candidato con gancho, subtítulos y metadatos."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^clip_\d{3,}$")
    rank: int = Field(ge=1)
    start_time: str = Field(pattern=r"^(\d{1,2}:)?\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^(\d{1,2}:)?\d{2}:\d{2}$")
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)
    platform: Literal["tiktok", "reels", "shorts"]
    hook: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    caption_text: str = Field(min_length=1)
    hashtags: list[str] = Field(default_factory=list, max_length=12)
    score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)
    keywords: list[str] = Field(default_factory=list)
    subtitles: list[SubtitleLine] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_clip(self) -> Clip:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds debe ser mayor que start_seconds")
        expected = self.end_seconds - self.start_seconds
        if abs(expected - self.duration_seconds) > 0.5:
            raise ValueError("duration_seconds no coincide con el rango del clip")
        if len(self.hook.split()) > 10:
            raise ValueError("el gancho no puede superar 10 palabras")
        if len(set(self.hashtags)) != len(self.hashtags):
            raise ValueError("los hashtags no pueden repetirse")
        return self


class AnalysisResult(BaseModel):
    """Resultado enriquecido del análisis (contrato v1.0)."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["1.0"] = "1.0"
    generated_at: datetime
    source: SourceInfo
    engine: EngineInfo
    clips: list[Clip] = Field(default_factory=list)

    def to_spec(self) -> list[dict[str, Any]]:
        """Devuelve el formato mínimo pedido en ``SKILLS.md``."""

        return [
            {
                "start_time": clip.start_time,
                "end_time": clip.end_time,
                "hook": clip.hook,
                "caption_text": clip.caption_text,
                "hashtags": list(clip.hashtags),
            }
            for clip in self.clips
        ]


class SpecClip(BaseModel):
    """Formato de salida mínimo de la especificación."""

    model_config = ConfigDict(extra="forbid")

    start_time: str
    end_time: str
    hook: str
    caption_text: str
    hashtags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class AnalysisRequest(BaseModel):
    """Petición de análisis desde la API."""

    model_config = ConfigDict(extra="forbid")

    transcript: Any
    platform: Literal["tiktok", "reels", "shorts"] = "tiktok"
    max_clips: int = Field(default=5, ge=1, le=20)
    use_llm: bool = True
    min_duration: float = Field(default=15.0, ge=5.0, le=180.0)
    max_duration: float = Field(default=60.0, ge=10.0, le=180.0)

    @model_validator(mode="after")
    def _check_durations(self) -> AnalysisRequest:
        if self.max_duration <= self.min_duration:
            raise ValueError("max_duration debe ser mayor que min_duration")
        return self


class FeatureFlag(BaseModel):
    """Feature flag local con dueño y expiración."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    enabled: bool
    owner: str | None = None
    expires_at: datetime | None = None
    description: str | None = None
