"""Lanzador de escritorio: arranca la API local y abre el navegador."""

from __future__ import annotations

import argparse
import copy
import socket
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import uvicorn

from . import __version__
from .api.app import create_app
from .assets import AssetVersion, versioned_url
from .config import Settings

DEFAULT_START_TIMEOUT = 10.0

ServerFactory = Callable[[object, str, int, str], uvicorn.Server]
BrowserOpen = Callable[[str], bool]


def free_port(host: str = "127.0.0.1") -> int:
    """Reserva un puerto libre en el host indicado."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def resolve_port(host: str, port: int) -> int:
    """Devuelve el puerto pedido o uno libre cuando ``port`` es 0."""

    if port > 0:
        return port
    return free_port(host)


def build_url(host: str, port: int, version: str | None = None) -> str:
    """Construye la URL de la interfaz.

    Cuando se indica ``version`` se añade como parámetro ``v``. El navegador
    guarda la página de entrada en su caché y, si esa copia está vigente, no
    vuelve a preguntar al servidor: seguiría pidiendo los assets con la URL
    antigua y mostrando el diseño anterior. Abrir con una URL versionada
    garantiza que la primera respuesta es siempre la vigente.
    """

    url = f"http://{host}:{port}"
    if version:
        return versioned_url(url, version)
    return url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="viralclip",
        description=(
            "Arranca el Editor de Clips Virales en local. Por defecto abre una "
            "ventana de escritorio propia; con --browser usa el navegador del "
            "sistema."
        ),
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host de escucha (por defecto VIRALCLIP_HOST o 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Puerto (0 = libre; por defecto VIRALCLIP_PORT o 8000).",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Ruta de la base SQLite (por defecto VIRALCLIP_DB_PATH).",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help=(
            "Abre la interfaz en el navegador del sistema en lugar de la "
            "ventana de escritorio propia."
        ),
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="No abre ninguna interfaz: solo arranca el servidor local.",
    )
    parser.add_argument(
        "--transcribe",
        default=None,
        metavar="VIDEO",
        help="Transcribe un video/audio local y guarda el JSON; no arranca el servidor.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Ruta del JSON de salida para --transcribe.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Modelo de Whisper para --transcribe (tiny, base, small, medium, large-v3).",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Idioma para --transcribe (auto, es, en…).",
    )
    parser.add_argument(
        "--compute-type",
        default=None,
        help="Tipo de cómputo para --transcribe (auto, int8, float16, float32).",
    )
    parser.add_argument(
        "--render",
        default=None,
        metavar="ANALYSIS_JSON",
        help="Renderiza un clip del análisis JSON indicado; no arranca el servidor.",
    )
    parser.add_argument(
        "--clip",
        default=None,
        metavar="CLIP_ID",
        help="Clip a renderizar con --render (por defecto, el primero).",
    )
    parser.add_argument(
        "--video",
        default=None,
        metavar="VIDEO",
        help="Video de origen para --render.",
    )
    parser.add_argument(
        "--render-output",
        default=None,
        metavar="DIR",
        help="Carpeta de salida para --render (por defecto VIRALCLIP_RENDER_DIR).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"viralclip {__version__}",
    )
    return parser


def apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    """Aplica los argumentos de línea de comandos sobre los ajustes del entorno."""

    changes: dict[str, object] = {}
    if args.host:
        changes["host"] = args.host
    if args.port is not None:
        changes["port"] = args.port
    if args.db:
        changes["db_path"] = Path(args.db)
    return replace(settings, **changes) if changes else settings


def _uvicorn_log_config(log_level: str) -> dict[str, Any]:
    """Devuelve la configuración de logging de Uvicorn sin colores.

    Uvicorn decide si usar colores llamando a ``sys.stdout.isatty()`` (y a
    ``sys.stderr.isatty()``) en sus formateadores. En el ejecutable de ventana
    (PyInstaller con ``console=False``) ``sys.stdout`` es ``None`` y esa llamada
    revienta con
    ``AttributeError: 'NoneType' object has no attribute 'isatty'``.
    Fijar ``use_colors=False`` lo evita en cualquier entorno.
    """

    config = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    for formatter in config.get("formatters", {}).values():
        if isinstance(formatter, dict):
            formatter["use_colors"] = False
    level = log_level.upper()
    if level in {"TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logger_cfg = config.get("loggers", {}).get(name)
            if isinstance(logger_cfg, dict):
                logger_cfg["level"] = level
    return config


def _default_server_factory(
    app: object,
    host: str,
    port: int,
    log_level: str,
) -> uvicorn.Server:
    # Blindaje: Uvicorn accede a sys.stdout/sys.stderr al configurar logging.
    from .desktop_window import ensure_streams

    ensure_streams()

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        log_config=_uvicorn_log_config(log_level),
    )
    return uvicorn.Server(config)


def _wait_until_started(server: object, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if getattr(server, "started", False):
            return True
        time.sleep(0.05)
    return bool(getattr(server, "started", False))


def _port_in_use(host: str, port: int) -> bool:
    """Indica si hay ya alguien escuchando en el puerto indicado."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _start_server(
    app: object,
    host: str,
    port: int,
    log_level: str,
    start_timeout: float,
    server_factory: ServerFactory,
) -> tuple[Any, threading.Thread]:
    """Arranca el servidor Uvicorn en un hilo daemon y espera a que esté listo."""

    server = server_factory(app, host, port, log_level)
    thread = threading.Thread(
        target=server.run,
        name="viralclip-server",
        daemon=True,
    )
    thread.start()

    if not _wait_until_started(server, start_timeout):
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("El servidor no arrancó a tiempo.")
    return server, thread


def _stop_server(server: Any, thread: threading.Thread) -> None:
    """Pide al servidor que pare y espera a que termine el hilo."""

    server.should_exit = True
    thread.join(timeout=10)


def serve(
    app: object,
    host: str,
    port: int,
    *,
    log_level: str = "INFO",
    open_browser: bool = True,
    start_timeout: float = DEFAULT_START_TIMEOUT,
    server_factory: ServerFactory = _default_server_factory,
    browser_open: BrowserOpen = webbrowser.open,
) -> None:
    """Arranca el servidor en un hilo, abre el navegador y espera el cierre."""

    server, thread = _start_server(
        app, host, port, log_level, start_timeout, server_factory
    )

    url = build_url(host, port)
    asset_version = AssetVersion().get()
    browser_url = build_url(host, port, asset_version)
    print(f"Editor de Clips Virales {__version__}", flush=True)
    print(f"Interfaz: {url}", flush=True)
    print(f"API docs: {url}/docs", flush=True)
    print("Pulsa Ctrl+C para detener.", flush=True)

    if open_browser:
        browser_open(browser_url)

    try:
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\nDeteniendo...", flush=True)
    finally:
        _stop_server(server, thread)


def serve_window(
    app: object,
    host: str,
    port: int,
    *,
    log_level: str = "INFO",
    start_timeout: float = DEFAULT_START_TIMEOUT,
    server_factory: ServerFactory = _default_server_factory,
    window_runner: Callable[..., int] | None = None,
) -> int:
    """Arranca el servidor y muestra la interfaz en una ventana de escritorio.

    Es el modo por defecto del ejecutable: la app se abre como cualquier otra
    aplicación de Windows, con su propia ventana, sin abrir el navegador.
    """

    from .desktop_window import run_desktop_window

    runner = window_runner or run_desktop_window

    server, thread = _start_server(
        app, host, port, log_level, start_timeout, server_factory
    )

    url = build_url(host, port)
    asset_version = AssetVersion().get()
    window_url = build_url(host, port, asset_version)
    print(f"Editor de Clips Virales {__version__}", flush=True)
    print(f"Interfaz local: {url}", flush=True)
    print(f"API docs: {url}/docs", flush=True)

    try:
        return runner(window_url, on_closed=lambda: _stop_server(server, thread))
    finally:
        _stop_server(server, thread)


def transcribe_command(args: argparse.Namespace, settings: Settings) -> int:
    """Transcribe un archivo local y guarda el JSON normalizado."""

    from .errors import ViralClipError
    from .transcription import WhisperTranscriber

    output = (
        Path(args.output)
        if args.output
        else Path(args.transcribe).with_suffix(".transcript.json")
    )
    try:
        transcriber = WhisperTranscriber(
            model_size=args.model or settings.whisper_model,
            device=settings.whisper_device,
            compute_type=args.compute_type or settings.whisper_compute_type,
            language=args.language or settings.whisper_language,
            model_dir=settings.whisper_model_dir,
            ffmpeg_path=settings.ffmpeg_path,
            beam_size=settings.whisper_beam_size,
            vad=settings.whisper_vad,
            max_segments=settings.max_segments,
        )

        def on_stage(progress: int, stage: str) -> None:
            print(f"[{progress:3d}%] {stage}", flush=True)

        transcript = transcriber.transcribe(args.transcribe, on_stage=on_stage)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            transcript.model_dump_json(indent=2), encoding="utf-8"
        )
    except ViralClipError as exc:
        print(f"Error {exc.code.value}: {exc.message}", file=sys.stderr)
        if exc.detail:
            print(exc.detail, file=sys.stderr)
        return 1
    print(f"Transcripción guardada en {output}", flush=True)
    return 0


def render_command(args: argparse.Namespace, settings: Settings) -> int:
    """Renderiza un clip de un análisis JSON con el FFmpeg del sistema."""

    from uuid import uuid4

    from .errors import ViralClipError
    from .models import AnalysisResult
    from .render import FFmpegRenderer

    analysis_path = Path(args.render).expanduser()
    if not analysis_path.is_file():
        print(f"Error: no existe el análisis {analysis_path}", file=sys.stderr)
        return 1
    if not args.video:
        print("Error: --render requiere --video VIDEO", file=sys.stderr)
        return 1

    try:
        result = AnalysisResult.model_validate_json(
            analysis_path.read_text(encoding="utf-8")
        )
        if not result.clips:
            print("Error: el análisis no contiene clips", file=sys.stderr)
            return 1
        clip = (
            next((item for item in result.clips if item.id == args.clip), None)
            if args.clip
            else result.clips[0]
        )
        if clip is None:
            print(f"Error: no existe el clip {args.clip}", file=sys.stderr)
            return 1

        if args.render_output:
            settings = replace(
                settings, render_dir=Path(args.render_output).expanduser()
            )

        renderer = FFmpegRenderer(settings)

        def on_progress(progress: int, stage: str) -> None:
            print(f"[{progress:3d}%] {stage}", flush=True)

        rendered = renderer.render(
            source_path=args.video,
            clip=clip,
            render_id=uuid4().hex[:12],
            job_id=analysis_path.stem,
            progress=on_progress,
        )
    except ViralClipError as exc:
        print(f"Error {exc.code.value}: {exc.message}", file=sys.stderr)
        if exc.detail:
            print(exc.detail, file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: el análisis no es válido: {exc}", file=sys.stderr)
        return 1

    print(f"Video renderizado en {rendered.output_path}", flush=True)
    if rendered.thumbnail_path:
        print(f"Miniatura en {rendered.thumbnail_path}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    # En el ejecutable de ventana no hay consola: sys.stdout/sys.stderr pueden
    # ser None y romper el formateador de logs de Uvicorn.
    from .desktop_window import ensure_streams

    ensure_streams()

    args = build_parser().parse_args(argv)
    settings = apply_overrides(Settings.from_env(), args)
    if args.transcribe:
        return transcribe_command(args, settings)
    if args.render:
        return render_command(args, settings)

    port = resolve_port(settings.host, settings.port)
    app = create_app(settings=settings)

    if args.no_browser:
        try:
            serve(
                app,
                settings.host,
                port,
                log_level=settings.log_level,
                open_browser=False,
            )
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\nDetenido.")
        return 0

    if args.browser:
        try:
            serve(
                app,
                settings.host,
                port,
                log_level=settings.log_level,
                open_browser=True,
            )
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\nDetenido.")
        return 0

    try:
        return serve_window(
            app,
            settings.host,
            port,
            log_level=settings.log_level,
        )
    except RuntimeError as exc:
        from .desktop_window import show_error

        if settings.port > 0 and _port_in_use(settings.host, settings.port):
            show_error(
                "Editor de Clips Virales",
                "Ya hay otra instancia en ejecución.\n\n"
                f"El puerto {settings.port} ya está ocupado. Cierra la otra "
                "ventana o arranca con otro puerto:\n\n"
                f"    viralclip --port 8765",
            )
        else:
            show_error("Editor de Clips Virales", f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nDetenido.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
