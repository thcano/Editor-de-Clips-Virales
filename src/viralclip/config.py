"""Configuración por variables de entorno con valores por defecto seguros."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .desktop import default_data_dir

DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
)

_TRUE_VALUES = frozenset({"1", "true", "yes", "si", "sí", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _read(environ: Mapping[str, str], name: str, default: str) -> str:
    value = environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_bool(environ: Mapping[str, str], name: str, default: bool) -> bool:
    raw = _read(environ, name, "true" if default else "false").lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise ValueError(
        f"{name} debe ser un booleano (true/false); valor recibido: {raw!r}"
    )


def _env_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = _read(environ, name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un entero; valor recibido: {raw!r}") from exc


def _env_float(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = _read(environ, name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un número; valor recibido: {raw!r}") from exc


def _env_list(
    environ: Mapping[str, str], name: str, default: tuple[str, ...]
) -> tuple[str, ...]:
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    items = tuple(item.strip() for item in raw.split(",") if item.strip())
    return items or default


def _load_dotenv(path: Path | None = None) -> None:
    """Carga un archivo ``.env`` local sin sobrescribir el entorno real.

    Formato admitido: ``CLAVE=valor`` por línea, comentarios con ``#`` y
    valores opcionalmente entre comillas simples o dobles.
    """

    import os

    env_path = path or Path(".env")
    try:
        content = env_path.read_text(encoding="utf-8")
    except OSError:
        return

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    """Ajustes de la aplicación leídos del entorno."""

    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000

    db_path: Path = Path("data/viralclip.db")
    api_key: str | None = None
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS

    max_input_bytes: int = 2_000_000
    max_clips: int = 8
    max_segments: int = 20_000

    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_language: str = "auto"
    whisper_model_dir: Path = Path("data/models")
    whisper_beam_size: int = 5
    whisper_vad: bool = True
    upload_dir: Path = Path("data/uploads")
    upload_max_bytes: int = 2_000_000_000
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    render_dir: Path = Path("data/renders")
    render_width: int = 1080
    render_height: int = 1920
    render_fps: int = 30
    render_crf: int = 20
    render_preset: str = "veryfast"
    render_zoom: float = 0.06
    render_font: str = "Arial"
    render_font_size: int = 54
    render_timeout: float = 1800.0

    llm_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:latest"
    ollama_timeout: float = 60.0
    ollama_health_timeout: float = 2.0
    ollama_circuit_failures: int = 3
    ollama_circuit_cooldown: float = 60.0

    log_level: str = "INFO"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Construye los ajustes desde un mapeo (por defecto ``os.environ``)."""

        if environ is None:
            import os

            _load_dotenv()
            environ = os.environ

        api_key = environ.get("VIRALCLIP_API_KEY")
        if api_key is not None and not api_key.strip():
            api_key = None

        data_dir = default_data_dir(environ)
        db_path = Path(_read(environ, "VIRALCLIP_DB_PATH", "data/viralclip.db"))

        return cls(
            env=_read(environ, "VIRALCLIP_ENV", "development"),
            host=_read(environ, "VIRALCLIP_HOST", "127.0.0.1"),
            port=_env_int(environ, "VIRALCLIP_PORT", 8000),
            db_path=db_path,
            api_key=api_key.strip() if api_key else None,
            cors_origins=_env_list(
                environ, "VIRALCLIP_CORS_ORIGINS", DEFAULT_CORS_ORIGINS
            ),
            max_input_bytes=_env_int(environ, "VIRALCLIP_MAX_INPUT_BYTES", 2_000_000),
            max_clips=_env_int(environ, "VIRALCLIP_MAX_CLIPS", 8),
            max_segments=_env_int(environ, "VIRALCLIP_MAX_SEGMENTS", 20_000),
            whisper_model=_read(
                environ, "VIRALCLIP_WHISPER_MODEL", "small"
            ).lower(),
            whisper_device=_read(
                environ, "VIRALCLIP_WHISPER_DEVICE", "auto"
            ).lower(),
            whisper_compute_type=_read(
                environ, "VIRALCLIP_WHISPER_COMPUTE_TYPE", "auto"
            ).lower(),
            whisper_language=_read(
                environ, "VIRALCLIP_WHISPER_LANGUAGE", "auto"
            ).lower(),
            whisper_model_dir=Path(
                _read(
                    environ,
                    "VIRALCLIP_WHISPER_MODEL_DIR",
                    str(data_dir / "models"),
                )
            ),
            whisper_beam_size=_env_int(environ, "VIRALCLIP_WHISPER_BEAM_SIZE", 5),
            whisper_vad=_env_bool(environ, "VIRALCLIP_WHISPER_VAD", True),
            upload_dir=Path(
                _read(
                    environ,
                    "VIRALCLIP_UPLOAD_DIR",
                    str(data_dir / "uploads"),
                )
            ),
            upload_max_bytes=_env_int(
                environ, "VIRALCLIP_UPLOAD_MAX_BYTES", 2_000_000_000
            ),
            ffmpeg_path=_read(environ, "VIRALCLIP_FFMPEG", "ffmpeg"),
            ffprobe_path=_read(environ, "VIRALCLIP_FFPROBE", "ffprobe"),
            render_dir=Path(
                _read(
                    environ,
                    "VIRALCLIP_RENDER_DIR",
                    str(data_dir / "renders"),
                )
            ),
            render_width=_env_int(environ, "VIRALCLIP_RENDER_WIDTH", 1080),
            render_height=_env_int(environ, "VIRALCLIP_RENDER_HEIGHT", 1920),
            render_fps=_env_int(environ, "VIRALCLIP_RENDER_FPS", 30),
            render_crf=_env_int(environ, "VIRALCLIP_RENDER_CRF", 20),
            render_preset=_read(
                environ, "VIRALCLIP_RENDER_PRESET", "veryfast"
            ).lower(),
            render_zoom=_env_float(environ, "VIRALCLIP_RENDER_ZOOM", 0.06),
            render_font=_read(environ, "VIRALCLIP_RENDER_FONT", "Arial"),
            render_font_size=_env_int(
                environ, "VIRALCLIP_RENDER_FONT_SIZE", 54
            ),
            render_timeout=_env_float(
                environ, "VIRALCLIP_RENDER_TIMEOUT", 1800.0
            ),
            llm_enabled=_env_bool(environ, "VIRALCLIP_LLM_ENABLED", True),
            ollama_base_url=_read(
                environ, "OLLAMA_BASE_URL", "http://127.0.0.1:11434"
            ).rstrip("/"),
            ollama_model=_read(environ, "OLLAMA_MODEL", "llama3.2:latest"),
            ollama_timeout=_env_float(environ, "VIRALCLIP_OLLAMA_TIMEOUT", 60.0),
            ollama_health_timeout=_env_float(
                environ, "VIRALCLIP_OLLAMA_HEALTH_TIMEOUT", 2.0
            ),
            ollama_circuit_failures=_env_int(
                environ, "VIRALCLIP_OLLAMA_CIRCUIT_FAILURES", 3
            ),
            ollama_circuit_cooldown=_env_float(
                environ, "VIRALCLIP_OLLAMA_CIRCUIT_COOLDOWN", 60.0
            ),
            log_level=_read(environ, "VIRALCLIP_LOG_LEVEL", "INFO").upper(),
        )


def load_settings() -> Settings:
    """Atajo para leer los ajustes del entorno actual."""

    return Settings.from_env()
