from __future__ import annotations

import re

import pytest

from viralclip.analyzer import ClipCandidate
from viralclip.errors import InvalidParameterError
from viralclip.lexicon import is_corporate
from viralclip.platforms import build_metadata

HASHTAG_RE = re.compile(r"^#[A-Za-z0-9_]+$")


def _candidate() -> ClipCandidate:
    return ClipCandidate(
        start_seconds=0,
        end_seconds=20,
        text="El error brutal que te cuesta miles de euros.",
        score=0.8,
        reason="Señales: error, dato",
        keywords=("ventas", "error", "clientes"),
        signals={
            "advice": 0.8,
            "numbers": 0.6,
            "story": 0.0,
            "controversy": 0.5,
        },
    )


@pytest.mark.parametrize(
    ("platform", "expected_base"),
    [
        ("tiktok", "#fyp"),
        ("reels", "#reels"),
        ("shorts", "#shorts"),
    ],
)
def test_platform_metadata(platform: str, expected_base: str) -> None:
    metadata = build_metadata(
        _candidate(), "Nadie te cuenta esto sobre ventas", platform
    )

    assert metadata.title
    assert len(metadata.title) <= 120
    assert metadata.description
    assert len(metadata.description) <= 500
    assert 1 <= len(metadata.hashtags) <= 8
    assert len(set(metadata.hashtags)) == len(metadata.hashtags)
    assert expected_base in metadata.hashtags
    assert all(HASHTAG_RE.match(tag) for tag in metadata.hashtags)


def test_keyword_hashtags_are_included() -> None:
    metadata = build_metadata(_candidate(), "Hook", "tiktok")

    assert "#ventas" in metadata.hashtags
    assert "#error" in metadata.hashtags


def test_invalid_platform_is_rejected() -> None:
    with pytest.raises(InvalidParameterError):
        build_metadata(_candidate(), "Hook", "facebook")


def test_description_has_no_corporate_language() -> None:
    metadata = build_metadata(_candidate(), "Hook", "tiktok")

    assert not is_corporate(metadata.description)


def test_title_is_truncated() -> None:
    metadata = build_metadata(_candidate(), "x" * 200, "tiktok")

    assert len(metadata.title) <= 120
    assert metadata.title.endswith("...")


def test_hashtags_are_capped_and_unique() -> None:
    metadata = build_metadata(_candidate(), "Hook", "shorts")

    assert len(metadata.hashtags) <= 8
    assert len(metadata.hashtags) == len(set(metadata.hashtags))
