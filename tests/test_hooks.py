from __future__ import annotations

from viralclip.hooks import FALLBACK_HOOK, count_words, generate_hook, is_valid_hook
from viralclip.lexicon import is_corporate


def test_hook_rules_across_platforms() -> None:
    cases = [
        (
            "Nadie te cuenta esto: el 80% de las ventas se pierde por no preguntar.",
            ("ventas",),
            "tiktok",
        ),
        (
            "Tienes que dejar de hablar y empezar a escuchar.",
            ("clientes",),
            "reels",
        ),
        (
            "La clave está en preguntar y escuchar a tu cliente.",
            ("clave",),
            "shorts",
        ),
        ("", (), "tiktok"),
    ]

    for text, keywords, platform in cases:
        hook = generate_hook(text, keywords, platform)
        assert is_valid_hook(hook)
        assert count_words(hook) <= 10
        assert not is_corporate(hook)


def test_question_first_sentence_is_used() -> None:
    hook = generate_hook("¿Por qué nadie habla de vender?", ("vender",), "tiktok")

    assert hook.lower().startswith("¿por qué")
    assert is_valid_hook(hook)


def test_corporate_sentence_is_not_used() -> None:
    hook = generate_hook(
        "Vamos a optimizar la sinergia y el engagement del pipeline.",
        ("ventas",),
        "tiktok",
    )

    assert not is_corporate(hook)
    assert "sinergia" not in hook.lower()


def test_platform_difference() -> None:
    text = (
        "En este video hablamos de temas relacionados con el trabajo diario "
        "y las rutinas de oficina."
    )

    tiktok = generate_hook(text, ("video",), "tiktok")
    shorts = generate_hook(text, ("video",), "shorts")

    assert tiktok != shorts


def test_fallback_for_empty_text() -> None:
    assert generate_hook("", (), "tiktok") == FALLBACK_HOOK
    assert is_valid_hook(FALLBACK_HOOK)


def test_invalid_hooks_are_rejected() -> None:
    assert not is_valid_hook("")
    assert not is_valid_hook("uno dos tres cuatro cinco seis siete ocho nueve diez once")
    assert not is_valid_hook("Optimizar la sinergia del pipeline")


def test_long_first_sentence_is_truncated_or_replaced() -> None:
    text = (
        "Esta es una frase larga que tiene muchísimas palabras y no debería "
        "usarse completa como gancho."
    )

    hook = generate_hook(text, ("frase",), "tiktok")

    assert count_words(hook) <= 10
    assert is_valid_hook(hook)


def test_generation_is_deterministic() -> None:
    text = "Nadie te cuenta esto: el 80% de las ventas se pierde por no preguntar."

    assert generate_hook(text, ("ventas",), "tiktok") == generate_hook(
        text, ("ventas",), "tiktok"
    )
