"""Infraestructura E2E: servidor real + Chromium de Playwright."""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright no está instalado; se omiten las pruebas E2E.",
)
pytest.importorskip(
    "axe_playwright_python.sync_playwright",
    reason="axe-playwright-python no está instalado.",
)

from playwright.sync_api import sync_playwright  # noqa: E402

from viralclip.api.app import create_app  # noqa: E402
from viralclip.config import Settings  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def live_server(tmp_path):
    settings = Settings(db_path=tmp_path / "e2e.db", llm_enabled=False, max_clips=8)
    app = create_app(settings=settings)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    if not server.started:
        pytest.skip("El servidor E2E no arrancó.")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)
    app.state.storage.close()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - depende del entorno
            pytest.skip(f"Chromium no disponible: {exc}")
        yield chromium
        chromium.close()


@pytest.fixture()
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()
