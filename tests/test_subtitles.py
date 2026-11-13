from __future__ import annotations

from pathlib import Path

import pytest

from viralclip.analyzer import ClipCandidate, analyze_transcript
from viralclip.errors import InvalidParameterError
from viralclip.subtitles import build_subtitles, to_srt, to_vtt
from viralclip.transcript import load_transcript, normalize_transcript

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def viral_transcript():
    return load_transcript(FIXTURES / "transcripcion_viral.json")


@pytest.fixture()
def top_candidate(viral_transcript):
    return analyze_transcript(
        viral_transcript, min_duration=15, max_duration=30, max_clips=1
    )[0]


def test_subtitle_lines_respect_rules(viral_transcript, top_candidate) -> None:
    lines = build_subtitles(viral_transcript, top_candidate)

    assert lines
    for expected_index, line in enumerate(lines, start=1):
        assert line.index == expected_index
        assert 1 <= len(line.words) <= 5
        assert len(line.text) <= 42
        assert line.text == " ".join(word.word for word in line.words)
        assert line.start == line.words[0].start
        assert line.end == line.words[-1].end
        assert top_candidate.start_seconds <= line.start <= top_candidate.end_seconds + 0.001
        assert top_candidate.start_seconds <= line.end <= top_candidate.end_seconds + 0.001


def test_max_four_words_per_line(viral_transcript, top_candidate) -> None:
    lines = build_subtitles(
        viral_transcript, top_candidate, max_words_per_line=4
    )

    assert lines
    assert all(len(line.words) <= 4 for line in lines)


def test_highlights_are_limited(viral_transcript, top_candidate) -> None:
    lines = build_subtitles(
        viral_transcript,
        top_candidate,
        highlight_keywords=("ventas", "error"),
    )

    highlighted = [word for line in lines for word in line.words if word.highlight]
    assert highlighted
    for line in lines:
        assert sum(1 for word in line.words if word.highlight) <= 2


def test_srt_export(viral_transcript, top_candidate) -> None:
    lines = build_subtitles(viral_transcript, top_candidate)
    srt = to_srt(lines)

    assert srt.startswith("1\n")
    assert "-->" in srt
    assert "," in srt.splitlines()[1]
    assert srt.endswith("\n")


def test_vtt_export(viral_transcript, top_candidate) -> None:
    lines = build_subtitles(viral_transcript, top_candidate)
    vtt = to_vtt(lines)

    assert vtt.startswith("WEBVTT")
    assert "-->" in vtt
    assert "." in vtt.splitlines()[2]
    assert vtt.endswith("\n")


def test_empty_range_returns_no_lines(viral_transcript) -> None:
    candidate = ClipCandidate(
        start_seconds=100,
        end_seconds=110,
        text="",
        score=0.0,
        reason="prueba",
    )

    assert build_subtitles(viral_transcript, candidate) == []
    assert to_srt([]) == ""
    assert to_vtt([]).startswith("WEBVTT")


def test_pause_breaks_line() -> None:
    transcript = normalize_transcript(
        {
            "segments": [
                {
                    "start": 0,
                    "end": 3,
                    "text": "Hola mundo",
                    "words": [
                        {"word": "Hola", "start": 0.0, "end": 0.5},
                        {"word": "mundo", "start": 2.0, "end": 2.5},
                    ],
                }
            ]
        }
    )
    candidate = ClipCandidate(
        start_seconds=0, end_seconds=3, text="Hola mundo", score=0.5, reason="prueba"
    )

    lines = build_subtitles(transcript, candidate)

    assert [line.text for line in lines] == ["Hola", "mundo"]


def test_punctuation_breaks_line() -> None:
    transcript = normalize_transcript(
        {
            "segments": [
                {
                    "start": 0,
                    "end": 2,
                    "text": "Hola mundo. Otra frase.",
                    "words": [
                        {"word": "Hola", "start": 0.0, "end": 0.3},
                        {"word": "mundo.", "start": 0.3, "end": 0.7},
                        {"word": "Otra", "start": 0.9, "end": 1.2},
                        {"word": "frase.", "start": 1.2, "end": 1.6},
                    ],
                }
            ]
        }
    )
    candidate = ClipCandidate(
        start_seconds=0,
        end_seconds=2,
        text="Hola mundo. Otra frase.",
        score=0.5,
        reason="prueba",
    )

    lines = build_subtitles(transcript, candidate)

    assert [line.text for line in lines] == ["Hola mundo.", "Otra frase."]


def test_invalid_parameters(viral_transcript, top_candidate) -> None:
    with pytest.raises(InvalidParameterError):
        build_subtitles(viral_transcript, top_candidate, max_words_per_line=0)

    with pytest.raises(InvalidParameterError):
        build_subtitles(viral_transcript, top_candidate, max_words_per_line=6)

    with pytest.raises(InvalidParameterError):
        build_subtitles(viral_transcript, top_candidate, max_chars_per_line=5)

    with pytest.raises(InvalidParameterError):
        build_subtitles(viral_transcript, top_candidate, max_gap=-1)
