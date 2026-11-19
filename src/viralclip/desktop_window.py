"""Ventana de escritorio nativa para el Editor de Clips Virales.

El backend sigue siendo HTTP local (FastAPI + Uvicorn en ``127.0.0.1``), pero la
interfaz se muestra en una **ventana del sistema**, como cualquier otra
aplicación de escritorio, en lugar de abrirse en el navegador del sistema.

La ventana usa `pywebview`, que en Windows se apoya en **WebView2** (Edge
Chromium embebido). WebView2 viene instalado de serie en Windows 11 y en las
actualizaciones recientes de Windows 10; si faltara, `pywebview` recurre a otros
motores o la app avisa al usuario.

Flujo:

1. se arranca el servidor Uvicorn en un hilo daemon,
2. se abre la ventana apuntando a la URL versionada de la interfaz,
3. al cerrar la ventana se detiene el servidor y termina la app.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WINDOW_TITLE = "Editor de Clips Virales"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 880
WINDOW_MIN_SIZE = (940, 620)
#: Color de fondo de la ventana, igual al ``--bg`` del tema Kinetic Typography.
WINDOW_BACKGROUND = "#0A0A0A"


def webview_available() -> bool:
    """Indica si ``pywebview`` puede importarse en este entorno."""

    try:
        import webview  # noqa: F401
    except Exception:  # pragma: no cover - depende del entorno
        return False
    return True


def show_error(title: str, message: str) -> None:
    """Muestra un diálogo nativo de error (Windows) o escribe en stderr."""

    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
            return
        except Exception:  # pragma: no cover - depende del entorno
            logger.exception("no se pudo mostrar el dialogo de error")
    print(f"{title}: {message}", file=sys.stderr)


class _NullStream:
    """Descriptor de escritura que se descarta.

    Sustituye a ``sys.stdout``/``sys.stderr`` cuando la app corre sin consola
    y no hay ningún destino donde escribir. Existe para que librerías que
    llaman a ``sys.stdout.isatty()`` (como el formateador de Uvicorn) no
    fallen con ``AttributeError: 'NoneType' object has no attribute 'isatty'``.
    """

    def write(self, data: str) -> int:
        return len(data)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise OSError("flujo descartado")

    @property
    def encoding(self) -> str:
        return "utf-8"


def ensure_streams() -> None:
    """Garantiza que ``sys.stdout`` y ``sys.stderr`` no sean ``None``.

    En los builds de PyInstaller con ``console=False`` no hay consola, y el
    intérprete deja ambos atributos a ``None``. Cualquier librería que los use
    (el formateador de logs de Uvicorn, ``print``, ``traceback``...) falla con
    ``AttributeError``. Esta función instala un flujo descartable para que el
    arranque nunca se rompa.
    """

    if sys.stdout is None:
        sys.stdout = _NullStream()  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = _NullStream()  # type: ignore[assignment]


def redirect_output_to_log(log_path: Path) -> None:
    """Envía ``stdout`` y ``stderr`` a un fichero de log.

    En el ejecutable de ventana no hay consola (PyInstaller deja ``sys.stdout``
    a ``None``), así que sin esto los mensajes se perderían. El log vive en el
    directorio de datos del usuario.
    """

    console_out = sys.stdout
    console_err = sys.stderr
    stream = None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(log_path, "a", encoding="utf-8", errors="replace")  # noqa: SIM115
    except OSError:
        logger.exception("no se pudo abrir el fichero de log %s", log_path)

    class _Tee:
        """Escribe a la consola (si la hay) y al fichero de log."""

        def __init__(self, console: Any) -> None:
            self._console = console
            self._lock = threading.Lock()

        def write(self, data: str) -> int:
            with self._lock:
                if self._console is not None:
                    try:
                        self._console.write(data)
                    except Exception:
                        pass
                if stream is not None:
                    try:
                        stream.write(data)
                        stream.flush()
                    except Exception:
                        pass
            return len(data)

        def flush(self) -> None:
            with self._lock:
                if self._console is not None:
                    try:
                        self._console.flush()
                    except Exception:
                        pass
                if stream is not None:
                    try:
                        stream.flush()
                    except Exception:
                        pass

        def isatty(self) -> bool:
            return False

    sys.stdout = _Tee(console_out)  # type: ignore[assignment]
    sys.stderr = _Tee(console_err)  # type: ignore[assignment]
    ensure_streams()


def run_desktop_window(
    url: str,
    *,
    title: str = WINDOW_TITLE,
    width: int = WINDOW_WIDTH,
    height: int = WINDOW_HEIGHT,
    min_size: tuple[int, int] = WINDOW_MIN_SIZE,
    background_color: str = WINDOW_BACKGROUND,
    on_closed: Callable[[], None] | None = None,
    webview_factory: Callable[..., Any] | None = None,
) -> int:
    """Abre la ventana nativa y bloquea hasta que el usuario la cierre.

    Devuelve ``0`` si la ventana se cerró con normalidad y ``1`` si no se pudo
    abrir.
    """

    try:
        import webview as webview_module
    except Exception:
        logger.exception("pywebview no esta disponible")
        show_error(
            WINDOW_TITLE,
            "No se pudo cargar el motor de la ventana de escritorio.\n\n"
            "Reinstala la aplicacion o ejecuta 'viralclip --browser' para usar "
            "la interfaz en el navegador.",
        )
        return 1

    factory = webview_factory or webview_module.create_window

    try:
        window = factory(
            title,
            url,
            width=width,
            height=height,
            min_size=min_size,
            resizable=True,
            background_color=background_color,
            text_select=True,
        )
    except Exception:
        logger.exception("no se pudo crear la ventana")
        show_error(WINDOW_TITLE, "No se pudo abrir la ventana de la aplicacion.")
        return 1

    if window is None:
        logger.error("create_window devolvio None")
        show_error(WINDOW_TITLE, "No se pudo abrir la ventana de la aplicacion.")
        return 1

    def _cleanup() -> None:
        if on_closed is not None:
            try:
                on_closed()
            except Exception:  # pragma: no cover - depende del entorno
                logger.exception("error en el cierre de la ventana")

    try:
        window.events.closed += _cleanup
    except Exception:  # pragma: no cover - depende de la versión de pywebview
        logger.debug("no se pudo suscribir al evento closed", exc_info=True)

    try:
        webview_module.start()
    except Exception:
        logger.exception("la ventana se cerro con error")
        _cleanup()
        return 1

    _cleanup()
    return 0
