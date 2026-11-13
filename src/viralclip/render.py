"""Renderizado de clips verticales con FFmpeg.

El módulo no depende de FastAPI ni de SQLite: recibe un :class:`~viralclip.models.Clip`,
un video de origen y unos ajustes, y produce un MP4 9:16 con fondo desenfocado,
zoom suave y subtítulos ASS quemados.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .errors import (
    InvalidSourceError,
    RenderFailedError,
    RenderToolUnavailableError,
)
from .models import Clip

logger = logging.getLogger("viralclip.render")

ProgressCallback = Callable[[int, str], None]

VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mov",
        ".mkv",
        ".avi",
        ".webm",
        ".m4v",
        ".mpeg",
        ".mpg",
        ".wmv",
        ".flv",
        ".ts",
        ".3gp",
    }
)

# Amarillo #FFD400 en formato ASS (AABBGGRR).
ASS_YELLOW = "&H0000D4FF&"
ASS_WHITE = "&H00FFFFFF&"


@dataclass(frozen=True)
class VideoInfo:
    """Datos mínimos del video que necesita el grafo de filtros."""

    width: int
    height: int
    duration: float
    has_audio: bool


@dataclass(frozen=True)
class RenderResult:
    """Resultado de un renderizado correcto."""

    output_path: Path
    thumbnail_path: Path | None
    width: int
    height: int
    duration: float
    size_bytes: int


def _resolve_tool(name: str, *, label: str) -> str:
    """Resuelve un binario de FFmpeg o lanza un error estable."""

    candidate = shutil.which(name)
    if candidate is None:
        path = Path(name).expanduser()
        if path.is_file():
            candidate = str(path)
    if candidate is None:
        raise RenderToolUnavailableError(
            f"{label} no está instalado o no está en PATH. "
            f"Instálalo y comprueba con '{label.lower()} -version'."
        )
    return candidate


def ffprobe_available(ffprobe_path: str = "ffprobe") -> bool:
    """Comprueba ffprobe sin lanzar excepciones (para /api/config)."""

    try:
        _resolve_tool(ffprobe_path, label="ffprobe")
    except RenderToolUnavailableError:
        return False
    return True


def validate_source(path: str | Path) -> Path:
    """Comprueba que el video existe y tiene una extensión admitida."""

    source = Path(path).expanduser()
    if not source.is_file():
        raise InvalidSourceError(f"No existe el video de origen: {source}")
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise InvalidSourceError(
            f"Formato de video no soportado: {source.suffix or '(sin extensión)'}. "
            f"Formatos: {', '.join(sorted(VIDEO_EXTENSIONS))}"
        )
    return source.resolve()


def probe_video(source: Path, ffprobe_path: str = "ffprobe") -> VideoInfo:
    """Lee dimensiones, duración y presencia de audio con ``ffprobe``."""

    binary = _resolve_tool(ffprobe_path, label="ffprobe")
    command = [
        binary,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(source),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
            check=False,
        )
    except OSError as exc:
        raise RenderToolUnavailableError(
            "ffprobe no se pudo ejecutar", detail=str(exc)
        ) from exc

    if completed.returncode != 0:
        raise InvalidSourceError(
            "El video de origen no se pudo leer",
            detail=(completed.stderr or completed.stdout or "").strip()[:300],
        )

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise InvalidSourceError(
            "ffprobe devolvió una respuesta ilegible", detail=str(exc)
        ) from exc

    streams = payload.get("streams") or []
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if video is None:
        raise InvalidSourceError("El archivo no contiene una pista de video")

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise InvalidSourceError("No se pudieron leer las dimensiones del video")

    duration_raw = video.get("duration") or (payload.get("format") or {}).get(
        "duration"
    )
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError):
        raise InvalidSourceError("No se pudo leer la duración del video") from None
    if duration <= 0:
        raise InvalidSourceError("La duración del video no es válida")

    has_audio = any(
        stream.get("codec_type") == "audio" for stream in streams
    )
    return VideoInfo(
        width=width, height=height, duration=duration, has_audio=has_audio
    )


def validate_clip(clip: Clip, info: VideoInfo) -> None:
    """Comprueba que el rango del clip cae dentro del video."""

    if clip.start_seconds < 0:
        raise InvalidSourceError("El clip empieza antes del inicio del video")
    if clip.end_seconds <= clip.start_seconds:
        raise InvalidSourceError("El clip tiene un rango de tiempo inválido")
    if clip.end_seconds > info.duration + 0.5:
        raise InvalidSourceError(
            f"El clip termina en {clip.end_seconds:.2f} s, "
            f"pero el video dura {info.duration:.2f} s"
        )


def _escape_ass_text(text: str) -> str:
    """Escapa caracteres especiales de ASS en texto plano."""

    return (
        text.replace("\\", "/")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _ass_timestamp(seconds: float) -> str:
    clamped = max(0.0, seconds)
    hours = int(clamped // 3600)
    minutes = int((clamped % 3600) // 60)
    secs = int(clamped % 60)
    centis = int(round((clamped - int(clamped)) * 100))
    if centis >= 100:
        secs += 1
        centis -= 100
    if secs >= 60:
        minutes += 1
        secs -= 60
    if minutes >= 60:
        hours += 1
        minutes -= 60
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def build_ass_subtitles(
    clip: Clip,
    *,
    width: int,
    height: int,
    font: str = "Arial",
    font_size: int = 54,
) -> str:
    """Genera el contenido ASS con los subtítulos del clip."""

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{font_size},{ASS_WHITE},{ASS_YELLOW},"
        "&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,1,2,60,60,220,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )

    start_offset = clip.start_seconds
    duration = clip.end_seconds - clip.start_seconds
    events: list[str] = []

    for line in clip.subtitles:
        start = max(0.0, line.start - start_offset)
        end = min(duration, line.end - start_offset)
        if end <= start:
            continue

        if line.words:
            parts: list[str] = []
            for word in line.words:
                text = _escape_ass_text(word.word)
                if not text:
                    continue
                if word.highlight:
                    parts.append(f"{{\\c{ASS_YELLOW}}}{text}{{\\c{ASS_WHITE}}}")
                else:
                    parts.append(text)
            body = " ".join(parts)
        else:
            body = _escape_ass_text(line.text)

        if not body:
            continue
        events.append(
            f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},"
            f"Default,,0,0,0,,{body}"
        )

    return header + "\n".join(events) + ("\n" if events else "")


def build_filter_graph(
    *,
    width: int,
    height: int,
    zoom: float,
    clip_duration: float,
    subtitles_name: str | None,
) -> str:
    """Construye el grafo: fondo desenfocado + frente centrado + ASS."""

    background = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=20:2,"
        "eq=brightness=-0.10:saturation=0.9[bgv];"
    )

    foreground = (
        f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        "setsar=1"
    )
    if zoom > 0 and clip_duration > 0:
        factor = f"(1+{zoom:.6f}*t/{clip_duration:.6f})"
        foreground += (
            f",scale=w='trunc(iw*{factor}/2)*2':h=-2:eval=frame"
        )
    foreground += "[fgv];"

    overlay = (
        "[bgv][fgv]overlay=(W-w)/2:(H-h)/2:format=auto"
    )
    if subtitles_name:
        overlay += f",ass={subtitles_name}"
    overlay += ",format=yuv420p[vout]"

    return background + foreground + overlay


def build_ffmpeg_command(
    *,
    ffmpeg_binary: str,
    source: Path,
    output: Path,
    clip: Clip,
    info: VideoInfo,
    settings: Settings,
    subtitles_name: str | None,
) -> list[str]:
    """Construye la lista de argumentos de FFmpeg."""

    duration = clip.end_seconds - clip.start_seconds
    graph = build_filter_graph(
        width=settings.render_width,
        height=settings.render_height,
        zoom=settings.render_zoom,
        clip_duration=duration,
        subtitles_name=subtitles_name,
    )

    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-ss",
        f"{clip.start_seconds:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(source),
    ]

    if not info.has_audio:
        command += [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
        ]

    command += [
        "-filter_complex",
        graph,
        "-map",
        "[vout]",
    ]
    if info.has_audio:
        command += ["-map", "0:a:0?"]
    else:
        command += ["-map", "1:a:0", "-shortest"]

    command += [
        "-c:v",
        "libx264",
        "-preset",
        settings.render_preset,
        "-crf",
        str(settings.render_crf),
        "-r",
        str(settings.render_fps),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output),
    ]
    return command


def _parse_progress_line(line: str) -> float | None:
    """Devuelve el tiempo de salida en segundos a partir de ``-progress``."""

    key, _, raw = line.strip().partition("=")
    if key not in {"out_time_us", "out_time_ms", "out_time"}:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if key in {"out_time_us", "out_time_ms"}:
        try:
            return int(raw) / 1_000_000
        except ValueError:
            return None
    # out_time=HH:MM:SS.ffffff
    try:
        hours, minutes, seconds = raw.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return None


def _run_ffmpeg(
    command: list[str],
    *,
    duration: float,
    timeout: float,
    progress: ProgressCallback | None,
    cwd: str | Path | None = None,
) -> None:
    """Ejecuta FFmpeg, informa progreso y controla el tiempo máximo."""

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            cwd=str(cwd) if cwd is not None else None,
        )
    except OSError as exc:
        raise RenderToolUnavailableError(
            "FFmpeg no se pudo ejecutar", detail=str(exc)
        ) from exc

    assert process.stdout is not None
    deadline = time.monotonic() + timeout if timeout > 0 else None
    tail: list[str] = []

    try:
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            seconds = _parse_progress_line(line)
            if seconds is not None and duration > 0 and progress is not None:
                ratio = max(0.0, min(1.0, seconds / duration))
                progress(10 + int(ratio * 80), "renderizando")
                continue
            tail.append(line)
            if len(tail) > 40:
                tail.pop(0)
            if deadline is not None and time.monotonic() > deadline:
                process.kill()
                raise RenderFailedError(
                    "El renderizado superó el tiempo máximo configurado"
                )
        returncode = process.wait()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    if returncode != 0:
        detail = "\n".join(tail[-8:]) or "FFmpeg terminó con error"
        raise RenderFailedError(
            "FFmpeg no pudo renderizar el clip", detail=detail[:1000]
        )


def _extract_thumbnail(
    ffmpeg_binary: str,
    *,
    output: Path,
    thumbnail: Path,
    duration: float,
    timeout: float,
) -> Path | None:
    """Extrae un JPG del primer segundo (o del centro si el clip es corto)."""

    position = 1.0 if duration > 1.5 else max(0.0, duration / 2)
    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{position:.3f}",
        "-i",
        str(output),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(thumbnail),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=max(30.0, timeout),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("No se pudo generar la miniatura: %s", exc)
        return None
    if completed.returncode != 0 or not thumbnail.is_file():
        logger.warning(
            "No se pudo generar la miniatura: %s",
            (completed.stderr or "").strip()[:300],
        )
        return None
    return thumbnail


class FFmpegRenderer:
    """Renderizador real basado en el FFmpeg del sistema."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def render(
        self,
        *,
        source_path: str | Path,
        clip: Clip,
        render_id: str,
        job_id: str,
        output_dir: str | Path | None = None,
        progress: ProgressCallback | None = None,
    ) -> RenderResult:
        settings = self.settings

        def report(value: int, stage: str) -> None:
            if progress is not None:
                progress(value, stage)

        report(2, "validando")
        source = validate_source(source_path)
        ffmpeg_binary = _resolve_tool(settings.ffmpeg_path, label="ffmpeg")
        info = probe_video(source, settings.ffprobe_path)
        validate_clip(clip, info)

        target_dir = Path(output_dir or settings.render_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{job_id}_{clip.id}_{render_id}"
        output = target_dir / f"{stem}.mp4"
        thumbnail = target_dir / f"{stem}.jpg"
        duration = clip.end_seconds - clip.start_seconds

        report(8, "preparando")
        with tempfile.TemporaryDirectory(prefix="viralclip-render-") as temp:
            workdir = Path(temp)
            subtitles_name: str | None = None
            if clip.subtitles:
                ass_path = workdir / "subtitles.ass"
                ass_path.write_text(
                    build_ass_subtitles(
                        clip,
                        width=settings.render_width,
                        height=settings.render_height,
                        font=settings.render_font,
                        font_size=settings.render_font_size,
                    ),
                    encoding="utf-8",
                )
                subtitles_name = ass_path.name

            command = build_ffmpeg_command(
                ffmpeg_binary=ffmpeg_binary,
                source=source,
                output=output,
                clip=clip,
                info=info,
                settings=settings,
                subtitles_name=subtitles_name,
            )
            _run_ffmpeg(
                command,
                duration=duration,
                timeout=settings.render_timeout,
                progress=progress,
                cwd=workdir,
            )

        if not output.is_file() or output.stat().st_size == 0:
            raise RenderFailedError("FFmpeg no generó el archivo de salida")

        report(95, "miniatura")
        thumbnail_path = _extract_thumbnail(
            ffmpeg_binary,
            output=output,
            thumbnail=thumbnail,
            duration=duration,
            timeout=settings.render_timeout,
        )
        report(100, "done")

        return RenderResult(
            output_path=output,
            thumbnail_path=thumbnail_path,
            width=settings.render_width,
            height=settings.render_height,
            duration=duration,
            size_bytes=output.stat().st_size,
        )
