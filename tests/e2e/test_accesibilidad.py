"""Auditoría de accesibilidad con axe-core sobre la interfaz real."""

from __future__ import annotations

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect

BLOCKING_IMPACTS = {"critical", "serious"}


def test_sin_violaciones_graves(page: Page, live_server: str) -> None:
    page.goto(live_server)
    expect(page.get_by_role("heading", name="Editor de Clips Virales")).to_be_visible()

    results = Axe().run(page)
    blocking = [
        violation
        for violation in results.response["violations"]
        if violation.get("impact") in BLOCKING_IMPACTS
    ]

    assert not blocking, results.generate_report()


def test_dialogo_accesible_por_teclado(page: Page, live_server: str) -> None:
    page.goto(live_server)

    page.keyboard.press("Tab")
    assert "skip-link" in page.evaluate("document.activeElement.className")

    page.get_by_role("button", name="Ajustes").click()
    expect(page.locator("#settings-dialog")).to_be_visible()
    expect(page.locator("#api-key")).to_be_focused()

    page.keyboard.press("Escape")
    expect(page.locator("#settings-dialog")).to_be_hidden()
