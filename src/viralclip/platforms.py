"""Metadatos por plataforma: título, descripción y hashtags."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .analyzer import ClipCandidate
from .errors import InvalidParameterError
from .lexicon import STOPWORDS, normalize_text

SUPPORTED_PLATFORMS = ("tiktok", "reels", "shorts")

BASE_HASHTAGS: dict[str, list[str]] = {
    "tiktok": ["#fyp", "#parati", "#viral", "#tiktok"],
    "reels": ["#reels", "#instagram", "#viral", "#explore"],
    "shorts": ["#shorts", "#youtube", "#viral", "#youtubeshorts"],
}

CTAS: dict[str, str] = {
    "tiktok": "Guarda este clip y compártelo con alguien que lo necesite.",
    "reels": "Guarda esto para tu próxima publicación.",
    "shorts": "Suscríbete para más clips como este.",
}

MAX_HASHTAGS = 8
MAX_TITLE_CHARS = 120
MAX_DESCRIPTION_CHARS = 500
MAX_SUMMARY_CHARS = 220


@dataclass(frozen=True)
class ClipMetadata:
    title: str
    description: str
    hashtags: list[str]


def _to_hashtag(keyword: str) -> str | None:
    normalized = normalize_text(keyword)
    clean = re.sub(r"[^a-z0-9]", "", normalized)
    if len(clean) < 4 or clean in STOPWORDS:
        return None
    return f"#{clean}"


def _build_title(hook: str) -> str:
    title = " ".join((hook or "").split()).strip().rstrip(".")
    if not title:
        title = "Clip viral"
    if len(title) > MAX_TITLE_CHARS:
        title = title[: MAX_TITLE_CHARS - 3].rstrip() + "..."
    return title


def _build_description(candidate: ClipCandidate, platform: str) -> str:
    text = " ".join(candidate.text.split()).strip()
    if text:
        summary = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    else:
        summary = ""
    summary = summary.strip()
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[:MAX_SUMMARY_CHARS].rsplit(" ", 1)[0].strip()

    cta = CTAS[platform]
    description = f"{summary} {cta}".strip() if summary else cta
    return description[:MAX_DESCRIPTION_CHARS]


def _build_hashtags(candidate: ClipCandidate, platform: str) -> list[str]:
    tags = list(BASE_HASHTAGS[platform])

    for keyword in candidate.keywords:
        tag = _to_hashtag(keyword)
        if tag and tag not in tags:
            tags.append(tag)

    signals = candidate.signals
    if signals.get("advice", 0.0) >= 0.5:
        tags.extend(["#consejos", "#tips"])
    if signals.get("numbers", 0.0) >= 0.5:
        tags.append("#datos")
    if signals.get("story", 0.0) >= 0.5:
        tags.append("#historia")
    if signals.get("controversy", 0.0) >= 0.5:
        tags.append("#opinion")

    unique: list[str] = []
    for tag in tags:
        if tag not in unique:
            unique.append(tag)
    return unique[:MAX_HASHTAGS]


def build_metadata(
    candidate: ClipCandidate,
    hook: str,
    platform: str,
) -> ClipMetadata:
    """Construye título, descripción y hashtags para una plataforma."""

    if platform not in SUPPORTED_PLATFORMS:
        raise InvalidParameterError(
            f"Plataforma no soportada: {platform!r}. "
            f"Usa una de: {', '.join(SUPPORTED_PLATFORMS)}"
        )

    return ClipMetadata(
        title=_build_title(hook),
        description=_build_description(candidate, platform),
        hashtags=_build_hashtags(candidate, platform),
    )
