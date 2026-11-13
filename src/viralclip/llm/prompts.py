"""Prompts y parseo de respuestas para los ganchos generados por Ollama."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from ..hooks import MAX_HOOK_WORDS, is_valid_hook

MAX_PROMPT_CHARS = 1_500

PLATFORM_LABELS: dict[str, str] = {
    "tiktok": "TikTok",
    "reels": "Instagram Reels",
    "shorts": "YouTube Shorts",
}

SYSTEM_PROMPT = (
    "Eres un guionista experto en clips virales para TikTok, Reels y YouTube Shorts. "
    "Escribes ganchos conversacionales, directos y sin lenguaje corporativo. "
    "Respondes solo con el gancho final: una línea, sin comillas, sin etiquetas, "
    "sin explicaciones y sin inventar datos que no aparezcan en el texto."
)

_LIST_PREFIX_RE = re.compile(r"^(?:[-*•]|\d+[.)])\s*")
_LABEL_PREFIX_RE = re.compile(
    r"^(?:gancho|hook|t[ií]tulo|title|respuesta)\s*:\s*", re.IGNORECASE
)
_QUOTES = "\"'“”‘’«»"


def build_hook_prompt(
    candidate_text: str,
    keywords: Iterable[str] = (),
    platform: str = "tiktok",
    *,
    max_words: int = MAX_HOOK_WORDS,
) -> str:
    """Construye el prompt de usuario para redactar un gancho."""

    text = " ".join((candidate_text or "").split())[:MAX_PROMPT_CHARS]
    keyword_list = [keyword for keyword in keywords if keyword]
    keyword_text = ", ".join(keyword_list) if keyword_list else "ninguna"
    label = PLATFORM_LABELS.get(platform, "TikTok")

    return (
        f"Plataforma: {label}\n"
        f"Palabras clave: {keyword_text}\n"
        f"Máximo de palabras: {max_words}\n\n"
        "Texto del clip:\n"
        f"{text}\n\n"
        "Escribe un gancho que detenga el scroll en los primeros 3 segundos.\n"
        "Reglas:\n"
        f"- Máximo {max_words} palabras y una sola línea.\n"
        "- Tono conversacional, sin lenguaje corporativo.\n"
        "- No inventes cifras, nombres ni hechos que no estén en el texto.\n"
        "- No uses comillas, viñetas ni la etiqueta 'Gancho:'.\n"
        "- Devuelve únicamente el gancho."
    )


def parse_hook_response(raw: str | None) -> str | None:
    """Extrae y valida el primer gancho válido de una respuesta del LLM.

    Devuelve ``None`` si no hay ninguna línea que cumpla las reglas; el
    pipeline usará entonces el gancho heurístico.
    """

    if not raw:
        return None

    for line in raw.splitlines():
        candidate = line.strip()
        if not candidate:
            continue

        candidate = _LIST_PREFIX_RE.sub("", candidate)
        candidate = _LABEL_PREFIX_RE.sub("", candidate)
        candidate = candidate.strip().strip(_QUOTES).strip()
        candidate = " ".join(candidate.split()).rstrip(".,;:")
        if not candidate:
            continue

        if is_valid_hook(candidate):
            return candidate

    return None


JUDGE_SYSTEM_PROMPT = (
    "Eres un evaluador de ganchos para videos cortos. "
    "Respondes solo con un objeto JSON válido, sin explicaciones ni texto extra."
)

_JUDGE_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_JUDGE_KEYS = ("clarity", "curiosity", "fidelity")


def build_judge_prompt(hook: str, source_text: str) -> str:
    """Construye el prompt del juez LLM opcional."""

    text = " ".join((source_text or "").split())[:MAX_PROMPT_CHARS]
    return (
        "Evalúa el siguiente gancho frente al texto del clip.\n"
        "- clarity: se entiende en una sola lectura (1–5).\n"
        "- curiosity: dan ganas de seguir viendo (1–5).\n"
        "- fidelity: no inventa datos y representa el texto (1–5).\n\n"
        'Responde solo JSON: {"clarity": 1, "curiosity": 1, "fidelity": 1}\n\n'
        f"Gancho: {hook}\n\n"
        "Texto del clip:\n"
        f"{text}"
    )


def parse_judge_response(raw: str | None) -> dict[str, float] | None:
    """Valida el JSON del juez y normaliza la puntuación a 0–1.

    Devuelve ``None`` si falta el JSON, si alguna clave no es numérica o si
    algún valor queda fuera de 1–5.
    """

    if not raw:
        return None
    match = _JUDGE_JSON_RE.search(raw)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    result: dict[str, float] = {}
    for key in _JUDGE_KEYS:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if not 1 <= float(value) <= 5:
            return None
        result[key] = float(value)

    result["score"] = round(sum(result[key] for key in _JUDGE_KEYS) / 15.0, 4)
    return result
