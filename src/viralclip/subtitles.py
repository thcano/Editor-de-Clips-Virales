"""Subtítulos dinámicos y exportación SRT/VTT."""

from __future__ import annotations

from collections.abc import Iterable

from .analyzer import ClipCandidate
from .errors import InvalidParameterError
from .lexicon import CURIOSITY_WORDS, EMOTION_WORDS, normalize_token
from .models import SubtitleLine, SubtitleWord, Transcript
from .transcript import synthesize_words

EMPHASIS_WORDS = CURIOSITY_WORDS | EMOTION_WORDS
_PUNCTUATION = ".,;:!?¿¡\"'()[]"
_SENTENCE_PUNCTUATION = (".", "!", "?", ";", ":")


def _collect_words(
    transcript: Transcript, start: float, end: float
) -> list[SubtitleWord]:
    """Recolecta palabras dentro del rango del clip, recortando bordes."""

    words: list[SubtitleWord] = []
    seen: set[tuple[str, float, float]] = set()

    for segment in transcript.segments:
        if segment.end <= start or segment.start >= end:
            continue
        segment_words = segment.words or synthesize_words(
            segment.text, segment.start, segment.end
        )
        for word in segment_words:
            word_start = max(word.start, start)
            word_end = min(word.end, end)
            if word_end <= word_start:
                continue
            rounded_start = round(word_start, 3)
            rounded_end = round(word_end, 3)
            key = (word.word, rounded_start, rounded_end)
            if key in seen:
                continue
            seen.add(key)
            words.append(
                SubtitleWord(
                    word=word.word,
                    start=rounded_start,
                    end=rounded_end,
                    highlight=False,
                )
            )

    words.sort(key=lambda item: (item.start, item.end))
    return words


def _should_break(
    line: list[SubtitleWord],
    word: SubtitleWord,
    max_words: int,
    max_chars: int,
    max_gap: float,
) -> bool:
    if len(line) >= max_words:
        return True
    if not line:
        return False

    last = line[-1]
    if word.start - last.end > max_gap:
        return True
    if last.word.rstrip().endswith(_SENTENCE_PUNCTUATION) and len(line) >= 2:
        return True

    current_length = len(" ".join(item.word for item in line))
    if current_length + 1 + len(word.word) > max_chars and len(line) >= 2:
        return True
    return False


def _highlight_words(
    words: list[SubtitleWord],
    keyword_set: set[str],
    max_highlights: int = 2,
) -> list[SubtitleWord]:
    result: list[SubtitleWord] = []
    highlighted = 0
    for word in words:
        normalized = normalize_token(word.word.strip(_PUNCTUATION))
        should_highlight = (
            highlighted < max_highlights
            and bool(normalized)
            and (normalized in keyword_set or normalized in EMPHASIS_WORDS)
        )
        if should_highlight:
            highlighted += 1
        result.append(word.model_copy(update={"highlight": should_highlight}))
    return result


def build_subtitles(
    transcript: Transcript,
    candidate: ClipCandidate,
    *,
    max_words_per_line: int = 5,
    max_chars_per_line: int = 42,
    max_gap: float = 0.6,
    highlight_keywords: Iterable[str] | None = None,
) -> list[SubtitleLine]:
    """Construye líneas de subtítulo de 4–5 palabras dentro del clip."""

    if not 1 <= max_words_per_line <= 5:
        raise InvalidParameterError("max_words_per_line debe estar entre 1 y 5")
    if max_chars_per_line < 10:
        raise InvalidParameterError("max_chars_per_line debe ser al menos 10")
    if max_gap < 0:
        raise InvalidParameterError("max_gap no puede ser negativo")

    words = _collect_words(
        transcript, candidate.start_seconds, candidate.end_seconds
    )
    if not words:
        return []

    keywords = highlight_keywords if highlight_keywords is not None else candidate.keywords
    keyword_set = {normalize_token(keyword) for keyword in keywords}

    grouped: list[list[SubtitleWord]] = []
    current: list[SubtitleWord] = []
    for word in words:
        if current and _should_break(
            current, word, max_words_per_line, max_chars_per_line, max_gap
        ):
            grouped.append(current)
            current = []
        current.append(word)
    if current:
        grouped.append(current)

    lines: list[SubtitleLine] = []
    for index, line_words in enumerate(grouped, start=1):
        highlighted = _highlight_words(line_words, keyword_set)
        lines.append(
            SubtitleLine(
                index=index,
                start=highlighted[0].start,
                end=highlighted[-1].end,
                text=" ".join(word.word for word in highlighted),
                words=highlighted,
            )
        )
    return lines


def _format_timestamp(seconds: float, separator: str) -> str:
    total_ms = int(round(max(0.0, float(seconds)) * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def to_srt(lines: list[SubtitleLine]) -> str:
    """Exporta líneas a SubRip (SRT)."""

    if not lines:
        return ""
    blocks = [
        (
            f"{line.index}\n"
            f"{_format_timestamp(line.start, ',')} --> "
            f"{_format_timestamp(line.end, ',')}\n"
            f"{line.text}"
        )
        for line in lines
    ]
    return "\n\n".join(blocks) + "\n"


def to_vtt(lines: list[SubtitleLine]) -> str:
    """Exporta líneas a WebVTT."""

    blocks = ["WEBVTT"]
    for line in lines:
        blocks.append("")
        blocks.append(
            f"{_format_timestamp(line.start, '.')} --> "
            f"{_format_timestamp(line.end, '.')}"
        )
        blocks.append(line.text)
    return "\n".join(blocks) + "\n"
