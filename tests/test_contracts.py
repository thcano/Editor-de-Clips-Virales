from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from viralclip.models import (
    AnalysisResult,
    Clip,
    EngineInfo,
    SourceInfo,
    SpecClip,
    SubtitleLine,
    SubtitleWord,
)
from viralclip.transcript import normalize_transcript, transcript_to_dict

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
INPUT_SCHEMA = json.loads(
    (ROOT / "docs" / "contratos" / "transcripcion.schema.json").read_text(encoding="utf-8")
)
OUTPUT_SCHEMA = json.loads(
    (ROOT / "docs" / "contratos" / "salida.schema.json").read_text(encoding="utf-8")
)


def _validate(schema: dict, instance: object) -> None:
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(instance)


def _sample_result() -> AnalysisResult:
    subtitle = SubtitleLine(
        index=1,
        start=0.0,
        end=1.2,
        text="Esto es lo que",
        words=[
            SubtitleWord(word="Esto", start=0.0, end=0.3, highlight=False),
            SubtitleWord(word="es", start=0.3, end=0.5, highlight=False),
            SubtitleWord(word="lo", start=0.5, end=0.7, highlight=False),
            SubtitleWord(word="que", start=0.7, end=0.9, highlight=True),
        ],
    )
    clip = Clip(
        id="clip_001",
        rank=1,
        start_time="00:00",
        end_time="00:45",
        start_seconds=0.0,
        end_seconds=45.0,
        duration_seconds=45.0,
        platform="tiktok",
        hook="Nadie te cuenta esto sobre vender",
        title="El error que frena tus ventas",
        description="Un consejo directo para vender más sin sonar corporativo.",
        caption_text="Esto es lo que nadie te cuenta sobre vender.",
        hashtags=["#ventas", "#emprendimiento", "#tips"],
        score=0.87,
        reason="Pregunta directa + dato + lenguaje conversacional",
        keywords=["vender", "nadie"],
        subtitles=[subtitle],
    )
    return AnalysisResult(
        generated_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        source=SourceInfo(language="es", duration=12.0, segment_count=3),
        engine=EngineInfo(name="heuristic", model=None, degraded=True),
        clips=[clip],
    )


def test_input_schema_accepts_document_and_array() -> None:
    document = json.loads(
        (FIXTURES / "transcripcion_basica.json").read_text(encoding="utf-8")
    )
    array = json.loads(
        (FIXTURES / "transcripcion_array.json").read_text(encoding="utf-8")
    )

    _validate(INPUT_SCHEMA, document)
    _validate(INPUT_SCHEMA, array)


def test_input_schema_rejects_missing_text() -> None:
    payload = {"segments": [{"start": 0, "end": 1}]}

    with pytest.raises(ValidationError):
        _validate(INPUT_SCHEMA, payload)


def test_normalized_transcript_matches_input_schema() -> None:
    raw = json.loads(
        (FIXTURES / "transcripcion_basica.json").read_text(encoding="utf-8")
    )
    normalized = transcript_to_dict(normalize_transcript(raw))

    _validate(INPUT_SCHEMA, normalized)


def test_output_schema_accepts_sample_result() -> None:
    data = json.loads(_sample_result().model_dump_json())

    _validate(OUTPUT_SCHEMA, data)


def test_output_schema_rejects_hook_too_long() -> None:
    with pytest.raises(ValueError):
        Clip(
            id="clip_001",
            rank=1,
            start_time="00:00",
            end_time="00:10",
            start_seconds=0.0,
            end_seconds=10.0,
            duration_seconds=10.0,
            platform="tiktok",
            hook="uno dos tres cuatro cinco seis siete ocho nueve diez once",
            title="Título",
            description="Descripción",
            caption_text="Texto",
            hashtags=["#uno"],
            score=0.5,
            reason="Razón",
        )


def test_to_spec_shape() -> None:
    spec = _sample_result().to_spec()

    assert len(spec) == 1
    assert set(spec[0]) == {"start_time", "end_time", "hook", "caption_text", "hashtags"}
    _validate(
        {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "start_time",
                    "end_time",
                    "hook",
                    "caption_text",
                    "hashtags",
                ],
            },
        },
        spec,
    )


def test_spec_clip_model() -> None:
    clip = SpecClip(
        start_time="00:00",
        end_time="00:45",
        hook="Nadie te cuenta esto",
        caption_text="Esto es lo que nadie te cuenta.",
        hashtags=["#ventas"],
    )

    assert clip.model_dump()["start_time"] == "00:00"
