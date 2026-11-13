from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from viralclip.analyzer import analyze_transcript
from viralclip.errors import InvalidParameterError
from viralclip.pipeline import analyze, build_clip
from viralclip.transcript import load_transcript

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
OUTPUT_SCHEMA = json.loads(
    (ROOT / "docs" / "contratos" / "salida.schema.json").read_text(encoding="utf-8")
)
FIXED_TIME = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


@pytest.fixture()
def viral_transcript():
    return load_transcript(FIXTURES / "transcripcion_viral.json")


def test_analyze_pipeline(viral_transcript) -> None:
    result = analyze(
        viral_transcript,
        platform="tiktok",
        max_clips=2,
        min_duration=15,
        max_duration=30,
        generated_at=FIXED_TIME,
    )

    assert result.version == "1.0"
    assert result.generated_at == FIXED_TIME
    assert 1 <= len(result.clips) <= 2
    assert result.engine.name == "heuristic"
    assert result.engine.degraded is False

    for clip in result.clips:
        assert clip.id.startswith("clip_")
        assert clip.rank >= 1
        assert clip.hook
        assert len(clip.hook.split()) <= 10
        assert clip.title
        assert clip.description
        assert clip.caption_text
        assert clip.hashtags
        assert clip.subtitles
        assert all(len(line.words) <= 5 for line in clip.subtitles)
        assert clip.start_time and clip.end_time
        assert clip.start_seconds < clip.end_seconds


def test_pipeline_matches_output_schema(viral_transcript) -> None:
    result = analyze(
        viral_transcript,
        platform="shorts",
        max_clips=2,
        min_duration=15,
        max_duration=30,
        generated_at=FIXED_TIME,
    )

    data = json.loads(result.model_dump_json())
    Draft202012Validator(OUTPUT_SCHEMA).validate(data)


def test_to_spec_shape(viral_transcript) -> None:
    result = analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        generated_at=FIXED_TIME,
    )

    spec = result.to_spec()

    assert spec
    assert set(spec[0]) == {"start_time", "end_time", "hook", "caption_text", "hashtags"}


def test_pipeline_is_deterministic(viral_transcript) -> None:
    first = analyze(
        viral_transcript,
        platform="tiktok",
        max_clips=3,
        min_duration=15,
        max_duration=30,
        generated_at=FIXED_TIME,
    )
    second = analyze(
        viral_transcript,
        platform="tiktok",
        max_clips=3,
        min_duration=15,
        max_duration=30,
        generated_at=FIXED_TIME,
    )

    assert first.model_dump_json() == second.model_dump_json()


def test_build_clip_rank_and_id(viral_transcript) -> None:
    candidate = analyze_transcript(
        viral_transcript, min_duration=15, max_duration=30, max_clips=1
    )[0]

    clip = build_clip(candidate, viral_transcript, platform="shorts", rank=3)

    assert clip.id == "clip_003"
    assert clip.rank == 3
    assert clip.platform == "shorts"
    assert clip.start_seconds == candidate.start_seconds
    assert clip.end_seconds == candidate.end_seconds


def test_platform_variants_change_metadata(viral_transcript) -> None:
    tiktok = analyze(
        viral_transcript,
        platform="tiktok",
        max_clips=1,
        min_duration=15,
        max_duration=30,
        generated_at=FIXED_TIME,
    )
    shorts = analyze(
        viral_transcript,
        platform="shorts",
        max_clips=1,
        min_duration=15,
        max_duration=30,
        generated_at=FIXED_TIME,
    )

    assert tiktok.clips[0].hashtags != shorts.clips[0].hashtags
    assert "#fyp" in tiktok.clips[0].hashtags
    assert "#shorts" in shorts.clips[0].hashtags


def test_invalid_platform_is_rejected(viral_transcript) -> None:
    with pytest.raises(InvalidParameterError):
        analyze(
            viral_transcript,
            platform="facebook",
            max_clips=1,
            min_duration=15,
            max_duration=30,
            generated_at=FIXED_TIME,
        )
