"""Pruebas de la API de transcripción con un transcriptor falso."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from viralclip.api.app import create_app
from viralclip.config import Settings
from viralclip.errors import TranscriptionFailedError
from viralclip.storage import Storage
from viralclip.transcript import normalize_transcript


def sample_transcript():
    return normalize_transcript(
        {
            "language": "es",
            "duration": 12.0,
            "segments": [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "Nadie te cuenta esto",
                },
                {
                    "start": 5.5,
                    "end": 11.0,
                    "text": "El error que frena tus ventas",
                },
            ],
        }
    )


class FakeTranscriber:
    def __init__(self, *, transcript=None, error: Exception | None = None) -> None:
        self.transcript = transcript or sample_transcript()
        self.error = error
        self.calls: list[tuple[str, str | None]] = []

    def transcribe(self, media_path, *, language=None, on_stage=None):
        self.calls.append((str(media_path), language))
        if on_stage is not None:
            on_stage(15, "transcribiendo")
            on_stage(80, "transcribiendo")
        if self.error is not None:
            raise self.error
        return self.transcript


class ClientBundle:
    def __init__(
        self,
        client: TestClient,
        storage: Storage,
        settings: Settings,
        transcriber: FakeTranscriber,
    ) -> None:
        self.client = client
        self.storage = storage
        self.settings = settings
        self.transcriber = transcriber


@pytest.fixture()
def make_client(tmp_path):
    created: list[ClientBundle] = []

    def _make(
        *,
        transcriber: FakeTranscriber | None = None,
        upload_max_bytes: int = 2_000_000_000,
    ) -> ClientBundle:
        fake = transcriber or FakeTranscriber()
        settings = Settings(
            db_path=tmp_path / "viralclip.db",
            llm_enabled=False,
            api_key=None,
            max_input_bytes=2_000_000,
            max_clips=8,
            whisper_model_dir=tmp_path / "models",
            upload_dir=tmp_path / "uploads",
            upload_max_bytes=upload_max_bytes,
        )
        storage = Storage(settings.db_path)
        app = create_app(
            settings=settings,
            storage=storage,
            transcriber_factory=lambda record, settings: fake,
        )
        client = TestClient(app)
        client.__enter__()
        bundle = ClientBundle(client, storage, settings, fake)
        created.append(bundle)
        return bundle

    yield _make

    for bundle in created:
        bundle.client.__exit__(None, None, None)
        bundle.storage.close()


def test_config_exposes_whisper_settings(make_client) -> None:
    bundle = make_client()

    response = bundle.client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert "small" in data["whisper_models"]
    assert "medium" in data["whisper_models"]
    assert data["whisper_model"] == "small"
    assert data["whisper_device"] in {"cpu", "cuda"}
    assert data["upload_max_bytes"] == 2_000_000_000
    assert isinstance(data["ffmpeg_available"], bool)


def test_upload_transcribes_and_returns_result(make_client) -> None:
    bundle = make_client()

    response = bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("clip.mp4", b"video falso", "video/mp4")},
        data={"model": "small", "language": "es"},
    )

    assert response.status_code == 202, response.text
    accepted = response.json()
    assert accepted["status"] == "queued"
    assert accepted["events_url"].endswith("/events")

    detail = bundle.client.get(f"/api/transcriptions/{accepted['id']}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["status"] == "done"
    assert data["progress"] == 100
    assert data["language"] == "es"
    assert data["filename"] == "clip.mp4"
    assert data["transcript"]["segments"]
    assert data["error"] is None
    assert bundle.transcriber.calls[0][1] == "es"


def test_list_transcriptions(make_client) -> None:
    bundle = make_client()
    bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("clip.mp4", b"video falso", "video/mp4")},
    )

    response = bundle.client.get("/api/transcriptions?limit=10&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["limit"] == 10
    assert data["items"][0]["status"] == "done"
    assert data["items"][0]["transcript"] is None


def test_transcription_events_emit_done(make_client) -> None:
    bundle = make_client()
    accepted = bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("clip.mp4", b"video falso", "video/mp4")},
    ).json()

    response = bundle.client.get(f"/api/transcriptions/{accepted['id']}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in response.text
    assert '"status":"done"' in response.text


def test_upload_rejects_unsupported_extension(make_client) -> None:
    bundle = make_client()

    response = bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("notas.txt", b"hola", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VC-1101"


def test_upload_rejects_empty_file(make_client) -> None:
    bundle = make_client()

    response = bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("clip.mp4", b"", "video/mp4")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VC-1101"


def test_upload_rejects_too_large(make_client) -> None:
    bundle = make_client(upload_max_bytes=3)

    response = bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("clip.mp4", b"demasiado grande", "video/mp4")},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "VC-1102"
    assert not any(bundle.settings.upload_dir.glob("*"))


def test_upload_rejects_invalid_model(make_client) -> None:
    bundle = make_client()

    response = bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("clip.mp4", b"video", "video/mp4")},
        data={"model": "inventado"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VC-1003"


def test_create_transcription_from_local_path(make_client, tmp_path) -> None:
    bundle = make_client()
    media = tmp_path / "entrevista.mp4"
    media.write_bytes(b"video local")

    response = bundle.client.post(
        "/api/transcriptions",
        json={"path": str(media), "model": "medium", "language": "auto"},
    )

    assert response.status_code == 202, response.text
    transcription_id = response.json()["id"]
    data = bundle.client.get(f"/api/transcriptions/{transcription_id}").json()
    assert data["status"] == "done"
    assert data["model"] == "medium"
    assert data["filename"] == "entrevista.mp4"


def test_create_transcription_rejects_missing_path(make_client, tmp_path) -> None:
    bundle = make_client()

    response = bundle.client.post(
        "/api/transcriptions",
        json={"path": str(tmp_path / "no-existe.mp4")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VC-1101"


def test_get_missing_transcription(make_client) -> None:
    bundle = make_client()

    response = bundle.client.get("/api/transcriptions/no-existe")

    assert response.status_code == 404
    assert response.json()["code"] == "VC-2004"


def test_transcriber_error_marks_transcription_as_error(make_client) -> None:
    bundle = make_client(
        transcriber=FakeTranscriber(
            error=TranscriptionFailedError("No se detectó voz en el audio")
        )
    )
    accepted = bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("clip.mp4", b"video falso", "video/mp4")},
    ).json()

    data = bundle.client.get(f"/api/transcriptions/{accepted['id']}").json()

    assert data["status"] == "error"
    assert data["progress"] == 100
    assert data["error"]["code"] == "VC-1104"
    assert "voz" in data["error"]["message"]
    assert data["transcript"] is None


def test_analyze_transcription_creates_analysis(make_client) -> None:
    bundle = make_client()
    accepted = bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("clip.mp4", b"video falso", "video/mp4")},
    ).json()

    response = bundle.client.post(
        f"/api/transcriptions/{accepted['id']}/analyze",
        json={"platform": "tiktok", "max_clips": 2, "use_llm": False},
    )

    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    analysis = bundle.client.get(f"/api/analyses/{job_id}").json()
    assert analysis["status"] == "done"
    assert 1 <= len(analysis["clips"]) <= 2


def test_analyze_requires_finished_transcription(make_client) -> None:
    bundle = make_client()
    bundle.storage.create_transcription(
        transcription_id="pendiente",
        source_path=str(bundle.settings.upload_dir / "pendiente.mp4"),
        filename="pendiente.mp4",
        model="small",
        device="cpu",
        language="auto",
    )

    response = bundle.client.post(
        "/api/transcriptions/pendiente/analyze",
        json={"use_llm": False},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "VC-2002"


def test_delete_transcription_removes_uploaded_file(make_client) -> None:
    bundle = make_client()
    accepted = bundle.client.post(
        "/api/transcriptions/upload",
        files={"file": ("clip.mp4", b"video falso", "video/mp4")},
    ).json()

    source = bundle.storage.get_transcription(accepted["id"]).source_path
    assert Path(source).is_file()

    response = bundle.client.delete(f"/api/transcriptions/{accepted['id']}")

    assert response.status_code == 204
    assert not Path(source).exists()
    assert bundle.client.get(f"/api/transcriptions/{accepted['id']}").status_code == 404
