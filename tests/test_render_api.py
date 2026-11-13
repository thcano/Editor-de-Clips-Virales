"""Pruebas de la API de renderizado con un renderizador falso."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from viralclip.api.app import create_app
from viralclip.config import Settings
from viralclip.errors import RenderFailedError
from viralclip.models import (
    AnalysisResult,
    Clip,
    EngineInfo,
    SourceInfo,
    SubtitleLine,
    SubtitleWord,
)
from viralclip.render import RenderResult
from viralclip.storage import Storage

FIXED_TIME = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def make_clip(clip_id: str = "clip_001") -> Clip:
    line = SubtitleLine(
        index=1,
        start=0.0,
        end=2.0,
        text="Nadie te cuenta esto",
        words=[
            SubtitleWord(word="Nadie", start=0.0, end=0.6, highlight=True),
            SubtitleWord(word="te", start=0.6, end=0.8),
            SubtitleWord(word="cuenta", start=0.8, end=1.2, highlight=True),
        ],
    )
    return Clip(
        id=clip_id,
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
        hashtags=["#ventas"],
        score=0.8,
        reason="Señales: curiosidad",
        subtitles=[line],
    )


def make_result(clip: Clip | None = None) -> AnalysisResult:
    clip = clip or make_clip()
    return AnalysisResult(
        generated_at=FIXED_TIME,
        source=SourceInfo(language="es", duration=10.0, segment_count=1),
        engine=EngineInfo(name="heuristic", model=None, degraded=False),
        clips=[clip],
    )


class FakeRenderer:
    def __init__(self, settings: Settings, *, error: Exception | None = None) -> None:
        self.settings = settings
        self.error = error
        self.calls: list[dict] = []

    def render(
        self,
        *,
        source_path,
        clip,
        render_id,
        job_id,
        output_dir=None,
        progress=None,
    ):
        self.calls.append(
            {
                "source_path": str(source_path),
                "clip_id": clip.id,
                "render_id": render_id,
                "job_id": job_id,
            }
        )
        if progress is not None:
            progress(20, "renderizando")
            progress(90, "miniatura")
        if self.error is not None:
            raise self.error

        target = Path(output_dir or self.settings.render_dir)
        target.mkdir(parents=True, exist_ok=True)
        output = target / f"{job_id}_{clip.id}_{render_id}.mp4"
        thumbnail = target / f"{job_id}_{clip.id}_{render_id}.jpg"
        output.write_bytes(b"fake-mp4")
        thumbnail.write_bytes(b"fake-jpg")
        return RenderResult(
            output_path=output,
            thumbnail_path=thumbnail,
            width=self.settings.render_width,
            height=self.settings.render_height,
            duration=clip.duration_seconds,
            size_bytes=output.stat().st_size,
        )


class Bundle:
    def __init__(
        self,
        client: TestClient,
        storage: Storage,
        settings: Settings,
        renderer: FakeRenderer,
        video: Path,
    ) -> None:
        self.client = client
        self.storage = storage
        self.settings = settings
        self.renderer = renderer
        self.video = video


@pytest.fixture()
def make_bundle(tmp_path):
    created: list[Bundle] = []

    def _make(
        *,
        status: str = "done",
        source_path: str | None = "__VIDEO__",
        renderer_error: Exception | None = None,
    ) -> Bundle:
        settings = Settings(
            db_path=tmp_path / "viralclip.db",
            llm_enabled=False,
            api_key=None,
            render_dir=tmp_path / "renders",
        )
        storage = Storage(settings.db_path)
        video = tmp_path / "video.mp4"
        video.write_bytes(b"video-falso")
        resolved_source = str(video) if source_path == "__VIDEO__" else source_path
        renderer = FakeRenderer(settings, error=renderer_error)
        app = create_app(
            settings=settings,
            storage=storage,
            renderer_factory=lambda _settings: renderer,
        )
        client = TestClient(app)
        client.__enter__()

        storage.create_job(
            job_id="job-1",
            transcript_json='{"language":"es","duration":10.0,"segments":[]}',
            platform="tiktok",
            max_clips=2,
            min_duration=5.0,
            max_duration=60.0,
            use_llm=False,
            request_id="req-1",
            source_path=resolved_source,
            transcription_id="tr-1" if resolved_source else None,
        )
        if status == "done":
            storage.mark_running("job-1")
            storage.complete_job("job-1", make_result())

        bundle = Bundle(client, storage, settings, renderer, video)
        created.append(bundle)
        return bundle

    yield _make

    for bundle in created:
        bundle.client.__exit__(None, None, None)
        bundle.storage.close()


def test_create_render_and_download(make_bundle) -> None:
    bundle = make_bundle()

    response = bundle.client.post(
        "/api/analyses/job-1/clips/clip_001/render", json={}
    )

    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "queued"
    assert accepted["events_url"].startswith("/api/renders/")

    record = bundle.storage.get_render(accepted["id"])
    assert record is not None
    assert record.status == "done"
    assert record.transcription_id == "tr-1"
    assert record.width == 1080
    assert record.height == 1920
    assert record.output_path and Path(record.output_path).is_file()
    assert record.thumbnail_path and Path(record.thumbnail_path).is_file()

    listing = bundle.client.get("/api/renders?job_id=job-1").json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["download_url"].endswith("/download")
    assert item["thumbnail_url"].endswith("/thumbnail")

    detail = bundle.client.get(f"/api/renders/{accepted['id']}")
    assert detail.status_code == 200
    assert detail.json()["clip_id"] == "clip_001"

    download = bundle.client.get(item["download_url"])
    assert download.status_code == 200
    assert download.content == b"fake-mp4"
    assert download.headers["content-type"].startswith("video/mp4")

    thumbnail = bundle.client.get(item["thumbnail_url"])
    assert thumbnail.status_code == 200
    assert thumbnail.content == b"fake-jpg"
    assert thumbnail.headers["content-type"].startswith("image/jpeg")


def test_render_events_returns_done(make_bundle) -> None:
    bundle = make_bundle()
    accepted = bundle.client.post(
        "/api/analyses/job-1/clips/clip_001/render", json={}
    ).json()

    response = bundle.client.get(f"/api/renders/{accepted['id']}/events")

    assert response.status_code == 200
    assert "event: done" in response.text


def test_render_uses_manual_video_path(make_bundle, tmp_path) -> None:
    bundle = make_bundle(source_path=None)
    manual = tmp_path / "manual.mp4"
    manual.write_bytes(b"manual")

    response = bundle.client.post(
        "/api/analyses/job-1/clips/clip_001/render",
        json={"video_path": str(manual)},
    )

    assert response.status_code == 202
    assert bundle.renderer.calls[0]["source_path"] == str(manual)


def test_render_requires_source(make_bundle) -> None:
    bundle = make_bundle(source_path=None)

    response = bundle.client.post(
        "/api/analyses/job-1/clips/clip_001/render", json={}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VC-1201"


def test_render_rejects_missing_analysis(make_bundle) -> None:
    bundle = make_bundle()

    response = bundle.client.post(
        "/api/analyses/no-existe/clips/clip_001/render", json={}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "VC-2001"


def test_render_rejects_missing_clip(make_bundle) -> None:
    bundle = make_bundle()

    response = bundle.client.post(
        "/api/analyses/job-1/clips/clip_999/render", json={}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "VC-2001"


def test_render_rejects_unfinished_analysis(make_bundle) -> None:
    bundle = make_bundle(status="queued")

    response = bundle.client.post(
        "/api/analyses/job-1/clips/clip_001/render", json={}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "VC-2002"


def test_render_conflict_and_force(make_bundle) -> None:
    bundle = make_bundle()
    bundle.storage.create_render(
        render_id="active",
        job_id="job-1",
        clip_id="clip_001",
        source_path=str(bundle.video),
    )

    response = bundle.client.post(
        "/api/analyses/job-1/clips/clip_001/render", json={}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "VC-1204"

    forced = bundle.client.post(
        "/api/analyses/job-1/clips/clip_001/render", json={"force": True}
    )
    assert forced.status_code == 202


def test_render_failure_is_persisted(make_bundle) -> None:
    bundle = make_bundle(renderer_error=RenderFailedError("FFmpeg falló"))

    accepted = bundle.client.post(
        "/api/analyses/job-1/clips/clip_001/render", json={}
    ).json()

    record = bundle.storage.get_render(accepted["id"])
    assert record is not None
    assert record.status == "error"
    assert record.error_code == "VC-1203"

    detail = bundle.client.get(f"/api/renders/{accepted['id']}").json()
    assert detail["status"] == "error"
    assert detail["error"]["code"] == "VC-1203"


def test_delete_render_removes_files(make_bundle) -> None:
    bundle = make_bundle()
    accepted = bundle.client.post(
        "/api/analyses/job-1/clips/clip_001/render", json={}
    ).json()
    record = bundle.storage.get_render(accepted["id"])
    assert record is not None
    output = Path(record.output_path)
    thumbnail = Path(record.thumbnail_path)

    response = bundle.client.delete(f"/api/renders/{accepted['id']}")

    assert response.status_code == 204
    assert bundle.storage.get_render(accepted["id"]) is None
    assert not output.exists()
    assert not thumbnail.exists()


def test_delete_running_render_conflicts(make_bundle) -> None:
    bundle = make_bundle()
    bundle.storage.create_render(
        render_id="active",
        job_id="job-1",
        clip_id="clip_001",
        source_path=str(bundle.video),
    )

    response = bundle.client.delete("/api/renders/active")

    assert response.status_code == 409
    assert response.json()["code"] == "VC-1204"


def test_missing_render_returns_404(make_bundle) -> None:
    bundle = make_bundle()

    assert bundle.client.get("/api/renders/no-existe").status_code == 404
    assert (
        bundle.client.get("/api/renders/no-existe/download").json()["code"]
        == "VC-2005"
    )


def test_config_exposes_render_settings(make_bundle) -> None:
    bundle = make_bundle()

    config = bundle.client.get("/api/config").json()

    assert config["render_width"] == 1080
    assert config["render_height"] == 1920
    assert config["render_fps"] == 30
    assert config["render_crf"] == 20
    assert config["render_preset"] == "veryfast"
    assert isinstance(config["ffprobe_available"], bool)
