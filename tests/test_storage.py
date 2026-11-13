from __future__ import annotations

from datetime import UTC, datetime

import pytest

from viralclip.models import (
    AnalysisResult,
    Clip,
    EngineInfo,
    SourceInfo,
    SubtitleLine,
    SubtitleWord,
)
from viralclip.storage import Storage

FIXED_TIME = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def _result() -> AnalysisResult:
    line = SubtitleLine(
        index=1,
        start=0.0,
        end=1.0,
        text="Nadie te cuenta",
        words=[
            SubtitleWord(word="Nadie", start=0.0, end=0.4, highlight=True),
            SubtitleWord(word="te", start=0.4, end=0.6),
            SubtitleWord(word="cuenta", start=0.6, end=1.0, highlight=True),
        ],
    )
    clip = Clip(
        id="clip_001",
        rank=1,
        start_time="00:00",
        end_time="00:10",
        start_seconds=0.0,
        end_seconds=10.0,
        duration_seconds=10.0,
        platform="tiktok",
        hook="Nadie te cuenta esto",
        title="Nadie te cuenta esto",
        description="Un consejo directo.",
        caption_text="Nadie te cuenta esto sobre vender.",
        hashtags=["#ventas", "#tips"],
        score=0.8,
        reason="Señales: curiosidad",
        keywords=["ventas"],
        subtitles=[line],
    )
    return AnalysisResult(
        generated_at=FIXED_TIME,
        source=SourceInfo(language="es", duration=10.0, segment_count=1),
        engine=EngineInfo(name="heuristic", model=None, degraded=False),
        clips=[clip],
    )


@pytest.fixture()
def storage(tmp_path):
    store = Storage(tmp_path / "test.db")
    yield store
    store.close()


def _create(store: Storage, job_id: str = "job-1") -> None:
    store.create_job(
        job_id=job_id,
        transcript_json='{"language":"es","duration":10.0,"segments":[]}',
        platform="tiktok",
        max_clips=2,
        min_duration=15.0,
        max_duration=60.0,
        use_llm=False,
        request_id="req-1",
    )


def test_ping_and_pragmas(storage: Storage) -> None:
    assert storage.ping() is True

    journal = storage._connection.execute("PRAGMA journal_mode").fetchone()[0]
    foreign_keys = storage._connection.execute("PRAGMA foreign_keys").fetchone()[0]
    assert journal.lower() == "wal"
    assert foreign_keys == 1


def test_create_and_get_job(storage: Storage) -> None:
    _create(storage)
    job = storage.get_job("job-1")

    assert job is not None
    assert job.id == "job-1"
    assert job.status == "queued"
    assert job.platform == "tiktok"
    assert job.max_clips == 2
    assert job.use_llm is False
    assert job.request_id == "req-1"
    assert job.progress == 0
    assert job.stage == "queued"
    assert job.is_terminal is False
    assert storage.get_job("no-existe") is None


def test_complete_job_persists_result(storage: Storage) -> None:
    _create(storage)
    storage.mark_running("job-1")
    storage.complete_job("job-1", _result())

    job = storage.get_job("job-1")
    assert job is not None
    assert job.status == "done"
    assert job.engine_name == "heuristic"
    assert job.degraded is False
    assert job.progress == 100
    assert job.stage == "done"
    assert job.result_json

    result = storage.result_for(job)
    assert result is not None
    assert result.clips[0].hook == "Nadie te cuenta esto"

    clips = storage._connection.execute(
        "SELECT clip_id, rank, hashtags_json FROM clips WHERE job_id = ?",
        ("job-1",),
    ).fetchall()
    assert len(clips) == 1
    assert clips[0]["clip_id"] == "clip_001"
    assert clips[0]["rank"] == 1
    assert "#ventas" in clips[0]["hashtags_json"]


def test_fail_job(storage: Storage) -> None:
    _create(storage)
    storage.fail_job("job-1", "VC-4001", "Ollama no disponible")

    job = storage.get_job("job-1")
    assert job is not None
    assert job.status == "error"
    assert job.error_code == "VC-4001"
    assert job.error_message == "Ollama no disponible"
    assert job.progress == 100
    assert job.stage == "error"
    assert job.result_json is None
    assert storage.result_for(job) is None


def test_mark_interrupted_jobs(storage: Storage) -> None:
    _create(storage, "queued")
    _create(storage, "running")
    storage.mark_running("running")
    _create(storage, "done")
    storage.complete_job("done", _result())

    assert storage.mark_interrupted_jobs() == 2

    queued = storage.get_job("queued")
    running = storage.get_job("running")
    done = storage.get_job("done")
    assert queued is not None and queued.status == "error"
    assert running is not None and running.status == "error"
    assert done is not None and done.status == "done"
    assert queued.progress == 100 and queued.stage == "error"
    assert running.progress == 100 and running.stage == "error"
    assert "reiniciar" in (queued.error_message or "")


def test_update_progress(storage: Storage) -> None:
    _create(storage)

    assert storage.update_progress("job-1", 40, "candidatos") is True
    job = storage.get_job("job-1")
    assert job is not None
    assert job.progress == 40
    assert job.stage == "candidatos"

    storage.update_progress("job-1", 250, "clips")
    clamped = storage.get_job("job-1")
    assert clamped is not None
    assert clamped.progress == 100

    assert storage.update_progress("no-existe", 10, "x") is False


def test_migrates_old_jobs_table(tmp_path) -> None:
    import sqlite3

    db_path = tmp_path / "old.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            platform TEXT NOT NULL,
            max_clips INTEGER NOT NULL,
            min_duration REAL NOT NULL,
            max_duration REAL NOT NULL,
            use_llm INTEGER NOT NULL,
            transcript_json TEXT NOT NULL,
            result_json TEXT,
            engine_name TEXT,
            engine_model TEXT,
            degraded INTEGER,
            error_code TEXT,
            error_message TEXT,
            request_id TEXT
        )
        """
    )
    connection.commit()
    connection.close()

    store = Storage(db_path)
    try:
        columns = {
            row["name"]
            for row in store._connection.execute("PRAGMA table_info(jobs)")
        }
        assert {"progress", "stage"} <= columns
    finally:
        store.close()


def test_list_jobs_pagination(storage: Storage) -> None:
    _create(storage, "job-1")
    _create(storage, "job-2")
    _create(storage, "job-3")

    jobs, total = storage.list_jobs(limit=2, offset=0)
    assert total == 3
    assert len(jobs) == 2

    jobs_page_2, total_2 = storage.list_jobs(limit=2, offset=2)
    assert total_2 == 3
    assert len(jobs_page_2) == 1
    assert {job.id for job in jobs} | {job.id for job in jobs_page_2} == {
        "job-1",
        "job-2",
        "job-3",
    }


def test_delete_job_cascades(storage: Storage) -> None:
    _create(storage)
    storage.complete_job("job-1", _result())

    assert storage.delete_job("job-1") is True
    assert storage.get_job("job-1") is None
    clips = storage._connection.execute(
        "SELECT COUNT(*) FROM clips WHERE job_id = ?", ("job-1",)
    ).fetchone()[0]
    assert clips == 0
    assert storage.delete_job("job-1") is False


def test_settings_roundtrip(storage: Storage) -> None:
    assert storage.get_setting("tema", "claro") == "claro"

    storage.set_setting("tema", "oscuro")
    storage.set_setting("tema", "auto")

    assert storage.get_setting("tema") == "auto"
    assert storage.all_settings() == {"tema": "auto"}


def test_flags_seed_and_toggle(storage: Storage) -> None:
    flags = storage.list_flags()
    names = {flag["name"] for flag in flags}
    assert {"export_srt", "sse_progress"} <= names
    assert storage.active_flags() == ["export_srt", "sse_progress"]

    updated = storage.set_flag("export_srt", False)
    assert updated["enabled"] is False
    assert updated["description"] == "Exportación de subtítulos en SRT/VTT"
    assert storage.active_flags() == ["sse_progress"]

    created = storage.set_flag(
        "beta",
        True,
        owner="equipo",
        description="Prueba",
    )
    assert created["name"] == "beta"
    assert created["owner"] == "equipo"
    assert "beta" in storage.active_flags()


def test_flag_expiration(storage: Storage) -> None:
    storage.set_flag(
        "temporal",
        True,
        expires_at="2000-01-01T00:00:00+00:00",
    )
    storage.set_flag(
        "futuro",
        True,
        expires_at="2999-01-01T00:00:00+00:00",
    )

    active = storage.active_flags()
    assert "temporal" not in active
    assert "futuro" in active


def test_audit_log(storage: Storage) -> None:
    storage.audit(
        action="analysis.create",
        resource="analysis",
        resource_id="job-1",
        request_id="req-1",
        detail="platform=tiktok",
    )
    storage.audit(action="analysis.delete", resource="analysis", resource_id="job-1")

    entries = storage.list_audit()
    assert len(entries) == 2
    assert {entry["action"] for entry in entries} == {
        "analysis.create",
        "analysis.delete",
    }
    assert entries[0]["resource_id"] == "job-1"

def test_job_source_metadata(storage: Storage) -> None:
    storage.create_job(
        job_id="job-src",
        transcript_json='{"language":"es","duration":10.0,"segments":[]}',
        platform="tiktok",
        max_clips=2,
        min_duration=5.0,
        max_duration=60.0,
        use_llm=False,
        source_path="C:/videos/entrevista.mp4",
        transcription_id="tr-1",
    )

    job = storage.get_job("job-src")

    assert job is not None
    assert job.source_path == "C:/videos/entrevista.mp4"
    assert job.transcription_id == "tr-1"


def test_render_lifecycle(storage: Storage) -> None:
    storage.create_render(
        render_id="render-1",
        job_id="job-1",
        clip_id="clip_001",
        source_path="C:/videos/entrevista.mp4",
        transcription_id="tr-1",
    )

    record = storage.get_render("render-1")
    assert record is not None
    assert record.status == "queued"
    assert record.progress == 0
    assert record.transcription_id == "tr-1"
    assert storage.find_active_render(job_id="job-1", clip_id="clip_001") is not None

    assert storage.mark_render_running("render-1") is True
    storage.update_render_progress("render-1", 40, "renderizando")
    record = storage.get_render("render-1")
    assert record is not None
    assert record.status == "running"
    assert record.progress == 40

    storage.complete_render(
        "render-1",
        output_path="C:/renders/clip.mp4",
        thumbnail_path="C:/renders/clip.jpg",
        width=1080,
        height=1920,
        duration=10.0,
        size_bytes=1234,
    )
    record = storage.get_render("render-1")
    assert record is not None
    assert record.status == "done"
    assert record.output_path == "C:/renders/clip.mp4"
    assert record.size_bytes == 1234
    assert storage.find_active_render(job_id="job-1", clip_id="clip_001") is None

    items, total = storage.list_renders(job_id="job-1")
    assert total == 1
    assert items[0].id == "render-1"
    assert storage.find_render(job_id="job-1", clip_id="clip_001").id == "render-1"

    assert storage.delete_render("render-1") is True
    assert storage.get_render("render-1") is None


def test_fail_and_interrupt_renders(storage: Storage) -> None:
    storage.create_render(
        render_id="render-1",
        job_id="job-1",
        clip_id="clip_001",
        source_path="C:/videos/entrevista.mp4",
    )
    storage.fail_render("render-1", "VC-1203", "falló")
    record = storage.get_render("render-1")
    assert record is not None
    assert record.status == "error"
    assert record.error_code == "VC-1203"

    storage.create_render(
        render_id="render-2",
        job_id="job-1",
        clip_id="clip_002",
        source_path="C:/videos/entrevista.mp4",
    )
    assert storage.mark_interrupted_renders() == 1
    record = storage.get_render("render-2")
    assert record is not None
    assert record.status == "error"
    assert record.error_code == "VC-1203"
