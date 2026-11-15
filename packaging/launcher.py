"""Punto de entrada del ejecutable empaquetado con PyInstaller."""

from __future__ import annotations

import sys


def _configure_output() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _configure_output()
    from viralclip.desktop import prepare_environment
    from viralclip.cli import main as cli_main

    prepare_environment()
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
