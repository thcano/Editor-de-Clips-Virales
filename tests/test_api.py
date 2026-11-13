from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from viralclip.api.app import create_app
from viralclip.config import Settings
from viralclip.llm.ollama import OllamaHealth
from viralclip.storage import Storage
from viralclip.transcript import normalize_transcript

FIXTURES = Path(__file__).parent / "fixtures"
MODEL = "llama3.2:latest"


class FakeOllama:
    def __init__(
        self,
        *,
        available: bool = True,
        responses: tuple[str, ...] = (),
    ) -> None:
        self.model = MODEL
        self.available = available
        self.responses = list(responses)
        self.health_calls = 0
        self.generate_calls = 0

    def health(self) -> OllamaHealth:
        self.health_calls += 1
        if self.available:
            return OllamaHealth(True, self.model, (self.model,), "Ollama disponible")
        return OllamaHealth(
            False,
            self.model,
            (),
            "Ollama no responde. Inicia Ollama o revisa OLLAMA_BASE_URL.",
        )

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.generate_calls += 1
        if not self.responses:
            return ""
        return self.responses.pop(0)

    def close(self) -> None:
        pass


def payload() -> dict:
    return json.loads(
        (FIXTURES / "transcripcion_viral.json").read_text(encoding="utf-8")
    )


def create(client: TestClient, **overrides) -> dict:
    body = {
        "transcript": payload(),
        "platform": "tiktok",
        "max_clips": 2,
        "use_llm": False,
    }
    body.update(overrides)
    response = client.post("/api/analyses", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def test_health_with_llm_disabled(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["version"]
    assert data["ollama"]["available"] is False
    assert "desactivado" in data["ollama"]["message"]


def test_config(client: TestClient) -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert data["max_clips"] == 8
    assert data["max_input_bytes"] == 2_000_000
    assert set(data["platforms"]) == {"tiktok", "reels", "shorts"}
    assert data["llm_enabled"] is False
    assert "export_srt" in data["flags"]
    assert "small" in data["whisper_models"]
    assert "medium" in data["whisper_models"]
    assert data["whisper_model"] == "small"
    assert data["whisper_device"] in {"cpu", "cuda"}
    assert isinstance(data["ffmpeg_available"], bool)


def test_create_analysis_and_get(client: TestClient) -> None:
    accepted = create(client)

    assert accepted["status"] == "queued"
    assert accepted["events_url"].endswith("/events")

    response = client.get(f"/api/analyses/{accepted['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["progress"] == 100
    assert data["engine"]["name"] == "heuristic"
    assert data["engine"]["degraded"] is False
    assert data["error"] is None
    assert 1 <= len(data["clips"]) <= 2
    assert data["clips"][0]["hook"]


def test_create_analysis_rejects_invalid_transcript(client: TestClient) -> None:
    response = client.post(
        "/api/analyses",
        json={"transcript": {"segments": []}, "use_llm": False},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "VC-1001"
    assert data["request_id"]


def test_create_analysis_rejects_oversized_payload(tmp_path) -> None:
    settings = Settings(
        db_path=tmp_path / "small.db",
        llm_enabled=False,
        max_input_bytes=100,
    )
    storage = Storage(settings.db_path)
    try:
        with TestClient(
            create_app(settings=settings, storage=storage)
        ) as client:
            response = client.post(
                "/api/analyses",
                json={"transcript": payload(), "use_llm": False},
            )
        assert response.status_code == 413
        assert response.json()["code"] == "VC-1002"
    finally:
        storage.close()


def test_create_analysis_rejects_max_clips_over_limit(
    client: TestClient, settings: Settings
) -> None:
    response = client.post(
        "/api/analyses",
        json={
            "transcript": payload(),
            "max_clips": settings.max_clips + 1,
            "use_llm": False,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VC-1003"


def test_list_analyses_pagination(client: TestClient) -> None:
    for _ in range(3):
        create(client)

    first = client.get("/api/analyses", params={"limit": 2, "offset": 0})
    assert first.status_code == 200
    data = first.json()
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2
    assert data["items"][0]["clips"] == []

    second = client.get("/api/analyses", params={"limit": 2, "offset": 2})
    assert len(second.json()["items"]) == 1


def test_delete_analysis(client: TestClient) -> None:
    accepted = create(client)

    response = client.delete(f"/api/analyses/{accepted['id']}")
    assert response.status_code == 204

    assert client.get(f"/api/analyses/{accepted['id']}").status_code == 404
    assert client.get("/api/analyses").json()["total"] == 0


def test_analysis_not_found(client: TestClient) -> None:
    response = client.get("/api/analyses/no-existe")

    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "VC-2001"
    assert data["request_id"]


def test_validation_error_handler(client: TestClient) -> None:
    response = client.post(
        "/api/analyses",
        json={"transcript": payload(), "max_clips": 0, "use_llm": False},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VC-1003"
    assert "max_clips" in data["detail"]
    assert data["request_id"]


def test_health_reports_database_error(
    client: TestClient, storage: Storage, monkeypatch
) -> None:
    def broken_ping() -> bool:
        raise RuntimeError("base de datos bloqueada")

    monkeypatch.setattr(storage, "ping", broken_ping)

    data = client.get("/api/health").json()

    assert data["status"] == "degraded"
    assert data["database"] == "error"


def test_export_formats(client: TestClient) -> None:
    accepted = create(client)
    analysis_id = accepted["id"]

    json_export = client.get(
        f"/api/analyses/{analysis_id}/export", params={"format": "json"}
    )
    assert json_export.status_code == 200
    assert json_export.json()["version"] == "1.0"

    spec = client.get(
        f"/api/analyses/{analysis_id}/export", params={"format": "spec"}
    )
    assert spec.status_code == 200
    spec_data = spec.json()
    assert spec_data
    assert set(spec_data[0]) == {
        "start_time",
        "end_time",
        "hook",
        "caption_text",
        "hashtags",
    }

    srt = client.get(
        f"/api/analyses/{analysis_id}/export", params={"format": "srt"}
    )
    assert srt.status_code == 200
    assert srt.headers["content-type"].startswith("application/x-subrip")
    assert "-->" in srt.text
    assert "attachment" in srt.headers["content-disposition"]

    vtt = client.get(
        f"/api/analyses/{analysis_id}/export", params={"format": "vtt"}
    )
    assert vtt.status_code == 200
    assert vtt.headers["content-type"].startswith("text/vtt")
    assert vtt.text.startswith("WEBVTT")


def test_export_clip_srt(client: TestClient) -> None:
    accepted = create(client)
    detail = client.get(f"/api/analyses/{accepted['id']}").json()
    clip_id = detail["clips"][0]["id"]

    response = client.get(
        f"/api/analyses/{accepted['id']}/clips/{clip_id}/srt"
    )

    assert response.status_code == 200
    assert "-->" in response.text
    assert response.headers["content-type"].startswith("application/x-subrip")


def test_export_clip_not_found(client: TestClient) -> None:
    accepted = create(client)

    response = client.get(
        f"/api/analyses/{accepted['id']}/clips/clip_999/srt"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "VC-2001"


def test_export_not_ready(client: TestClient, storage: Storage) -> None:
    transcript = normalize_transcript(payload())
    storage.create_job(
        job_id="pendiente",
        transcript_json=transcript.model_dump_json(),
        platform="tiktok",
        max_clips=1,
        min_duration=15.0,
        max_duration=60.0,
        use_llm=False,
    )

    response = client.get("/api/analyses/pendiente/export")

    assert response.status_code == 409
    assert response.json()["code"] == "VC-2002"


def test_events_snapshot_for_done_job(client: TestClient) -> None:
    accepted = create(client)

    response = client.get(f"/api/analyses/{accepted['id']}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "retry: 3000" in response.text
    assert "id: 1" in response.text
    assert "event: done" in response.text
    assert '"status":"done"' in response.text
    assert '"progress":100' in response.text
    assert '"stage":"done"' in response.text


def test_events_respects_last_event_id(client: TestClient) -> None:
    accepted = create(client)

    response = client.get(
        f"/api/analyses/{accepted['id']}/events",
        headers={"Last-Event-ID": "7"},
    )

    assert response.status_code == 200
    assert "id: 8" in response.text
    assert "id: 1\n" not in response.text


def test_events_invalid_last_event_id_starts_at_one(client: TestClient) -> None:
    accepted = create(client)

    response = client.get(
        f"/api/analyses/{accepted['id']}/events",
        headers={"Last-Event-ID": "no-es-un-numero"},
    )

    assert response.status_code == 200
    assert "id: 1" in response.text


def test_detail_exposes_progress_and_stage(client: TestClient) -> None:
    accepted = create(client)

    data = client.get(f"/api/analyses/{accepted['id']}").json()

    assert data["status"] == "done"
    assert data["progress"] == 100
    assert data["stage"] == "done"


def test_export_srt_respects_flag(client: TestClient) -> None:
    accepted = create(client)
    analysis_id = accepted["id"]
    detail = client.get(f"/api/analyses/{analysis_id}").json()
    clip_id = detail["clips"][0]["id"]

    disabled = client.patch(
        "/api/flags", json={"name": "export_srt", "enabled": False}
    )
    assert disabled.status_code == 200

    srt = client.get(
        f"/api/analyses/{analysis_id}/export", params={"format": "srt"}
    )
    assert srt.status_code == 403
    assert srt.json()["code"] == "VC-2003"

    vtt = client.get(
        f"/api/analyses/{analysis_id}/export", params={"format": "vtt"}
    )
    assert vtt.status_code == 403

    clip_srt = client.get(
        f"/api/analyses/{analysis_id}/clips/{clip_id}/srt"
    )
    assert clip_srt.status_code == 403
    assert clip_srt.json()["code"] == "VC-2003"

    json_export = client.get(
        f"/api/analyses/{analysis_id}/export", params={"format": "json"}
    )
    assert json_export.status_code == 200

    client.patch("/api/flags", json={"name": "export_srt", "enabled": True})
    assert (
        client.get(
            f"/api/analyses/{analysis_id}/export", params={"format": "srt"}
        ).status_code
        == 200
    )


def test_sse_formatter_is_compact() -> None:
    from viralclip.api.routes import _format_sse

    message = _format_sse(
        "progress",
        {"id": "job-1", "status": "running", "progress": 40},
        3,
    )

    assert message.startswith("id: 3\nevent: progress\ndata: ")
    assert '"progress":40' in message
    assert message.endswith("\n\n")


def test_flags_list_and_update(client: TestClient) -> None:
    listed = client.get("/api/flags")
    assert listed.status_code == 200
    names = {flag["name"] for flag in listed.json()}
    assert {"export_srt", "sse_progress"} <= names

    updated = client.patch(
        "/api/flags", json={"name": "export_srt", "enabled": False}
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    config = client.get("/api/config").json()
    assert "export_srt" not in config["flags"]


def test_api_key_is_enforced(tmp_path) -> None:
    settings = Settings(
        db_path=tmp_path / "secure.db",
        llm_enabled=False,
        api_key="secreto",
    )
    storage = Storage(settings.db_path)
    try:
        with TestClient(
            create_app(settings=settings, storage=storage)
        ) as client:
            unauthorized = client.get("/api/health")
            assert unauthorized.status_code == 401
            assert unauthorized.json()["code"] == "VC-3001"

            authorized = client.get(
                "/api/health", headers={"X-API-Key": "secreto"}
            )
            assert authorized.status_code == 200

            wrong = client.get(
                "/api/health", headers={"X-API-Key": "otra"}
            )
            assert wrong.status_code == 401
    finally:
        storage.close()


def test_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"


def test_generated_request_id_when_missing(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.headers["X-Request-ID"]


def test_audit_log_records_actions(client: TestClient, storage: Storage) -> None:
    accepted = create(client)
    client.delete(f"/api/analyses/{accepted['id']}")
    client.patch("/api/flags", json={"name": "export_srt", "enabled": True})

    actions = {entry["action"] for entry in storage.list_audit()}
    assert {"analysis.create", "analysis.delete", "flag.update"} <= actions


def _client_with_ollama(tmp_path, fake: FakeOllama) -> tuple[TestClient, Storage]:
    settings = Settings(
        db_path=tmp_path / "ollama.db",
        llm_enabled=True,
        max_clips=8,
    )
    storage = Storage(settings.db_path)
    app = create_app(settings=settings, storage=storage, ollama_client=fake)
    return TestClient(app), storage


def test_analysis_uses_ollama_when_available(tmp_path) -> None:
    fake = FakeOllama(
        responses=(
            "Nadie te cuenta esto sobre vender",
            "El error que frena tus ventas",
        )
    )
    client, storage = _client_with_ollama(tmp_path, fake)
    try:
        with client:
            accepted = create(client, use_llm=True)
            detail = client.get(f"/api/analyses/{accepted['id']}").json()
    finally:
        storage.close()

    assert detail["engine"]["name"] == "heuristic+ollama"
    assert detail["engine"]["model"] == MODEL
    assert detail["engine"]["degraded"] is False
    assert [clip["hook"] for clip in detail["clips"]] == [
        "Nadie te cuenta esto sobre vender",
        "El error que frena tus ventas",
    ]


def test_analysis_degrades_when_ollama_unavailable(tmp_path) -> None:
    fake = FakeOllama(available=False)
    client, storage = _client_with_ollama(tmp_path, fake)
    try:
        with client:
            accepted = create(client, use_llm=True)
            detail = client.get(f"/api/analyses/{accepted['id']}").json()
            health = client.get("/api/health").json()
    finally:
        storage.close()

    assert detail["engine"]["name"] == "heuristic"
    assert detail["engine"]["degraded"] is True
    assert "Inicia Ollama" in detail["engine"]["notes"]
    assert health["status"] == "degraded"
    assert health["ollama"]["available"] is False


def test_health_ok_when_ollama_available(tmp_path) -> None:
    fake = FakeOllama(available=True)
    client, storage = _client_with_ollama(tmp_path, fake)
    try:
        with client:
            health = client.get("/api/health").json()
    finally:
        storage.close()

    assert health["status"] == "ok"
    assert health["ollama"]["available"] is True
