"""Generación y validación de ganchos conversacionales."""

from __future__ import annotations

import re

from .lexicon import (
    ADVICE_PHRASES,
    ADVICE_WORDS,
    CONTROVERSY_PHRASES,
    CONTROVERSY_WORDS,
    CURIOSITY_WORDS,
    EMOTION_WORDS,
    NUMBER_RE,
    STOPWORDS,
    is_corporate,
    normalize_text,
    normalize_token,
    tokenize,
)

MAX_HOOK_WORDS = 10
MAX_HOOK_CHARS = 120
FALLBACK_HOOK = "Esto es lo que nadie te cuenta"

_FIRST_SENTENCE_RE = re.compile(r"^(.+?[.!?])(?:\s|$)")

QUESTION_TEMPLATES = (
    "¿Por qué nadie habla de {kw}?",
    "¿Qué es lo que nadie dice de {kw}?",
    "¿Y si todo lo que sabes de {kw} está mal?",
    "¿Cuál es el error que frena tu {kw}?",
)
NUMBER_TEMPLATES = (
    "El dato que cambia todo sobre {kw}",
    "El número que nadie te cuenta sobre {kw}",
    "Mira el dato clave sobre {kw}",
)
CONTROVERSY_TEMPLATES = (
    "La verdad sobre {kw} que nadie dice",
    "Esto es lo que nadie se atreve a decir",
    "Te están mintiendo sobre {kw}",
)
ADVICE_TEMPLATES = (
    "El error que frena tu {kw}",
    "Deja de hacer esto con {kw}",
    "El truco de {kw} que sí funciona",
)
INFORMAL_TEMPLATES = (
    "Nadie te cuenta esto sobre {kw}",
    "Esto lo cambia todo sobre {kw}",
    "Mira esto antes de seguir",
    "Lo que nadie dice de {kw}",
)
INFORMATIVE_TEMPLATES = (
    "La clave para entender {kw}",
    "Esto explica {kw} en 30 segundos",
    "El dato clave sobre {kw}",
    "Cómo mejorar tu {kw} sin esfuerzo",
)


def count_words(text: str) -> int:
    return len([word for word in text.split() if word.strip()])


def is_valid_hook(hook: str) -> bool:
    """Valida las reglas de retención del gancho."""

    if not hook or not hook.strip():
        return False
    if count_words(hook) > MAX_HOOK_WORDS:
        return False
    if len(hook) > MAX_HOOK_CHARS:
        return False
    return not is_corporate(hook)


def _clean_hook(hook: str) -> str:
    text = " ".join(hook.split()).strip()
    text = text.rstrip(".,;:")
    if not text:
        return FALLBACK_HOOK
    if text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def _truncate_words(text: str, max_words: int = MAX_HOOK_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    words = words[:max_words]
    while words and normalize_token(words[-1].rstrip(".,;:?!")) in STOPWORDS:
        words.pop()
    return " ".join(words).rstrip(".,;:")


def _first_sentence(text: str) -> str:
    match = _FIRST_SENTENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text.strip()


def _has_strong_signal(text: str) -> bool:
    if "?" in text:
        return True
    tokens = {normalize_token(token) for token in tokenize(text)}
    return bool(tokens & (CURIOSITY_WORDS | EMOTION_WORDS | ADVICE_WORDS | CONTROVERSY_WORDS))


def _pick_keyword(keywords: tuple[str, ...], text: str) -> str:
    for keyword in keywords:
        normalized = normalize_token(keyword)
        if (
            len(normalized) >= 4
            and normalized not in STOPWORDS
            and not normalized.isdigit()
            and not is_corporate(normalized)
        ):
            return keyword.lower()
    for token in tokenize(text):
        normalized = normalize_token(token)
        if (
            len(normalized) >= 4
            and normalized not in STOPWORDS
            and not normalized.isdigit()
            and not is_corporate(normalized)
        ):
            return token.lower()
    return "esto"


def _select_templates(platform: str, text: str) -> tuple[str, ...]:
    normalized = normalize_text(text)
    tokens = {normalize_token(token) for token in tokenize(text)}
    has_number = bool(NUMBER_RE.search(text))
    has_controversy = bool(tokens & CONTROVERSY_WORDS) or any(
        phrase in normalized for phrase in CONTROVERSY_PHRASES
    )
    has_advice = bool(tokens & ADVICE_WORDS) or any(
        phrase in normalized for phrase in ADVICE_PHRASES
    )

    if "?" in text:
        return QUESTION_TEMPLATES
    if has_number:
        return NUMBER_TEMPLATES
    if has_controversy:
        return CONTROVERSY_TEMPLATES
    if has_advice:
        return ADVICE_TEMPLATES
    if platform == "shorts":
        return INFORMATIVE_TEMPLATES
    return INFORMAL_TEMPLATES


def generate_hook(
    candidate_text: str,
    keywords: tuple[str, ...] = (),
    platform: str = "tiktok",
) -> str:
    """Genera un gancho determinista de ≤ 10 palabras.

    Prioriza la primera frase si ya es un gancho fuerte. Si no, usa una
    plantilla según las señales del texto y la plataforma.
    """

    text = (candidate_text or "").strip()
    if not text:
        return FALLBACK_HOOK

    if platform not in {"tiktok", "reels", "shorts"}:
        platform = "tiktok"

    first = _first_sentence(text)
    if (
        _has_strong_signal(first)
        and count_words(first) <= MAX_HOOK_WORDS
        and not is_corporate(first)
    ):
        hook = _clean_hook(first)
        if is_valid_hook(hook):
            return hook

    keyword = _pick_keyword(keywords, text)
    templates = _select_templates(platform, text)
    offset = (len(keyword) + len(text)) % len(templates)

    for index in range(len(templates)):
        template = templates[(offset + index) % len(templates)]
        hook = _clean_hook(template.format(kw=keyword))
        hook = _truncate_words(hook, MAX_HOOK_WORDS)
        if is_valid_hook(hook):
            return hook

    return FALLBACK_HOOK


def generate_hooks(
    candidates: list,
    platform: str = "tiktok",
) -> list[str]:
    """Genera un gancho por candidato, preservando el orden."""

    return [
        generate_hook(candidate.text, candidate.keywords, platform)
        for candidate in candidates
    ]
