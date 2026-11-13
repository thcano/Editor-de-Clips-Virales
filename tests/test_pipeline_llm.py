from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from viralclip.config import Settings
from viralclip.errors import OllamaUnavailableError
from viralclip.llm.ollama import OllamaHealth
from viralclip.pipeline import analyze, build_clip
from viralclip.transcript import load_transcript

FIXTURES = Path(__file__).parent / "fixtures"
FIXED_TIME = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
MODEL = "llama3.2:latest"
VALID_HOOKS = (
    "Nadie te cuenta esto sobre vender",
    "El error que frena tus ventas",
)


class FakeOllama:
    def __init__(
        self,
        *,
        available: bool = True,
        responses: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.model = MODEL
        self.available = available
        self.responses = list(responses or [])
        self.error = error
        self.health_calls = 0
        self.generate_calls = 0
        self.closed = False

    def health(self) -> OllamaHealth:
        self.health_calls += 1
        if self.available:
            return OllamaHealth(True, self.model, (self.model,), "Ollama disponible")
        return OllamaHealth(
            False,
            self.model,
            (),
            "Ollama no responde en http://127.0.0.1:11434. Inicia Ollama.",
        )

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.generate_calls += 1
        if self.error is not None:
            raise self.error
        if not self.responses:
            return ""
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def viral_transcript():
    return load_transcript(FIXTURES / "transcripcion_viral.json")


def _baseline(transcript, max_clips: int = 2):
    return analyze(
        transcript,
        platform="tiktok",
        max_clips=max_clips,
        min_duration=15,
        max_duration=30,
        use_llm=False,
        generated_at=FIXED_TIME,
    )


def test_explicit_heuristic_is_not_degraded(viral_transcript) -> None:
    result = _baseline(viral_transcript)

    assert result.engine.name == "heuristic"
    assert result.engine.model is None
    assert result.engine.degraded is False
    assert "desactivado explícitamente" in (result.engine.notes or "")


def test_on_stage_reports_monotonic_progress(viral_transcript) -> None:
    stages: list[tuple[int, str]] = []

    analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        use_llm=False,
        generated_at=FIXED_TIME,
        on_stage=lambda progress, stage: stages.append((progress, stage)),
    )

    assert stages == [
        (10, "preparando"),
        (40, "candidatos"),
        (55, "ganchos"),
        (75, "ganchos"),
        (90, "clips"),
    ]
    assert [progress for progress, _ in stages] == sorted(
        progress for progress, _ in stages
    )


def test_llm_disabled_by_settings_does_not_call_ollama(viral_transcript) -> None:
    fake = FakeOllama()

    result = analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        use_llm=True,
        ollama_client=fake,
        settings=Settings(llm_enabled=False),
        generated_at=FIXED_TIME,
    )

    assert fake.health_calls == 0
    assert fake.generate_calls == 0
    assert result.engine.name == "heuristic"
    assert result.engine.degraded is False
    assert "VIRALCLIP_LLM_ENABLED" in (result.engine.notes or "")


def test_ollama_unavailable_falls_back(viral_transcript) -> None:
    fake = FakeOllama(available=False)

    result = analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        use_llm=True,
        ollama_client=fake,
        generated_at=FIXED_TIME,
    )

    assert fake.health_calls == 1
    assert fake.generate_calls == 0
    assert result.engine.name == "heuristic"
    assert result.engine.degraded is True
    assert "Inicia Ollama" in (result.engine.notes or "")
    assert [clip.hook for clip in result.clips] == [
        clip.hook for clip in _baseline(viral_transcript).clips
    ]


def test_valid_llm_hooks_are_used(viral_transcript) -> None:
    fake = FakeOllama(responses=list(VALID_HOOKS))

    result = analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        use_llm=True,
        ollama_client=fake,
        generated_at=FIXED_TIME,
    )

    assert fake.health_calls == 1
    assert fake.generate_calls == 2
    assert result.engine.name == "heuristic+ollama"
    assert result.engine.model == MODEL
    assert result.engine.degraded is False
    assert "2 de 2" in (result.engine.notes or "")
    assert [clip.hook for clip in result.clips] == list(VALID_HOOKS)


def test_invalid_llm_hooks_fall_back(viral_transcript) -> None:
    fake = FakeOllama(
        responses=[
            "uno dos tres cuatro cinco seis siete ocho nueve diez once",
            "Optimizar la sinergia del pipeline",
        ]
    )

    result = analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        use_llm=True,
        ollama_client=fake,
        generated_at=FIXED_TIME,
    )

    assert result.engine.name == "heuristic"
    assert result.engine.degraded is True
    assert "ningún gancho superó la validación" in (result.engine.notes or "")
    assert [clip.hook for clip in result.clips] == [
        clip.hook for clip in _baseline(viral_transcript).clips
    ]


def test_partial_valid_hooks(viral_transcript) -> None:
    fake = FakeOllama(
        responses=[
            VALID_HOOKS[0],
            "uno dos tres cuatro cinco seis siete ocho nueve diez once",
        ]
    )

    result = analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        use_llm=True,
        ollama_client=fake,
        generated_at=FIXED_TIME,
    )

    baseline = _baseline(viral_transcript)

    assert result.engine.name == "heuristic+ollama"
    assert result.engine.degraded is False
    assert "1 de 2" in (result.engine.notes or "")
    assert result.clips[0].hook == VALID_HOOKS[0]
    assert result.clips[1].hook == baseline.clips[1].hook


def test_generate_error_falls_back(viral_transcript) -> None:
    fake = FakeOllama(error=OllamaUnavailableError("Ollama cayó"))

    result = analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        use_llm=True,
        ollama_client=fake,
        generated_at=FIXED_TIME,
    )

    assert fake.generate_calls == 2
    assert result.engine.name == "heuristic"
    assert result.engine.degraded is True


def test_timestamps_do_not_change_with_llm(viral_transcript) -> None:
    fake = FakeOllama(responses=list(VALID_HOOKS))

    baseline = _baseline(viral_transcript)
    result = analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        use_llm=True,
        ollama_client=fake,
        generated_at=FIXED_TIME,
    )

    assert [
        (clip.start_seconds, clip.end_seconds) for clip in result.clips
    ] == [(clip.start_seconds, clip.end_seconds) for clip in baseline.clips]
    assert [clip.caption_text for clip in result.clips] == [
        clip.caption_text for clip in baseline.clips
    ]


def test_injected_client_is_not_closed(viral_transcript) -> None:
    fake = FakeOllama(responses=list(VALID_HOOKS))

    analyze(
        viral_transcript,
        max_clips=2,
        min_duration=15,
        max_duration=30,
        use_llm=True,
        ollama_client=fake,
        generated_at=FIXED_TIME,
    )

    assert fake.closed is False


def test_build_clip_accepts_valid_hook(viral_transcript) -> None:
    from viralclip.analyzer import analyze_transcript

    candidate = analyze_transcript(
        viral_transcript, min_duration=15, max_duration=30, max_clips=1
    )[0]

    clip = build_clip(
        candidate,
        viral_transcript,
        platform="tiktok",
        rank=1,
        hook="Nadie te cuenta esto sobre vender",
    )

    assert clip.hook == "Nadie te cuenta esto sobre vender"
    assert clip.title == "Nadie te cuenta esto sobre vender"


def test_build_clip_rejects_invalid_hook(viral_transcript) -> None:
    from viralclip.analyzer import analyze_transcript

    candidate = analyze_transcript(
        viral_transcript, min_duration=15, max_duration=30, max_clips=1
    )[0]

    clip = build_clip(
        candidate,
        viral_transcript,
        platform="tiktok",
        rank=1,
        hook="uno dos tres cuatro cinco seis siete ocho nueve diez once",
    )

    assert clip.hook != "uno dos tres cuatro cinco seis siete ocho nueve diez once"
    assert len(clip.hook.split()) <= 10
