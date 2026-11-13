"""Evaluación de calidad de los clips y ganchos.

El módulo separa dos capas:

- **Determinista:** métricas de formato, fidelidad, metadatos, subtítulos y
  tiempos. Es la fuente de verdad y no depende de Ollama.
- **Juez LLM opcional:** puntúa claridad, curiosidad y fidelidad. Si falla o
  devuelve algo inválido, la evaluación determinista sigue siendo válida.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .errors import OllamaUnavailableError
from .hooks import is_valid_hook
from .lexicon import NUMBER_RE, STOPWORDS, normalize_token, tokenize
from .llm.ollama import OllamaClient
from .llm.prompts import (
    JUDGE_SYSTEM_PROMPT,
    build_judge_prompt,
    parse_judge_response,
)
from .models import AnalysisResult, Clip
from .pipeline import analyze
from .transcript import normalize_transcript

PASS_THRESHOLD = 0.8
PROMPT_VERSION = "judge-v1"
CRITICAL_METRICS = frozenset({"hook_format", "hook_fidelity"})
METRIC_NAMES = (
    "hook_format",
    "hook_fidelity",
    "hook_not_corporate",
    "metadata_complete",
    "subtitles_ok",
    "timestamps_ok",
    "hook_unique",
    "clip_count",
    "expected_keywords",
)


def _significant_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in tokenize(text):
        normalized = normalize_token(token)
        if len(normalized) > 2 and normalized not in STOPWORDS:
            tokens.add(normalized)
    return tokens


def _numbers(text: str) -> set[str]:
    return {match.replace(" ", "") for match in NUMBER_RE.findall(text)}


def hook_format_ok(hook: str) -> bool:
    return is_valid_hook(hook)


def hook_fidelity_ok(hook: str, text: str, keywords: list[str] | tuple[str, ...] = ()) -> bool:
    """Comprueba que el gancho se apoye en el texto y no invente cifras."""

    hook_tokens = _significant_tokens(hook)
    source_tokens = _significant_tokens(text)
    keyword_tokens = {normalize_token(keyword) for keyword in keywords if keyword}
    if not hook_tokens & (source_tokens | keyword_tokens):
        return False
    return not (_numbers(hook) - _numbers(text))


def metadata_complete(clip: Clip) -> bool:
    return bool(
        clip.title.strip()
        and clip.description.strip()
        and clip.caption_text.strip()
        and 1 <= len(clip.hashtags) <= 12
    )


def subtitles_ok(clip: Clip) -> bool:
    if not clip.subtitles:
        return False
    previous_start = -1.0
    for line in clip.subtitles:
        words = [word for word in line.text.split() if word.strip()]
        if not 1 <= len(words) <= 5:
            return False
        if line.end <= line.start:
            return False
        if line.start < previous_start:
            return False
        previous_start = line.start
    return True


def timestamps_ok(clip: Clip, duration: float) -> bool:
    return bool(
        0 <= clip.start_seconds < clip.end_seconds <= duration + 0.5
    )


def evaluate_clip(clip: Clip, duration: float) -> dict[str, bool]:
    return {
        "hook_format": hook_format_ok(clip.hook),
        "hook_fidelity": hook_fidelity_ok(clip.hook, clip.caption_text, clip.keywords),
        "hook_not_corporate": is_valid_hook(clip.hook),
        "metadata_complete": metadata_complete(clip),
        "subtitles_ok": subtitles_ok(clip),
        "timestamps_ok": timestamps_ok(clip, duration),
    }


@dataclass(frozen=True)
class CaseEvaluation:
    """Resultado de evaluar un análisis completo contra las métricas."""

    case_id: str
    score: float
    passed: bool
    metrics: dict[str, bool]
    clip_scores: list[float] = field(default_factory=list)
    failed_metrics: tuple[str, ...] = ()
    judge: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "score": self.score,
            "passed": self.passed,
            "metrics": dict(self.metrics),
            "clip_scores": list(self.clip_scores),
            "failed_metrics": list(self.failed_metrics),
            "judge": dict(self.judge) if self.judge else None,
        }


def evaluate_result(
    result: AnalysisResult,
    *,
    case_id: str = "analysis",
    min_clips: int = 1,
    expect_keywords: list[str] | tuple[str, ...] = (),
) -> CaseEvaluation:
    """Evalúa un ``AnalysisResult`` con métricas deterministas."""

    duration = result.source.duration
    clips = result.clips

    if not clips:
        metrics = {name: False for name in METRIC_NAMES}
        return CaseEvaluation(
            case_id=case_id,
            score=0.0,
            passed=False,
            metrics=metrics,
            failed_metrics=tuple(METRIC_NAMES),
        )

    clip_metrics = [evaluate_clip(clip, duration) for clip in clips]
    metrics: dict[str, bool] = {}
    for name in (
        "hook_format",
        "hook_fidelity",
        "hook_not_corporate",
        "metadata_complete",
        "subtitles_ok",
        "timestamps_ok",
    ):
        metrics[name] = all(item[name] for item in clip_metrics)

    hooks = [normalize_token(clip.hook) for clip in clips]
    metrics["hook_unique"] = len(hooks) == len(set(hooks))
    metrics["clip_count"] = len(clips) >= min_clips

    normalized_keywords = [normalize_token(keyword) for keyword in expect_keywords if keyword]
    if normalized_keywords:
        metrics["expected_keywords"] = any(
            keyword in normalize_token(clip.hook)
            for keyword in normalized_keywords
            for clip in clips
        )
    else:
        metrics["expected_keywords"] = True

    clip_scores = [
        sum(1 for value in item.values() if value) / len(item)
        for item in clip_metrics
    ]
    score = round(sum(1 for value in metrics.values() if value) / len(metrics), 4)
    failed = tuple(name for name, value in metrics.items() if not value)
    passed = (
        score >= PASS_THRESHOLD
        and not (CRITICAL_METRICS & set(failed))
        and metrics["clip_count"]
    )

    return CaseEvaluation(
        case_id=case_id,
        score=score,
        passed=passed,
        metrics=metrics,
        clip_scores=[round(value, 4) for value in clip_scores],
        failed_metrics=failed,
    )


def load_gold_cases(path: str | Path) -> list[dict[str, Any]]:
    """Carga el set de oro desde un JSON con lista o clave ``cases``."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("cases", [])
    if not isinstance(data, list):
        raise ValueError("El set de oro debe ser una lista o un objeto con 'cases'")
    return [case for case in data if isinstance(case, dict)]


def run_case(
    case: dict[str, Any],
    *,
    use_llm: bool = False,
    settings: Settings | None = None,
    ollama_client: OllamaClient | None = None,
) -> tuple[CaseEvaluation, AnalysisResult]:
    """Normaliza la transcripción del caso, ejecuta el pipeline y lo evalúa."""

    case_id = str(case.get("case_id") or "caso")
    transcript = normalize_transcript(case["transcript"])
    result = analyze(
        transcript,
        platform=str(case.get("platform", "tiktok")),
        max_clips=int(case.get("max_clips", 3)),
        min_duration=float(case.get("min_duration", 15.0)),
        max_duration=float(case.get("max_duration", 60.0)),
        use_llm=use_llm,
        settings=settings,
        ollama_client=ollama_client,
    )
    evaluation = evaluate_result(
        result,
        case_id=case_id,
        min_clips=int(case.get("min_clips", 1)),
        expect_keywords=case.get("expect_keywords", []),
    )
    return evaluation, result


def judge_hook(
    client: OllamaClient,
    hook: str,
    source_text: str,
) -> dict[str, Any] | None:
    """Pide al LLM una puntuación del gancho; ``None`` si falla o no valida."""

    try:
        raw = client.generate(
            build_judge_prompt(hook, source_text),
            system=JUDGE_SYSTEM_PROMPT,
        )
    except OllamaUnavailableError:
        return None
    parsed = parse_judge_response(raw)
    if parsed is None:
        return None
    return {"model": client.model, "prompt_version": PROMPT_VERSION, **parsed}


def summarize(evaluations: list[CaseEvaluation]) -> dict[str, Any]:
    if not evaluations:
        return {"total": 0, "passed": 0, "failed": 0, "mean_score": 0.0}
    scores = [evaluation.score for evaluation in evaluations]
    passed = sum(1 for evaluation in evaluations if evaluation.passed)
    return {
        "total": len(evaluations),
        "passed": passed,
        "failed": len(evaluations) - passed,
        "mean_score": round(sum(scores) / len(scores), 4),
        "min_score": round(min(scores), 4),
    }
