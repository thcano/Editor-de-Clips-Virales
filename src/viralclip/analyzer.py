"""Motor de análisis: ventanas candidatas, señales, scoring y selección."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .errors import InvalidParameterError
from .lexicon import (
    ADVICE_PHRASES,
    ADVICE_WORDS,
    CONTROVERSY_PHRASES,
    CONTROVERSY_WORDS,
    CURIOSITY_PHRASES,
    CURIOSITY_WORDS,
    EMOTION_WORDS,
    FILLER_PHRASES,
    FILLER_WORDS,
    INTERROGATIVES,
    NUMBER_PHRASES,
    NUMBER_RE,
    NUMBER_WORDS,
    STOPWORDS,
    STORY_PHRASES,
    STORY_WORDS,
    normalize_text,
    normalize_token,
    tokenize,
)
from .models import Segment, Transcript
from .timeutils import format_timecode
from .transcript import synthesize_words

MAX_WINDOWS = 3_000
MAX_ANCHORS = 2_000
MAX_WINDOW_CHARS = 8_000

FEATURE_WEIGHTS: dict[str, float] = {
    "question": 1.6,
    "curiosity": 1.2,
    "numbers": 1.0,
    "emotion": 1.1,
    "story": 0.9,
    "advice": 1.0,
    "controversy": 1.0,
    "density": 0.6,
    "completeness": 0.4,
    "keyword_density": 0.5,
    "filler": -0.9,
    "repetition": -0.6,
}

FEATURE_LABELS: dict[str, str] = {
    "question": "pregunta directa",
    "curiosity": "curiosidad",
    "numbers": "dato numérico",
    "emotion": "carga emocional",
    "story": "historia",
    "advice": "consejo práctico",
    "controversy": "opinión polémica",
    "completeness": "idea completa",
}

REASON_FEATURES = tuple(FEATURE_LABELS)


@dataclass(frozen=True)
class ClipCandidate:
    """Candidato interno previo a la construcción del ``Clip`` final."""

    start_seconds: float
    end_seconds: float
    text: str
    score: float
    reason: str
    keywords: tuple[str, ...] = ()
    signals: dict[str, float] = field(default_factory=dict, compare=False, repr=False)

    @property
    def duration(self) -> float:
        return round(self.end_seconds - self.start_seconds, 3)

    @property
    def start_time(self) -> str:
        return format_timecode(self.start_seconds)

    @property
    def end_time(self) -> str:
        return format_timecode(self.end_seconds)


@dataclass(frozen=True)
class _Window:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


def _count_words(tokens: list[str], words: frozenset[str]) -> int:
    return sum(1 for token in tokens if token in words)


def _count_phrases(normalized: str, phrases: tuple[str, ...]) -> int:
    return sum(normalized.count(phrase) for phrase in phrases)


def _extract_features(text: str, duration: float) -> dict[str, float]:
    normalized = normalize_text(text)
    tokens = [token for token in (normalize_token(item) for item in tokenize(text)) if token]
    word_count = len(tokens)
    safe_duration = max(duration, 0.001)

    question = 1.0 if "?" in text else 0.0
    if question == 0.0 and tokens:
        if tokens[0] in INTERROGATIVES or (
            len(tokens) >= 2 and f"{tokens[0]} {tokens[1]}" == "por que"
        ):
            question = 0.7

    curiosity = min(
        1.0,
        (_count_words(tokens, CURIOSITY_WORDS) + _count_phrases(normalized, CURIOSITY_PHRASES))
        / 3,
    )
    numbers = min(
        1.0,
        (
            len(NUMBER_RE.findall(text))
            + _count_words(tokens, NUMBER_WORDS)
            + _count_phrases(normalized, NUMBER_PHRASES)
        )
        / 3,
    )
    emotion = min(1.0, _count_words(tokens, EMOTION_WORDS) / 3)
    story = min(
        1.0,
        (_count_words(tokens, STORY_WORDS) + _count_phrases(normalized, STORY_PHRASES)) / 3,
    )
    advice = min(
        1.0,
        (_count_words(tokens, ADVICE_WORDS) + _count_phrases(normalized, ADVICE_PHRASES)) / 3,
    )
    controversy = min(
        1.0,
        (
            _count_words(tokens, CONTROVERSY_WORDS)
            + _count_phrases(normalized, CONTROVERSY_PHRASES)
        )
        / 3,
    )

    words_per_second = word_count / safe_duration
    density = max(0.0, 1.0 - abs(words_per_second - 2.5) / 2.5)

    sentence_text = text.replace("?", ".").replace("!", ".")
    sentence_count = len([part for part in sentence_text.split(".") if part.strip()])
    completeness = 1.0 if text.rstrip().endswith((".", "!", "?")) else 0.4
    if sentence_count >= 2:
        completeness = min(1.0, completeness + 0.2)

    content_tokens = [
        token for token in tokens if token not in STOPWORDS and len(token) >= 3
    ]
    keyword_density = min(1.0, (len(content_tokens) / max(1, word_count)) * 2)

    filler = min(
        1.0,
        (_count_words(tokens, FILLER_WORDS) + _count_phrases(normalized, FILLER_PHRASES)) / 5,
    )
    unique_ratio = len(set(tokens)) / max(1, word_count)
    repetition = min(1.0, (1.0 - unique_ratio) * 2)

    return {
        "question": question,
        "curiosity": curiosity,
        "numbers": numbers,
        "emotion": emotion,
        "story": story,
        "advice": advice,
        "controversy": controversy,
        "density": density,
        "completeness": completeness,
        "keyword_density": keyword_density,
        "filler": filler,
        "repetition": repetition,
    }


def extract_keywords(text: str, limit: int = 5) -> tuple[str, ...]:
    """Extrae palabras plenas ordenadas por frecuencia y longitud."""

    counts: Counter[str] = Counter()
    for token in tokenize(text):
        normalized = normalize_token(token)
        if len(normalized) < 4 or normalized in STOPWORDS or normalized.isdigit():
            continue
        counts[token.lower()] += 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    return tuple(word for word, _ in ranked[:limit]) or ("esto",)


def _build_reason(features: dict[str, float]) -> str:
    labels = [
        FEATURE_LABELS[key]
        for key in sorted(REASON_FEATURES, key=lambda name: -FEATURE_WEIGHTS[name])
        if features.get(key, 0.0) >= 0.5
    ]
    if features.get("filler", 0.0) >= 0.4:
        labels.append("algo de relleno")
    if labels:
        return ("Señales: " + ", ".join(labels[:4]))[:300]
    return "Ritmo conversacional y cierre de idea"


def _score_text(text: str, duration: float) -> tuple[float, str, dict[str, float], tuple[str, ...]]:
    features = _extract_features(text, duration)
    raw = sum(FEATURE_WEIGHTS[key] * features[key] for key in FEATURE_WEIGHTS)
    score = 1.0 / (1.0 + math.exp(-(raw - 2.2)))
    return round(score, 3), _build_reason(features), features, extract_keywords(text)


def _make_segment(words: list) -> Segment:
    start = words[0].start
    end = words[-1].end
    if end <= start:
        end = start + 0.01
    text = " ".join(word.word for word in words).strip()
    return Segment(start=start, end=end, text=text, words=list(words))


def _split_long_segments(segments: list[Segment], max_duration: float) -> list[Segment]:
    result: list[Segment] = []
    for segment in segments:
        if segment.end - segment.start <= max_duration:
            result.append(segment)
            continue

        words = segment.words or synthesize_words(segment.text, segment.start, segment.end)
        group = []
        group_start = 0.0
        for word in words:
            if not group:
                group_start = word.start
            if group and word.end - group_start > max_duration:
                result.append(_make_segment(group))
                group = [word]
                group_start = word.start
            else:
                group.append(word)
        if group:
            result.append(_make_segment(group))
    return result


def _make_window(segments: list[Segment]) -> _Window:
    return _Window(
        start=segments[0].start,
        end=segments[-1].end,
        text=" ".join(segment.text for segment in segments).strip(),
    )


def _chunk_segments(
    segments: list[Segment], min_duration: float, max_duration: float
) -> list[_Window]:
    chunks: list[_Window] = []
    current: list[Segment] = []

    for index, segment in enumerate(segments):
        current.append(segment)
        start = current[0].start
        duration = segment.end - start
        if duration < min_duration:
            continue

        next_gap = (
            segments[index + 1].start - segment.end if index + 1 < len(segments) else 0.0
        )
        natural_end = segment.text.rstrip().endswith((".", "!", "?")) or next_gap > 0.8
        if duration >= max_duration or natural_end:
            chunks.append(_make_window(current))
            current = []

    if current:
        tail = _make_window(current)
        if chunks and tail.end - chunks[-1].start <= max_duration:
            chunks[-1] = _Window(
                start=chunks[-1].start,
                end=tail.end,
                text=f"{chunks[-1].text} {tail.text}".strip(),
            )
        else:
            chunks.append(tail)

    return chunks


def _dedupe_windows(windows: list[_Window]) -> list[_Window]:
    seen_ranges: set[tuple[float, float]] = set()
    seen_texts: set[str] = set()
    result: list[_Window] = []
    for window in windows:
        if window.duration <= 0:
            continue
        range_key = (round(window.start, 1), round(window.end, 1))
        text_key = normalize_text(window.text)
        if range_key in seen_ranges or text_key in seen_texts:
            continue
        seen_ranges.add(range_key)
        seen_texts.add(text_key)
        result.append(window)
    return result


def _generate_windows(
    transcript: Transcript, min_duration: float, max_duration: float
) -> list[_Window]:
    segments = _split_long_segments(transcript.segments, max_duration)
    windows: list[_Window] = []

    chunks = _chunk_segments(segments, min_duration, max_duration)
    for index, chunk in enumerate(chunks):
        if min_duration <= chunk.duration <= max_duration:
            windows.append(chunk)
        for end_index in range(index + 1, min(index + 3, len(chunks))):
            merged = _Window(
                start=chunks[index].start,
                end=chunks[end_index].end,
                text=" ".join(
                    item.text for item in chunks[index : end_index + 1]
                ).strip(),
            )
            if merged.duration > max_duration:
                break
            if merged.duration >= min_duration:
                windows.append(merged)

    anchors = [
        index
        for index, segment in enumerate(segments)
        if index == 0
        or segment.start - segments[index - 1].end > 0.8
        or segments[index - 1].text.rstrip().endswith((".", "!", "?"))
    ]

    for anchor_index in anchors[:MAX_ANCHORS]:
        start = segments[anchor_index].start
        parts: list[str] = []
        for index in range(anchor_index, len(segments)):
            segment = segments[index]
            if segment.start - start > max_duration:
                break
            parts.append(segment.text)
            duration = segment.end - start
            if min_duration <= duration <= max_duration:
                windows.append(_Window(start=start, end=segment.end, text=" ".join(parts).strip()))
                next_gap = (
                    segments[index + 1].start - segment.end
                    if index + 1 < len(segments)
                    else 0.0
                )
                if segment.text.rstrip().endswith((".", "!", "?")) or next_gap > 0.8:
                    break
            if len(windows) >= MAX_WINDOWS:
                break
        if len(windows) >= MAX_WINDOWS:
            break

    windows = [
        window
        for window in windows
        if window.duration <= max_duration + 0.01 and len(window.text) <= MAX_WINDOW_CHARS
    ]

    if not windows:
        if transcript.duration <= max_duration:
            text = " ".join(segment.text for segment in transcript.segments).strip()
            windows.append(_Window(start=0.0, end=transcript.duration, text=text))
        else:
            parts: list[str] = []
            end = 0.0
            for segment in transcript.segments:
                if parts and segment.end > max_duration:
                    break
                parts.append(segment.text)
                end = segment.end
            windows.append(_Window(start=0.0, end=end, text=" ".join(parts).strip()))

    return _dedupe_windows(windows)


def build_candidates(
    transcript: Transcript,
    *,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> list[ClipCandidate]:
    """Genera y puntúa todos los candidatos de una transcripción."""

    if min_duration <= 0:
        raise InvalidParameterError("min_duration debe ser mayor que 0")
    if max_duration <= min_duration:
        raise InvalidParameterError("max_duration debe ser mayor que min_duration")

    candidates: list[ClipCandidate] = []
    for window in _generate_windows(transcript, min_duration, max_duration):
        score, reason, features, keywords = _score_text(window.text, window.duration)
        candidates.append(
            ClipCandidate(
                start_seconds=round(window.start, 3),
                end_seconds=round(window.end, 3),
                text=window.text,
                score=score,
                reason=reason,
                keywords=keywords,
                signals=features,
            )
        )

    candidates.sort(key=lambda candidate: (-candidate.score, candidate.start_seconds))
    return candidates


def _overlap_ratio(first: ClipCandidate, second: ClipCandidate) -> float:
    overlap = max(
        0.0,
        min(first.end_seconds, second.end_seconds)
        - max(first.start_seconds, second.start_seconds),
    )
    shortest = min(first.duration, second.duration)
    return overlap / shortest if shortest > 0 else 0.0


def _jaccard(first: str, second: str) -> float:
    first_tokens = {
        normalize_token(token)
        for token in tokenize(first)
        if normalize_token(token) not in STOPWORDS
    }
    second_tokens = {
        normalize_token(token)
        for token in tokenize(second)
        if normalize_token(token) not in STOPWORDS
    }
    if not first_tokens or not second_tokens:
        return 0.0
    return len(first_tokens & second_tokens) / len(first_tokens | second_tokens)


def select_candidates(
    candidates: list[ClipCandidate],
    *,
    max_clips: int = 5,
    max_overlap_ratio: float = 0.5,
    max_similarity: float = 0.85,
) -> list[ClipCandidate]:
    """Selecciona clips diversos por score, solapamiento y similitud."""

    if max_clips < 1:
        raise InvalidParameterError("max_clips debe ser al menos 1")

    ordered = sorted(candidates, key=lambda candidate: (-candidate.score, candidate.start_seconds))
    selected: list[ClipCandidate] = []

    for candidate in ordered:
        if len(selected) >= max_clips:
            break
        if any(
            _overlap_ratio(candidate, chosen) >= max_overlap_ratio for chosen in selected
        ):
            continue
        if any(_jaccard(candidate.text, chosen.text) > max_similarity for chosen in selected):
            continue
        selected.append(candidate)

    return selected


def analyze_transcript(
    transcript: Transcript,
    *,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    max_clips: int = 5,
) -> list[ClipCandidate]:
    """Pipeline de análisis de la Fase 3: candidatos + selección."""

    candidates = build_candidates(
        transcript,
        min_duration=min_duration,
        max_duration=max_duration,
    )
    return select_candidates(candidates, max_clips=max_clips)
