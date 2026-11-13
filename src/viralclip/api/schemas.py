"""Esquemas HTTP de la API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..models import Clip, EngineInfo, Transcript

JobStatus = Literal["queued", "running", "done", "error"]
ExportFormat = Literal["json", "spec", "srt", "vtt"]


class ErrorPayload(BaseModel):
    """Cuerpo de error estable de la API."""

    code: str
    message: str
    detail: str | None = None
    request_id: str | None = None


class OllamaStatus(BaseModel):
    available: bool
    model: str
    message: str = ""


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ok", "error"]
    ollama: OllamaStatus


class ConfigResponse(BaseModel):
    max_clips: int
    max_input_bytes: int
    platforms: list[str]
    llm_enabled: bool
    flags: list[str]
    whisper_models: list[str]
    whisper_model: str
    whisper_device: str
    whisper_language: str
    upload_max_bytes: int
    ffmpeg_available: bool
    ffprobe_available: bool = False
    render_width: int = 1080
    render_height: int = 1920
    render_fps: int = 30
    render_crf: int = 20
    render_preset: str = "veryfast"
    render_zoom: float = 0.06
    render_font: str = "Arial"
    render_font_size: int = 54


class JobAccepted(BaseModel):
    id: str
    status: Literal["queued", "running"]
    events_url: str


class AnalysisResponse(BaseModel):
    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    platform: Literal["tiktok", "reels", "shorts"]
    progress: int = Field(ge=0, le=100)
    stage: str | None = None
    source_path: str | None = None
    engine: EngineInfo | None = None
    error: ErrorPayload | None = None
    clips: list[Clip] = Field(default_factory=list)


class AnalysisListResponse(BaseModel):
    items: list[AnalysisResponse]
    total: int
    limit: int
    offset: int


class FeatureFlagUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    enabled: bool


TranscriptionStatus = Literal["queued", "running", "done", "error"]


class TranscriptionPathRequest(BaseModel):
    """Transcripción a partir de una ruta local."""

    model_config = {"extra": "forbid"}

    path: str = Field(min_length=1, max_length=4096)
    model: str = Field(default="small", max_length=32)
    language: str = Field(default="auto", max_length=16)


class TranscriptionAccepted(BaseModel):
    id: str
    status: Literal["queued", "running"]
    events_url: str


class TranscriptionResponse(BaseModel):
    id: str
    status: TranscriptionStatus
    created_at: datetime
    updated_at: datetime
    progress: int = Field(ge=0, le=100)
    stage: str | None = None
    filename: str
    model: str
    device: str
    language: str | None = None
    duration: float | None = None
    error: ErrorPayload | None = None
    transcript: Transcript | None = None


class TranscriptionListResponse(BaseModel):
    items: list[TranscriptionResponse]
    total: int
    limit: int
    offset: int


class TranscriptionAnalyzeRequest(BaseModel):
    """Parámetros para analizar una transcripción ya guardada."""

    model_config = {"extra": "forbid"}

    platform: Literal["tiktok", "reels", "shorts"] = "tiktok"
    max_clips: int = Field(default=5, ge=1, le=20)
    use_llm: bool = True
    min_duration: float = Field(default=15.0, ge=5.0, le=180.0)
    max_duration: float = Field(default=60.0, ge=10.0, le=180.0)

    @model_validator(mode="after")
    def _check_durations(self) -> TranscriptionAnalyzeRequest:
        if self.max_duration <= self.min_duration:
            raise ValueError("max_duration debe ser mayor que min_duration")
        return self


RenderStatus = Literal["queued", "running", "done", "error"]


class RenderRequest(BaseModel):
    """Solicitud de renderizado de un clip."""

    model_config = {"extra": "forbid"}

    video_path: str | None = Field(default=None, max_length=4096)
    force: bool = False


class RenderAccepted(BaseModel):
    id: str
    status: Literal["queued", "running"]
    events_url: str


class RenderResponse(BaseModel):
    id: str
    job_id: str
    clip_id: str
    transcription_id: str | None = None
    status: RenderStatus
    created_at: datetime
    updated_at: datetime
    progress: int = Field(ge=0, le=100)
    stage: str | None = None
    source_path: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    size_bytes: int | None = None
    error: ErrorPayload | None = None
    events_url: str
    download_url: str | None = None
    thumbnail_url: str | None = None


class RenderListResponse(BaseModel):
    items: list[RenderResponse]
    total: int
    limit: int
    offset: int
