from __future__ import annotations

import json
from pathlib import Path

from viralclip.config import Settings
from viralclip.evaluation import (
    evaluate_clip,
    evaluate_result,
    hook_fidelity_ok,
    hook_format_ok,
    load_gold_cases,
    metadata_complete,
    parse_judge_response,
    run_case,
    summarize,
    timestamps_ok,
)
from viralclip.models import AnalysisResult, EngineInfo, SourceInfo
from viralclip.storage import Storage

FIXTURES = Path(__file__).parent / "fixtures"


def _case(**overrides):
    transcript = json.loads(
        (FIXTURES / "transcripcion_viral.json").read_text(encoding="utf-8")
    )
    case = {
        "case_id": "viral",
        "transcript": transcript,
        "platform": "tiktok",
        "max_clips": 2,
        "min_duration": 15,
        "max_duration": 30,
        "min_clips": 1,
        "expect_keywords": ["preguntar", "escuchar", "hablar"],
    }
    case.update(overrides)
    return case


def _evaluated():
    return run_case(_case(), settings=Settings(llm_enabled=False))


def test_hook_format_rules() -> None:
    assert hook_format_ok("Nadie te cuenta esto") is True
    assert hook_format_ok("una dos tres cuatro cinco seis siete ocho nueve diez once") is False
    assert hook_format_ok("") is False
    assert hook_format_ok("Sinergia y optimización de KPIs") is False


def test_hook_fidelity_rejects_invented_numbers() -> None:
    assert hook_fidelity_ok("Nadie te cuenta el 80%", "el 80% de las ventas", ()) is True
    assert hook_fidelity_ok("Nadie te cuenta el 90%", "el 80% de las ventas", ()) is False
    assert hook_fidelity_ok("Esto lo cambia todo", "hablar de ventas", ()) is False


def test_run_case_passes_gold_metrics() -> None:
    evaluation, result = _evaluated()

    assert result.clips
    assert evaluation.score >= 0.8
    assert evaluation.passed, evaluation.failed_metrics
    assert evaluation.failed_metrics == ()


def test_evaluate_clip_detects_problems() -> None:
    _, result = _evaluated()
    clip = result.clips[0]
    duration = result.source.duration

    assert evaluate_clip(clip, duration)["subtitles_ok"] is True

    without_subtitles = clip.model_copy(update={"subtitles": []})
    assert evaluate_clip(without_subtitles, duration)["subtitles_ok"] is False

    bad_times = clip.model_copy(update={"start_seconds": 10, "end_seconds": 5})
    assert timestamps_ok(bad_times, duration) is False

    no_hashtags = clip.model_copy(update={"hashtags": []})
    assert metadata_complete(no_hashtags) is False


def test_empty_result_fails() -> None:
    result = AnalysisResult(
        generated_at="2026-11-09T00:00:00Z",
        source=SourceInfo(language="es", duration=60, segment_count=1),
        engine=EngineInfo(name="heuristic", degraded=False),
        clips=[],
    )

    evaluation = evaluate_result(result, case_id="vacio")

    assert evaluation.score == 0.0
    assert evaluation.passed is False
    assert "hook_format" in evaluation.failed_metrics


def test_judge_response_parsing() -> None:
    parsed = parse_judge_response('{"clarity": 5, "curiosity": 4, "fidelity": 3}')

    assert parsed is not None
    assert parsed["score"] == 0.8
    assert parse_judge_response("sin json") is None
    assert parse_judge_response('{"clarity": 5}') is None
    assert parse_judge_response('{"clarity": 9, "curiosity": 4, "fidelity": 3}') is None


def test_summarize() -> None:
    assert summarize([]) == {"total": 0, "passed": 0, "failed": 0, "mean_score": 0.0}

    evaluation, _ = _evaluated()
    summary = summarize([evaluation])

    assert summary["total"] == 1
    assert summary["passed"] == 1
    assert summary["failed"] == 0


def test_load_gold_cases() -> None:
    cases = load_gold_cases(Path("docs/evaluacion/casos-oro.json"))

    assert len(cases) == 3
    assert {case["case_id"] for case in cases} == {
        "ventas-preguntar",
        "fitness-grasa",
        "productividad-miedo",
    }


def test_storage_saves_and_lists_evaluations(tmp_path) -> None:
    storage = Storage(tmp_path / "eval.db")
    try:
        first = storage.save_evaluation(
            case_id="caso-1",
            score=0.9,
            passed=True,
            model="llama3.2",
            prompt_version="judge-v1",
            detail={"metrics": {"hook_format": True}},
        )
        second = storage.save_evaluation(
            case_id="caso-2",
            score=0.5,
            passed=False,
            detail={"metrics": {"hook_format": False}},
        )

        assert first > 0 and second > first
        items = storage.list_evaluations(limit=10)
        assert len(items) == 2
        latest = items[0]
        assert latest["case_id"] == "caso-2"
        assert latest["passed"] is False
        assert latest["detail"] == {"metrics": {"hook_format": False}}
        assert items[1]["model"] == "llama3.2"
    finally:
        storage.close()
