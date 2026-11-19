"""Tests del módulo de ventana de escritorio."""

from __future__ import annotations

import sys

import pytest

from viralclip import desktop_window


def test_webview_available_returns_bool() -> None:
    assert isinstance(desktop_window.webview_available(), bool)


def test_show_error_falls_back_to_stderr(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    desktop_window.show_error("Titulo", "Mensaje")
    captured = capsys.readouterr()
    assert "Titulo" in captured.err
    assert "Mensaje" in captured.err


def test_run_desktop_window_creates_window_with_kinetic_background(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeEvents:
        def __init__(self) -> None:
            self.closed: list = []

        def __iadd__(self, handler):
            self.closed.append(handler)
            return self

    class FakeWindow:
        def __init__(self) -> None:
            self.events = FakeEvents()

    def fake_create_window(title, url, **kwargs):
        calls.append({"title": title, "url": url, **kwargs})
        return FakeWindow()

    closed: list[bool] = []

    class FakeWebview:
        @staticmethod
        def create_window(title, url, **kwargs):
            return fake_create_window(title, url, **kwargs)

        @staticmethod
        def start():
            return None

    monkeypatch.setitem(sys.modules, "webview", FakeWebview)

    code = desktop_window.run_desktop_window(
        "http://127.0.0.1:8000/?v=abc123",
        on_closed=lambda: closed.append(True),
    )

    assert code == 0
    assert len(calls) == 1
    assert calls[0]["title"] == "Editor de Clips Virales"
    assert calls[0]["url"] == "http://127.0.0.1:8000/?v=abc123"
    assert calls[0]["background_color"] == "#0A0A0A"
    assert calls[0]["resizable"] is True
    assert closed == [True]


def test_run_desktop_window_reports_missing_webview(monkeypatch) -> None:
    """Si pywebview no está, se avisa y se devuelve un código de error."""

    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        desktop_window,
        "show_error",
        lambda title, message: errors.append((title, message)),
    )
    # ``None`` en sys.modules hace que ``import webview`` lance ImportError.
    monkeypatch.setitem(sys.modules, "webview", None)

    code = desktop_window.run_desktop_window("http://127.0.0.1:8000/")

    assert code == 1
    assert len(errors) == 1
    assert "Editor de Clips Virales" in errors[0][0]


def test_redirect_output_to_log_writes_to_file(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "logs" / "viralclip.log"
    original_stdout = sys.stdout

    desktop_window.redirect_output_to_log(log_path)
    try:
        print("mensaje de prueba")
    finally:
        sys.stdout = original_stdout

    assert log_path.exists()
    assert "mensaje de prueba" in log_path.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_window_constants_match_kinetic_palette() -> None:
    assert desktop_window.WINDOW_BACKGROUND == "#0A0A0A"
    assert desktop_window.WINDOW_TITLE == "Editor de Clips Virales"
