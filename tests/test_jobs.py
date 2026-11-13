from __future__ import annotations

import json
from pathlib import Path

from viralclip.api.jobs import run_analysis_job
from viralclip.config import Settings
from viralclip.storage import Storage
from viralclip.transcript import normalize_transcript

FIXTURES = Path(__file__).parent / "fixtures"


def _transcript_json() -> str:
    payload = json.loads(
        (FIXTURES / "transcripcion_viral.json").read_text(encoding="utf-8")
    )
    return normalize_transcript(payload).model_dump_json()


def _create(store: Storage, *, job_id: str, transcript_json: str, **overrides) -> None:
    options = {
        "platform": "tiktok",
        "max_clips": 1,
        "min_duration": 15.0,
        "max_duration": 30.0,
        "use_llm": False,
    }
    options.update(overrides)
    store.create_job(job_id=job_id, transcript_json=transcript_json, **options)


def test_job_completes(tmp_path) -> None:
    storage = Storage(tmp_path / "jobs.db")
    try:
        _create(storage, job_id="ok", transcript_json=_transcript_json())

        run_analysis_job(
            storage=storage,
            settings=Settings(llm_enabled=False),
            job_id="ok",
        )

        job = storage.get_job("ok")
        assert job is not None
        assert job.status == "done"
        assert job.progress == 100
        assert job.stage == "done"
        assert job.result_json
    finally:
        storage.close()


def test_job_with_invalid_transcript_fails_internal(tmp_path) -> None:
    storage = Storage(tmp_path / "jobs.db")
    try:
        _create(storage, job_id="bad", transcript_json="{}")

        run_analysis_job(
            storage=storage,
            settings=Settings(llm_enabled=False),
            job_id="bad",
        )

        job = storage.get_job("bad")
        assert job is not None
        assert job.status == "error"
        assert job.error_code == "VC-5001"
        assert job.progress == 100
        assert job.stage == "error"
        assert "Error interno" in (job.error_message or "")
    finally:
        storage.close()


def test_job_with_invalid_parameters_fails_with_domain_code(tmp_path) -> None:
    storage = Storage(tmp_path / "jobs.db")
    try:
        _create(
            storage,
            job_id="params",
            transcript_json=_transcript_json(),
            min_duration=0.0,
        )

        run_analysis_job(
            storage=storage,
            settings=Settings(llm_enabled=False),
            job_id="params",
        )

        job = storage.get_job("params")
        assert job is not None
        assert job.status == "error"
        assert job.error_code == "VC-1003"
        assert job.progress == 100
        assert job.stage == "error"
    finally:
        storage.close()


def test_job_missing_is_ignored(tmp_path) -> None:
    storage = Storage(tmp_path / "jobs.db")
    try:
        run_analysis_job(
            storage=storage,
            settings=Settings(llm_enabled=False),
            job_id="no-existe",
        )
    finally:
        storage.close()
