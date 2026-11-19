"""Tests de regresión del crash de arranque sin consola.

Reproduce el fallo reportado por el usuario:

    AttributeError: 'NoneType' object has no attribute 'isatty'
      at uvicorn/logging.py, in __init__
    ValueError: Unable to configure formatter 'default'

En los builds de PyInstaller con ``console=False`` no hay consola, por lo que
``sys.stdout`` y ``sys.stderr`` son ``None``.
"""

from __future__ import annotations

import sys

import pytest

from viralclip import cli, desktop_window


def test_ensure_streams_replaces_none_streams(monkeypatch) -> None:
    """``ensure_streams`` evita que ``sys.stdout``/``sys.stderr`` sigan a None."""

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    desktop_window.ensure_streams()

    assert sys.stdout is not None
    assert sys.stderr is not None
    assert sys.stdout.isatty() is False
    assert sys.stderr.isatty() is False


def test_null_stream_supports_common_operations() -> None:
    stream = desktop_window._NullStream()

    assert stream.write("texto") == 5
    assert stream.flush() is None
    assert stream.isatty() is False
    assert stream.encoding == "utf-8"


def test_uvicorn_config_builds_without_stdout(monkeypatch) -> None:
    """El ``Config`` de Uvicorn se construye aunque ``sys.stdout`` sea None.

    Este es el test que reproduce exactamente el traceback del usuario.
    """

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    desktop_window.ensure_streams()

    server = cli._default_server_factory(object(), "127.0.0.1", 8123, "info")

    assert server is not None


def test_uvicorn_log_config_disables_colors() -> None:
    config = cli._uvicorn_log_config("info")

    assert config["formatters"]["default"]["use_colors"] is False
    assert config["formatters"]["access"]["use_colors"] is False
    assert config["loggers"]["uvicorn"]["level"] == "INFO"


def test_redirect_output_to_log_works_without_console(tmp_path, monkeypatch) -> None:
    """Sin consola, la salida va al log y stdout nunca queda a None."""

    log_path = tmp_path / "viralclip.log"
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    desktop_window.redirect_output_to_log(log_path)

    assert sys.stdout is not None
    assert sys.stderr is not None
    print("mensaje sin consola")
    sys.stdout.flush()

    assert "mensaje sin consola" in log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("argv", [["--version"], ["--help"]])
def test_cli_main_survives_without_stdout(monkeypatch, argv, capsys) -> None:
    """``cli.main`` no se rompe si no hay consola."""

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    with pytest.raises(SystemExit):
        cli.main(argv)
