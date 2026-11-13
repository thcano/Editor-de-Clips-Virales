"""Transcripción local de audio/video con faster-whisper y FFmpeg.

El audio se extrae con FFmpeg a WAV PCM 16 kHz mono y se pasa a Whisper como
un array NumPy. Así se evita el decodificador de PyAV, que en algunas
combinaciones de versiones es incompatible, y se controla el formato exacto.

El modelo se carga de forma perezosa y se mantiene uno solo en memoria para no
agotar la RAM en equipos de consumo.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from .errors import (
    FFmpegUnavailableError,
    InvalidMediaError,
    InvalidParameterError,
    MediaTooLargeError,
    TranscriptionFailedError,
)
from .models import Transcript
from .transcript import normalize_transcript

logger = logging.getLogger("viralclip.transcription")

SUPPORTED_MODELS = ("tiny", "base", "small", "medium", "large-v3")
SUPPORTED_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mkv",
        ".mov",
        ".webm",
        ".m4v",
        ".avi",
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".opus",
    }
)
SAMPLE_RATE = 16_000
DEFAULT_MAX_TRANSCRIPT_BYTES = 50_000_000

ProgressCallback = Callable[[int, str], None]

_MODEL_LOCK = threading.Lock()
_CURRENT_MODEL: tuple[tuple[str, str, str, str], Any] | None = None
_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(-[a-z]{2,4})?$")


def normalize_model(value: str | None) -> str:
    """Valida y normaliza el nombre del modelo de Whisper."""

    model = (value or "small").strip().lower()
    if model == "large":
        model = "large-v3"
    if model not in SUPPORTED_MODELS:
        raise InvalidParameterError(
            f"Modelo de Whisper no soportado: {value!r}. "
            f"Usa uno de: {', '.join(SUPPORTED_MODELS)}"
        )
    return model


def normalize_language(value: str | None) -> str:
    """Valida el idioma forzado o ``auto``."""

    language = (value or "auto").strip().lower()
    if language == "auto":
        return language
    if not _LANGUAGE_RE.fullmatch(language):
        raise InvalidParameterError(
            f"Idioma no válido: {value!r}. Usa 'auto' o un código como 'es' o 'en'"
        )
    return language


def detect_device(preferred: str = "auto") -> str:
    """Devuelve ``cuda`` si hay GPU compatible y el usuario no fuerza otra cosa."""

    choice = (preferred or "auto").strip().lower()
    if choice in {"cpu", "cuda"}:
        return choice
    if choice != "auto":
        raise InvalidParameterError(
            f"Dispositivo no válido: {preferred!r}. Usa 'auto', 'cpu' o 'cuda'"
        )
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:  # pragma: no cover - depende del entorno
        logger.warning("No se pudo detectar CUDA; se usa CPU", exc_info=True)
        return "cpu"


def resolve_compute_type(device: str, preferred: str = "auto") -> str:
    """Elige el tipo de cómputo adecuado para el dispositivo."""

    choice = (preferred or "auto").strip().lower()
    if choice == "auto":
        return "float16" if device == "cuda" else "int8"
    allowed = {"int8", "int8_float16", "float16", "float32"}
    if choice not in allowed:
        raise InvalidParameterError(
            f"compute_type no válido: {preferred!r}. "
            f"Usa uno de: {', '.join(sorted(allowed))}"
        )
    if device == "cpu" and choice in {"float16", "int8_float16"}:
        logger.warning("compute_type=%s no es óptimo en CPU; se usa int8", choice)
        return "int8"
    return choice


def ffmpeg_binary(ffmpeg_path: str = "ffmpeg") -> str:
    """Resuelve el binario de FFmpeg o lanza un error estable."""

    candidate = shutil.which(ffmpeg_path)
    if candidate is None:
        path = Path(ffmpeg_path).expanduser()
        if path.is_file():
            candidate = str(path)
    if candidate is None:
        raise FFmpegUnavailableError(
            "FFmpeg no está instalado o no está en PATH. "
            "Instálalo y comprueba con 'ffmpeg -version'."
        )
    try:
        result = subprocess.run(
            [candidate, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError as exc:
        raise FFmpegUnavailableError(
            "FFmpeg no se pudo ejecutar", detail=str(exc)
        ) from exc
    if result.returncode != 0:
        raise FFmpegUnavailableError(
            "FFmpeg no se pudo ejecutar",
            detail=(result.stderr or result.stdout or "").strip()[:300],
        )
    return candidate


def ffmpeg_available(ffmpeg_path: str = "ffmpeg") -> bool:
    """Comprueba FFmpeg sin lanzar excepciones (para /api/config)."""

    try:
        ffmpeg_binary(ffmpeg_path)
    except FFmpegUnavailableError:
        return False
    return True


def audio_command(binary: str, media_path: Path, wav_path: Path) -> list[str]:
    """Comando FFmpeg para extraer WAV PCM 16 kHz mono."""

    return [
        binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(media_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]


def validate_media(path: str | Path, *, max_bytes: int | None = None) -> Path:
    """Comprueba existencia, extensión y tamaño del video o audio."""

    media = Path(path).expanduser()
    if not media.is_file():
        raise InvalidMediaError(f"No existe el archivo {media}")
    if media.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise InvalidMediaError(
            f"Formato no soportado: {media.suffix or '(sin extensión)'}. "
            f"Formatos: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    if max_bytes is not None and media.stat().st_size > max_bytes:
        raise MediaTooLargeError(
            f"El archivo supera el límite de {max_bytes} bytes"
        )
    return media


def extract_audio(
    media_path: Path,
    wav_path: Path,
    ffmpeg_path: str = "ffmpeg",
) -> None:
    """Extrae el audio del video con FFmpeg."""

    binary = ffmpeg_binary(ffmpeg_path)
    result = subprocess.run(
        audio_command(binary, media_path, wav_path),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-500:]
        raise TranscriptionFailedError(
            "FFmpeg no pudo extraer el audio del video", detail=detail
        )
    if not wav_path.is_file() or wav_path.stat().st_size == 0:
        raise TranscriptionFailedError("FFmpeg no generó audio utilizable")


def read_wav(wav_path: Path) -> tuple[np.ndarray, float]:
    """Lee un WAV PCM 16 bits mono y devuelve muestras float32 y duración."""

    try:
        with wave.open(str(wav_path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (OSError, wave.Error) as exc:
        raise TranscriptionFailedError(
            "El audio extraído no es un WAV válido", detail=str(exc)
        ) from exc

    if channels != 1 or width != 2 or rate != SAMPLE_RATE:
        raise TranscriptionFailedError(
            "El audio extraído tiene un formato inesperado",
            detail=f"channels={channels}, width={width}, rate={rate}",
        )
    if not frames:
        raise TranscriptionFailedError("El audio extraído está vacío")

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, len(audio) / SAMPLE_RATE


def _get_model(
    model_size: str,
    device: str,
    compute_type: str,
    model_dir: Path,
) -> Any:
    """Carga el modelo y mantiene solo uno en memoria."""

    global _CURRENT_MODEL
    key = (model_size, device, compute_type, str(model_dir))
    with _MODEL_LOCK:
        if _CURRENT_MODEL is not None and _CURRENT_MODEL[0] == key:
            return _CURRENT_MODEL[1]

        from faster_whisper import WhisperModel

        model_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Cargando Whisper %s (%s/%s) desde %s",
            model_size,
            device,
            compute_type,
            model_dir,
        )
        model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=str(model_dir),
        )
        _CURRENT_MODEL = (key, model)
        return model


def reset_model_cache() -> None:
    """Libera el modelo cargado (útil en pruebas o al cambiar de ajustes)."""

    global _CURRENT_MODEL
    with _MODEL_LOCK:
        _CURRENT_MODEL = None


def build_document(
    language: str | None,
    duration: float,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construye el documento que consume ``normalize_transcript``."""

    last_end = segments[-1]["end"] if segments else 0.0
    return {
        "language": language or "es",
        "duration": max(float(duration or 0.0), float(last_end)),
        "segments": segments,
    }


class WhisperTranscriber:
    """Transcriptor basado en faster-whisper con audio extraído por FFmpeg."""

    def __init__(
        self,
        *,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
        language: str = "auto",
        model_dir: str | Path = "data/models",
        ffmpeg_path: str = "ffmpeg",
        beam_size: int = 5,
        vad: bool = True,
        max_segments: int = 20_000,
        max_transcript_bytes: int = DEFAULT_MAX_TRANSCRIPT_BYTES,
    ) -> None:
        self.model_size = normalize_model(model_size)
        self.device = detect_device(device)
        self.compute_type = resolve_compute_type(self.device, compute_type)
        self.language = normalize_language(language)
        self.model_dir = Path(model_dir)
        self.ffmpeg_path = ffmpeg_path
        self.beam_size = beam_size
        self.vad = vad
        self.max_segments = max_segments
        self.max_transcript_bytes = max_transcript_bytes

    def transcribe(
        self,
        media_path: str | Path,
        *,
        language: str | None = None,
        on_stage: ProgressCallback | None = None,
    ) -> Transcript:
        """Transcribe un video/audio y devuelve un :class:`Transcript` validado."""

        def stage(progress: int, name: str) -> None:
            if on_stage is not None:
                on_stage(progress, name)

        media = validate_media(media_path)
        ffmpeg_binary(self.ffmpeg_path)
        selected_language = normalize_language(language or self.language)

        stage(5, "extrayendo")
        with tempfile.TemporaryDirectory(prefix="viralclip-audio-") as tmp:
            wav_path = Path(tmp) / "audio.wav"
            extract_audio(media, wav_path, self.ffmpeg_path)
            audio, wav_duration = read_wav(wav_path)

            stage(10, "cargando modelo")
            model = _get_model(
                self.model_size,
                self.device,
                self.compute_type,
                self.model_dir,
            )

            stage(15, "transcribiendo")
            segments_iter, info = model.transcribe(
                audio,
                language=None if selected_language == "auto" else selected_language,
                word_timestamps=True,
                vad_filter=self.vad,
                beam_size=self.beam_size,
            )

            segments: list[dict[str, Any]] = []
            total_duration = float(
                getattr(info, "duration", 0.0) or wav_duration or 0.0
            )
            for segment in segments_iter:
                text = (segment.text or "").strip()
                if not text or segment.end <= segment.start:
                    continue
                words: list[dict[str, Any]] = []
                for word in segment.words or []:
                    if word.end <= word.start:
                        continue
                    item: dict[str, Any] = {
                        "word": word.word.strip(),
                        "start": round(float(word.start), 3),
                        "end": round(float(word.end), 3),
                    }
                    probability = getattr(word, "probability", None)
                    if probability is not None:
                        item["confidence"] = round(float(probability), 4)
                    if item["word"]:
                        words.append(item)
                segments.append(
                    {
                        "start": round(float(segment.start), 3),
                        "end": round(float(segment.end), 3),
                        "text": text,
                        "words": words,
                    }
                )
                if total_duration > 0:
                    progress = 15 + int(
                        80 * min(float(segment.end) / total_duration, 1.0)
                    )
                    stage(progress, "transcribiendo")

        if not segments:
            raise TranscriptionFailedError(
                "No se detectó voz en el audio. Comprueba el volumen o prueba otro archivo."
            )

        stage(98, "guardando")
        document = build_document(
            getattr(info, "language", None) or selected_language,
            max(total_duration, wav_duration),
            segments,
        )
        return normalize_transcript(
            document,
            max_segments=self.max_segments,
            max_bytes=self.max_transcript_bytes,
        )
