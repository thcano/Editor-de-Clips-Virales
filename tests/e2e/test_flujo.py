"""Flujo E2E completo en Chromium real."""

from __future__ import annotations

from playwright.sync_api import Page, expect


def _run_sample_analysis(page: Page, live_server: str) -> None:
    page.goto(live_server)
    expect(page.get_by_role("heading", name="Editor de Clips Virales")).to_be_visible()
    page.get_by_role("button", name="Cargar ejemplo").click()
    page.get_by_role("button", name="Analizar transcripción").click()
    expect(page.locator(".clip-card").first).to_be_visible(timeout=20_000)


def test_flujo_de_analisis_y_detalle(page: Page, live_server: str) -> None:
    _run_sample_analysis(page, live_server)

    cards = page.locator(".clip-card")
    assert cards.count() >= 1

    first = cards.first
    expect(first.locator(".clip-hook")).not_to_be_empty()
    expect(first.locator(".clip-time")).to_contain_text("–")
    expect(first.locator(".clip-caption")).not_to_be_empty()
    expect(first.locator(".hashtags li").first).to_be_visible()
    expect(first.locator(".clip-srt")).to_be_visible()

    expect(page.locator("#detail-meta")).to_contain_text("heuristic")


def test_flags_ocultan_y_restauran_exportaciones(page: Page, live_server: str) -> None:
    _run_sample_analysis(page, live_server)

    srt_link = page.locator('#export-actions [data-export="srt"]')
    vtt_link = page.locator('#export-actions [data-export="vtt"]')
    expect(srt_link).to_be_visible()
    expect(vtt_link).to_be_visible()

    page.get_by_role("button", name="Ajustes").click()
    expect(page.locator("#settings-dialog")).to_be_visible()
    expect(page.locator("#api-key")).to_be_focused()

    flag_item = page.locator(".flag-item", has_text="Exportar subtítulos SRT/VTT")
    checkbox = flag_item.locator('input[type="checkbox"]')
    expect(checkbox).to_be_checked()
    checkbox.uncheck()
    expect(page.locator("#flags-status")).to_contain_text("Función actualizada.")

    page.keyboard.press("Escape")
    expect(page.locator("#settings-dialog")).to_be_hidden()
    expect(srt_link).to_be_hidden()
    expect(vtt_link).to_be_hidden()

    page.get_by_role("button", name="Ajustes").click()
    flag_item = page.locator(".flag-item", has_text="Exportar subtítulos SRT/VTT")
    flag_item.locator('input[type="checkbox"]').check()
    expect(page.locator("#flags-status")).to_contain_text("Función actualizada.")
    page.keyboard.press("Escape")

    expect(srt_link).to_be_visible()
    expect(vtt_link).to_be_visible()


def test_historial_permite_borrar(page: Page, live_server: str) -> None:
    _run_sample_analysis(page, live_server)

    items = page.locator(".history-item")
    expect(items.first).to_be_visible(timeout=10_000)
    assert items.count() == 1

    page.get_by_role("button", name="Abrir").first.click()
    expect(page.locator("#detail")).to_be_visible()

    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Borrar", exact=True).first.click()

    expect(page.locator(".history-empty")).to_be_visible(timeout=10_000)
    expect(page.locator("#detail")).to_be_hidden()
