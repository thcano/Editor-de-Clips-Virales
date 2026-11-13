from __future__ import annotations

from viralclip.llm.prompts import (
    SYSTEM_PROMPT,
    build_hook_prompt,
    parse_hook_response,
)


def test_system_prompt_has_guardrails() -> None:
    assert "TikTok" in SYSTEM_PROMPT
    assert "sin inventar datos" in SYSTEM_PROMPT
    assert "sin comillas" in SYSTEM_PROMPT


def test_build_hook_prompt_contains_context() -> None:
    prompt = build_hook_prompt(
        "Nadie te cuenta esto sobre vender.",
        ("ventas", "vender"),
        "shorts",
    )

    assert "YouTube Shorts" in prompt
    assert "ventas, vender" in prompt
    assert "Máximo de palabras: 10" in prompt
    assert "Nadie te cuenta esto sobre vender." in prompt


def test_build_hook_prompt_without_keywords() -> None:
    prompt = build_hook_prompt("Texto", (), "tiktok")

    assert "Palabras clave: ninguna" in prompt


def test_build_hook_prompt_truncates_long_text() -> None:
    prompt = build_hook_prompt("palabra " * 1_000, ("clave",), "tiktok")

    body = prompt.split("Texto del clip:\n", 1)[1].split("\n\n", 1)[0]
    assert len(body) <= 1_500


def test_build_hook_prompt_normalizes_whitespace() -> None:
    prompt = build_hook_prompt("Hola   mundo\n\n esto", (), "tiktok")

    assert "Hola mundo esto" in prompt


def test_parse_plain_response() -> None:
    assert parse_hook_response("Nadie te cuenta esto sobre vender") == (
        "Nadie te cuenta esto sobre vender"
    )


def test_parse_response_with_label_quotes_and_bullets() -> None:
    raw = 'Gancho: "Nadie te cuenta esto sobre vender."'

    assert parse_hook_response(raw) == "Nadie te cuenta esto sobre vender"

    raw_bullet = "- El error que frena tus ventas"
    assert parse_hook_response(raw_bullet) == "El error que frena tus ventas"


def test_parse_uses_first_valid_line() -> None:
    raw = (
        "Claro, aquí tienes varias opciones de gancho para tu clip viral:\n\n"
        "Gancho: El error que frena tus ventas\n"
    )

    assert parse_hook_response(raw) == "El error que frena tus ventas"


def test_parse_skips_invalid_lines() -> None:
    raw = (
        "uno dos tres cuatro cinco seis siete ocho nueve diez once\n"
        "El error que frena tus ventas\n"
    )

    assert parse_hook_response(raw) == "El error que frena tus ventas"


def test_parse_rejects_corporate_language() -> None:
    assert parse_hook_response("Optimizar la sinergia del pipeline") is None


def test_parse_rejects_empty_or_none() -> None:
    assert parse_hook_response(None) is None
    assert parse_hook_response("") is None
    assert parse_hook_response("   \n\n  ") is None


def test_parse_rejects_long_response() -> None:
    raw = "uno dos tres cuatro cinco seis siete ocho nueve diez once"

    assert parse_hook_response(raw) is None


def test_parse_strips_trailing_punctuation() -> None:
    assert parse_hook_response("El error que frena tus ventas.") == (
        "El error que frena tus ventas"
    )
