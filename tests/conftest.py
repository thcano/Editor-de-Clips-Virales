from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from viralclip.api.app import create_app
from viralclip.config import Settings
from viralclip.storage import Storage


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        db_path=tmp_path / "viralclip.db",
        llm_enabled=False,
        api_key=None,
        max_input_bytes=2_000_000,
        max_clips=8,
        whisper_model_dir=tmp_path / "models",
        upload_dir=tmp_path / "uploads",
    )


@pytest.fixture()
def storage(settings: Settings):
    store = Storage(settings.db_path)
    yield store
    store.close()


@pytest.fixture()
def app(settings: Settings, storage: Storage):
    return create_app(settings=settings, storage=storage)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client
