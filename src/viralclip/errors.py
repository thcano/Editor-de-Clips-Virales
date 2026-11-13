"""Códigos de error estables y excepciones del dominio."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Códigos estables que la API y la UI pueden interpretar."""

    INVALID_TRANSCRIPT = "VC-1001"
    PAYLOAD_TOO_LARGE = "VC-1002"
    INVALID_PARAMETERS = "VC-1003"
    INVALID_MEDIA = "VC-1101"
    MEDIA_TOO_LARGE = "VC-1102"
    FFMPEG_UNAVAILABLE = "VC-1103"
    TRANSCRIPTION_FAILED = "VC-1104"
    INVALID_SOURCE = "VC-1201"
    RENDER_TOOL_UNAVAILABLE = "VC-1202"
    RENDER_FAILED = "VC-1203"
    RENDER_CONFLICT = "VC-1204"
    ANALYSIS_NOT_FOUND = "VC-2001"
    ANALYSIS_NOT_READY = "VC-2002"
    FEATURE_DISABLED = "VC-2003"
    TRANSCRIPTION_NOT_FOUND = "VC-2004"
    RENDER_NOT_FOUND = "VC-2005"
    UNAUTHORIZED = "VC-3001"
    OLLAMA_UNAVAILABLE = "VC-4001"
    INTERNAL = "VC-5001"


class ViralClipError(Exception):
    """Excepción base con código, estado HTTP y mensaje para el usuario."""

    code: ErrorCode = ErrorCode.INTERNAL
    http_status: int = 500
    default_message: str = "Error interno del editor de clips"

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(self.message)

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.detail:
            payload["detail"] = self.detail
        if request_id:
            payload["request_id"] = request_id
        return payload


class InvalidTranscriptError(ViralClipError):
    """La transcripción no cumple el contrato de entrada."""

    code = ErrorCode.INVALID_TRANSCRIPT
    http_status = 400
    default_message = "La transcripción no es válida"


class PayloadTooLargeError(ViralClipError):
    """El payload o el número de segmentos excede el límite configurado."""

    code = ErrorCode.PAYLOAD_TOO_LARGE
    http_status = 413
    default_message = "El payload es demasiado grande"


class InvalidParameterError(ViralClipError):
    """Un parámetro de análisis está fuera de rango."""

    code = ErrorCode.INVALID_PARAMETERS
    http_status = 422
    default_message = "Los parámetros del análisis no son válidos"


class OllamaUnavailableError(ViralClipError):
    """Ollama no está disponible o no pudo completar la generación.

    No es fatal: el pipeline cae al motor heurístico y marca ``degraded``.
    """

    code = ErrorCode.OLLAMA_UNAVAILABLE
    http_status = 502
    default_message = "Ollama no está disponible; se usará el motor heurístico"


class AnalysisNotFoundError(ViralClipError):
    """No existe el análisis o el clip solicitado."""

    code = ErrorCode.ANALYSIS_NOT_FOUND
    http_status = 404
    default_message = "El análisis no existe"


class InvalidMediaError(ViralClipError):
    """El video no existe, no es un archivo o su formato no está soportado."""

    code = ErrorCode.INVALID_MEDIA
    http_status = 400
    default_message = "El video no es válido"


class MediaTooLargeError(ViralClipError):
    """El video supera el límite de subida configurado."""

    code = ErrorCode.MEDIA_TOO_LARGE
    http_status = 413
    default_message = "El video es demasiado grande"


class FFmpegUnavailableError(ViralClipError):
    """FFmpeg no está instalado o no se pudo ejecutar."""

    code = ErrorCode.FFMPEG_UNAVAILABLE
    http_status = 503
    default_message = "FFmpeg no está disponible"


class TranscriptionFailedError(ViralClipError):
    """Whisper o FFmpeg no pudieron completar la transcripción."""

    code = ErrorCode.TRANSCRIPTION_FAILED
    http_status = 500
    default_message = "La transcripción falló"


class TranscriptionNotFoundError(ViralClipError):
    """No existe la transcripción solicitada."""

    code = ErrorCode.TRANSCRIPTION_NOT_FOUND
    http_status = 404
    default_message = "La transcripción no existe"


class InvalidSourceError(ViralClipError):
    """El video de origen no existe, no es válido o el clip está fuera de rango."""

    code = ErrorCode.INVALID_SOURCE
    http_status = 400
    default_message = "El video de origen no es válido"


class RenderToolUnavailableError(ViralClipError):
    """FFmpeg o ffprobe no están disponibles para renderizar."""

    code = ErrorCode.RENDER_TOOL_UNAVAILABLE
    http_status = 503
    default_message = "FFmpeg no está disponible para renderizar"


class RenderFailedError(ViralClipError):
    """FFmpeg no pudo completar el renderizado del clip."""

    code = ErrorCode.RENDER_FAILED
    http_status = 500
    default_message = "El renderizado del clip falló"


class RenderConflictError(ViralClipError):
    """Ya hay un render activo para el mismo clip."""

    code = ErrorCode.RENDER_CONFLICT
    http_status = 409
    default_message = "Ya hay un render activo para este clip"


class RenderNotFoundError(ViralClipError):
    """No existe el render solicitado."""

    code = ErrorCode.RENDER_NOT_FOUND
    http_status = 404
    default_message = "El render no existe"


class AnalysisNotReadyError(ViralClipError):
    """El análisis todavía no terminó y no se puede exportar."""

    code = ErrorCode.ANALYSIS_NOT_READY
    http_status = 409
    default_message = "El análisis todavía no está listo"


class FeatureDisabledError(ViralClipError):
    """Una función está desactivada por un feature flag local."""

    code = ErrorCode.FEATURE_DISABLED
    http_status = 403
    default_message = "La función está desactivada"


class UnauthorizedError(ViralClipError):
    """Falta la API key o no coincide con la configurada."""

    code = ErrorCode.UNAUTHORIZED
    http_status = 401
    default_message = "API key ausente o inválida"
