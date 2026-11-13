from __future__ import annotations

from pathlib import Path

import pytest

from viralclip.analyzer import (
    analyze_transcript,
    build_candidates,
    extract_keywords,
    select_candidates,
)
from viralclip.errors import InvalidParameterError
from viralclip.transcript import load_transcript, normalize_transcript

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def viral_transcript():
    return load_transcript(FIXTURES / "transcripcion_viral.json")


def test_candidates_respect_duration(viral_transcript) -> None:
    candidates = build_candidates(viral_transcript, min_duration=15, max_duration=30)

    assert candidates
    for candidate in candidates:
        assert candidate.duration <= 30.01
        assert candidate.duration >= 14.99


def test_scores_reasons_and_keywords(viral_transcript) -> None:
    candidates = build_candidates(viral_transcript, min_duration=15, max_duration=30)

    for candidate in candidates:
        assert 0.0 <= candidate.score <= 1.0
        assert candidate.reason
        assert len(candidate.reason) <= 300
        assert candidate.keywords
        assert candidate.start_time
        assert candidate.end_time


def test_strong_candidate_wins(viral_transcript) -> None:
    selected = analyze_transcript(
        viral_transcript, min_duration=15, max_duration=30, max_clips=1
    )

    assert len(selected) == 1
    top = selected[0]
    text = top.text.lower()
    assert any(word in text for word in ("ventas", "error", "preguntar", "brutal"))
    assert top.score >= 0.5


def test_max_clips(viral_transcript) -> None:
    selected = analyze_transcript(
        viral_transcript, min_duration=15, max_duration=30, max_clips=2
    )

    assert len(selected) == 2


def test_no_large_overlap(viral_transcript) -> None:
    selected = analyze_transcript(
        viral_transcript, min_duration=15, max_duration=30, max_clips=5
    )

    for index, first in enumerate(selected):
        for second in selected[index + 1 :]:
            overlap = max(
                0.0,
                min(first.end_seconds, second.end_seconds)
                - max(first.start_seconds, second.start_seconds),
            )
            shortest = min(first.duration, second.duration)
            assert overlap / shortest < 0.5


def test_deterministic(viral_transcript) -> None:
    first = analyze_transcript(
        viral_transcript, min_duration=15, max_duration=30, max_clips=5
    )
    second = analyze_transcript(
        viral_transcript, min_duration=15, max_duration=30, max_clips=5
    )

    assert [
        (item.start_seconds, item.end_seconds, item.score, item.text, item.reason)
        for item in first
    ] == [
        (item.start_seconds, item.end_seconds, item.score, item.text, item.reason)
        for item in second
    ]


def test_short_transcript_returns_one_clip() -> None:
    transcript = normalize_transcript(
        {
            "segments": [
                {
                    "start": 0,
                    "end": 5,
                    "text": "Esto es lo que nadie te cuenta sobre vender.",
                }
            ]
        }
    )

    selected = analyze_transcript(
        transcript, min_duration=15, max_duration=60, max_clips=3
    )

    assert len(selected) == 1
    assert selected[0].start_seconds == 0
    assert selected[0].end_seconds == 5


def test_long_segment_is_split() -> None:
    text = " ".join(["palabra"] * 240)
    transcript = normalize_transcript(
        {"segments": [{"start": 0, "end": 120, "text": text}]}
    )

    candidates = build_candidates(transcript, min_duration=15, max_duration=30)

    assert candidates
    assert all(candidate.duration <= 30.01 for candidate in candidates)


def test_extract_keywords() -> None:
    keywords = extract_keywords(
        "El error brutal de las ventas: nadie pregunta y pierdes dinero."
    )

    assert "error" in keywords or "ventas" in keywords
    assert len(keywords) <= 5


def test_invalid_parameters(viral_transcript) -> None:
    with pytest.raises(InvalidParameterError):
        build_candidates(viral_transcript, min_duration=0, max_duration=30)

    with pytest.raises(InvalidParameterError):
        build_candidates(viral_transcript, min_duration=30, max_duration=15)

    with pytest.raises(InvalidParameterError):
        select_candidates([], max_clips=0)
