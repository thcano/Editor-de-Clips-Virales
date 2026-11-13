from __future__ import annotations

import json
from pathlib import Path

import pytest

from viralclip.errors import InvalidTranscriptError, PayloadTooLargeError
from viralclip.transcript import (
    load_transcript,
    normalize_transcript,
    transcript_to_dict,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_json(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_load_basic_document() -> None:
    transcript = load_transcript(FIXTURES / "transcripcion_basica.json")

    assert transcript.language == "es"
    assert transcript.duration == 12.0
    assert transcript.source_format == "document"
    assert len(transcript.segments) == 3
    assert len(transcript.segments[0].words) == 9
    assert transcript.segments[0].words[0].word == "Esto"
    assert transcript.segments[0].words[-1].end == 3.0


def test_array_root() -> None:
    transcript = normalize_transcript(_load_json("transcripcion_array.json"))

    assert transcript.source_format == "array"
    assert len(transcript.segments) == 2
    assert transcript.duration == 5.0
    assert transcript.segments[0].text == "Primer segmento de prueba."


def test_whisper_without_words_synthesizes() -> None:
    transcript = normalize_transcript(_load_json("transcripcion_whisper.json"))

    assert len(transcript.segments) == 3
    for segment in transcript.segments:
        assert len(segment.words) == len(segment.text.split())
        assert segment.words[0].start == segment.start
        assert segment.words[-1].end == segment.end
        for previous, current in zip(segment.words, segment.words[1:], strict=False):
            assert current.start >= previous.end - 1e-6


def test_top_level_words_grouped() -> None:
    transcript = normalize_transcript(_load_json("transcripcion_palabras.json"))

    assert transcript.source_format == "words"
    assert len(transcript.segments) == 2
    assert transcript.segments[0].start == 0.0
    assert transcript.segments[0].end == 2.0
    assert "Hola" in transcript.segments[0].text
    assert transcript.segments[1].start == 3.5
    assert transcript.segments[1].text == "El secreto es preguntar"


def test_json_string_payload() -> None:
    raw = (FIXTURES / "transcripcion_array.json").read_text(encoding="utf-8")
    transcript = normalize_transcript(raw)

    assert len(transcript.segments) == 2


def test_bytes_payload() -> None:
    raw = (FIXTURES / "transcripcion_array.json").read_bytes()
    transcript = normalize_transcript(raw)

    assert transcript.duration == 5.0


def test_invalid_json() -> None:
    with pytest.raises(InvalidTranscriptError) as error:
        normalize_transcript("{no es json")

    assert error.value.code.value == "VC-1001"


def test_empty_transcript() -> None:
    with pytest.raises(InvalidTranscriptError):
        normalize_transcript({"segments": []})


def test_missing_segments_and_words() -> None:
    with pytest.raises(InvalidTranscriptError):
        normalize_transcript({"foo": "bar"})


def test_end_before_start() -> None:
    with pytest.raises(InvalidTranscriptError):
        load_transcript(FIXTURES / "transcripcion_invalida.json")


def test_payload_too_large() -> None:
    with pytest.raises(PayloadTooLargeError) as error:
        normalize_transcript("x" * 100, max_bytes=10)

    assert error.value.code.value == "VC-1002"


def test_too_many_segments() -> None:
    payload = _load_json("transcripcion_basica.json")

    with pytest.raises(PayloadTooLargeError):
        normalize_transcript(payload, max_segments=2)


def test_overlap_rejected() -> None:
    with pytest.raises(InvalidTranscriptError):
        load_transcript(FIXTURES / "transcripcion_solapada.json")


def test_small_overlap_tolerated() -> None:
    payload = {
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "Uno"},
            {"start": 4.8, "end": 8.0, "text": "Dos"},
        ]
    }
    transcript = normalize_transcript(payload)

    assert len(transcript.segments) == 2


def test_duration_uses_maximum() -> None:
    payload = {
        "duration": 5.0,
        "segments": [{"start": 0.0, "end": 12.0, "text": "Texto"}],
    }
    transcript = normalize_transcript(payload)

    assert transcript.duration == 12.0


def test_invalid_word_time() -> None:
    payload = {
        "segments": [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "Hola mundo",
                "words": [
                    {"word": "Hola", "start": 1.0, "end": 0.5},
                ],
            }
        ]
    }
    with pytest.raises(InvalidTranscriptError):
        normalize_transcript(payload)


def test_word_outside_segment() -> None:
    payload = {
        "segments": [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "Hola mundo",
                "words": [
                    {"word": "Hola", "start": 0.0, "end": 3.0},
                ],
            }
        ]
    }
    with pytest.raises(InvalidTranscriptError):
        normalize_transcript(payload)


def test_language_default_and_truncation() -> None:
    payload = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hola"}]}
    assert normalize_transcript(payload).language == "es"

    payload["language"] = "espanol-muy-largo"
    assert normalize_transcript(payload).language == "espanol-mu"


def test_transcript_to_dict_is_json_serializable() -> None:
    transcript = normalize_transcript(_load_json("transcripcion_basica.json"))
    data = transcript_to_dict(transcript)

    assert data["language"] == "es"
    assert data["segments"][0]["words"][0]["word"] == "Esto"
    assert json.loads(json.dumps(data))
