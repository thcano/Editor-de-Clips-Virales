"""Punto de entrada del ejecutable empaquetado con PyInstaller.

El ejecutable es una aplicación de ventana: no muestra consola. Para no perder
los mensajes, ``stdout`` y ``stderr`` se redirigen a un fichero de log en el
directorio de datos del usuario.

Orden de arranque (importante en builds sin consola):

1. se garantiza que ``sys.stdout``/``sys.stderr`` no sean ``None``,
2. se redirige la salida al log del usuario,
3. solo entonces se importa el resto de la app (Uvicorn configura logging al
   construirse el ``Config`` y necesita ``sys.stdout.isatty()``).
"""

from __future__ import annotations

import os
import sys


def _configure_output() -> None:
    """Reconfigura la salida si hay consola y garantiza que no sea ``None``."""

    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover - depende del flujo de salida
            pass
    if sys.stderr is not None and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover - depende del flujo de salida
            pass

    # En builds sin consola PyInstaller deja ambos flujos a None; el formateador
    # de logs de Uvicorn llama a sys.stdout.isatty() y fallaría.
    try:
        from viralclip.desktop_window import ensure_streams

        ensure_streams()
    except Exception:  # pragma: no cover - último recurso
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def _redirect_to_log() -> None:
    """Envía la salida al log del usuario; nunca debe impedir el arranque."""

    try:
        from viralclip.desktop import default_data_dir
        from viralclip.desktop_window import redirect_output_to_log

        redirect_output_to_log(default_data_dir(os.environ) / "viralclip.log")
    except Exception:  # pragma: no cover - nunca debe impedir el arranque
        try:
            import traceback

            traceback.print_exc()
        except Exception:
            pass
        _configure_output()


def main() -> int:
    _configure_output()
    _redirect_to_log()

    from viralclip.cli import main as cli_main
    from viralclip.desktop import prepare_environment

    prepare_environment()
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
