from __future__ import annotations

import pytest

from viralclip.timeutils import format_timecode, parse_timestamp


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0.0),
        (12, 12.0),
        (12.5, 12.5),
        ("0", 0.0),
        ("12.5", 12.5),
        ("01:02", 62.0),
        ("01:02.500", 62.5),
        ("1:02:03", 3723.0),
        ("01:02:03.250", 3723.25),
        (" 00:00 ", 0.0),
    ],
)
def test_parse_timestamp_valid(value: object, expected: float) -> None:
    assert parse_timestamp(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        -1,
        "-1",
        True,
        False,
        "",
        "   ",
        "abc",
        "1:2:3:4",
        "01:60",
        "01:02:60",
        float("nan"),
        float("inf"),
        86_401,
        None,
        [],
    ],
)
def test_parse_timestamp_invalid(value: object) -> None:
    with pytest.raises(ValueError):
        parse_timestamp(value)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00"),
        (5.4, "00:05"),
        (5.6, "00:06"),
        (59.6, "01:00"),
        (60, "01:00"),
        (3599, "59:59"),
        (3600, "01:00:00"),
        (3723, "01:02:03"),
        (-5, "00:00"),
    ],
)
def test_format_timecode(seconds: float, expected: str) -> None:
    assert format_timecode(seconds) == expected


def test_format_timecode_force_hours() -> None:
    assert format_timecode(45, force_hours=True) == "00:00:45"
