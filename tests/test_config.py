from __future__ import annotations

import os
from pathlib import Path

import pytest

from viralclip.config import DEFAULT_CORS_ORIGINS, Settings, _load_dotenv


def test_defaults() -> None:
    settings = Settings.from_env({})

    assert settings.env == "development"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.db_path == Path("data/viralclip.db")
    assert settings.api_key is None
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS
    assert settings.max_input_bytes == 2_000_000
    assert settings.max_clips == 8
    assert settings.max_segments == 20_000
    assert settings.whisper_model == "small"
    assert settings.whisper_device == "auto"
    assert settings.whisper_compute_type == "auto"
    assert settings.whisper_language == "auto"
    assert settings.whisper_model_dir.name == "models"
    assert settings.whisper_beam_size == 5
    assert settings.whisper_vad is True
    assert settings.upload_dir.name == "uploads"
    assert settings.upload_max_bytes == 2_000_000_000
    assert settings.ffmpeg_path == "ffmpeg"
    assert settings.llm_enabled is True
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_model == "llama3.2:latest"
    assert settings.ollama_timeout == 60.0
    assert settings.ollama_health_timeout == 2.0
    assert settings.ollama_circuit_failures == 3
    assert settings.ollama_circuit_cooldown == 60.0
    assert settings.log_level == "INFO"


def test_custom_values() -> None:
    settings = Settings.from_env(
        {
            "VIRALCLIP_ENV": "production",
            "VIRALCLIP_HOST": "localhost",
            "VIRALCLIP_PORT": "9001",
            "VIRALCLIP_DB_PATH": "tmp/test.db",
            "VIRALCLIP_API_KEY": "secreto",
            "VIRALCLIP_CORS_ORIGINS": "http://a.test, http://b.test ",
            "VIRALCLIP_MAX_INPUT_BYTES": "1000",
            "VIRALCLIP_MAX_CLIPS": "3",
            "VIRALCLIP_MAX_SEGMENTS": "50",
            "VIRALCLIP_WHISPER_MODEL": "Medium",
            "VIRALCLIP_WHISPER_DEVICE": "cpu",
            "VIRALCLIP_WHISPER_COMPUTE_TYPE": "int8",
            "VIRALCLIP_WHISPER_LANGUAGE": "es",
            "VIRALCLIP_WHISPER_MODEL_DIR": "tmp/models",
            "VIRALCLIP_WHISPER_BEAM_SIZE": "3",
            "VIRALCLIP_WHISPER_VAD": "false",
            "VIRALCLIP_UPLOAD_DIR": "tmp/uploads",
            "VIRALCLIP_UPLOAD_MAX_BYTES": "12345",
            "VIRALCLIP_FFMPEG": "C:/ffmpeg/bin/ffmpeg.exe",
            "VIRALCLIP_LLM_ENABLED": "false",
            "OLLAMA_BASE_URL": "http://127.0.0.1:9999/",
            "OLLAMA_MODEL": "mistral:latest",
            "VIRALCLIP_OLLAMA_TIMEOUT": "12.5",
            "VIRALCLIP_OLLAMA_HEALTH_TIMEOUT": "0.5",
            "VIRALCLIP_OLLAMA_CIRCUIT_FAILURES": "5",
            "VIRALCLIP_OLLAMA_CIRCUIT_COOLDOWN": "30",
            "VIRALCLIP_LOG_LEVEL": "debug",
        }
    )

    assert settings.env == "production"
    assert settings.host == "localhost"
    assert settings.port == 9001
    assert settings.db_path == Path("tmp/test.db")
    assert settings.api_key == "secreto"
    assert settings.cors_origins == ("http://a.test", "http://b.test")
    assert settings.max_input_bytes == 1000
    assert settings.max_clips == 3
    assert settings.max_segments == 50
    assert settings.whisper_model == "medium"
    assert settings.whisper_device == "cpu"
    assert settings.whisper_compute_type == "int8"
    assert settings.whisper_language == "es"
    assert settings.whisper_model_dir == Path("tmp/models")
    assert settings.whisper_beam_size == 3
    assert settings.whisper_vad is False
    assert settings.upload_dir == Path("tmp/uploads")
    assert settings.upload_max_bytes == 12345
    assert settings.ffmpeg_path == "C:/ffmpeg/bin/ffmpeg.exe"
    assert settings.llm_enabled is False
    assert settings.ollama_base_url == "http://127.0.0.1:9999"
    assert settings.ollama_model == "mistral:latest"
    assert settings.ollama_timeout == 12.5
    assert settings.ollama_health_timeout == 0.5
    assert settings.ollama_circuit_failures == 5
    assert settings.ollama_circuit_cooldown == 30.0
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize("raw", ["1", "true", "yes", "si", "sí", "on", "TRUE"])
def test_bool_true_values(raw: str) -> None:
    assert Settings.from_env({"VIRALCLIP_LLM_ENABLED": raw}).llm_enabled is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "FALSE"])
def test_bool_false_values(raw: str) -> None:
    assert Settings.from_env({"VIRALCLIP_LLM_ENABLED": raw}).llm_enabled is False


def test_empty_api_key_is_none() -> None:
    assert Settings.from_env({"VIRALCLIP_API_KEY": "   "}).api_key is None


def test_empty_values_use_defaults() -> None:
    settings = Settings.from_env(
        {
            "VIRALCLIP_PORT": "   ",
            "VIRALCLIP_CORS_ORIGINS": "",
            "OLLAMA_BASE_URL": "",
        }
    )

    assert settings.port == 8000
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS
    assert settings.ollama_base_url == "http://127.0.0.1:11434"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("VIRALCLIP_PORT", "abc"),
        ("VIRALCLIP_MAX_CLIPS", "3.5"),
        ("VIRALCLIP_OLLAMA_TIMEOUT", "mucho"),
        ("VIRALCLIP_LLM_ENABLED", "quizas"),
    ],
)
def test_invalid_values_raise(name: str, value: str) -> None:
    with pytest.raises(ValueError):
        Settings.from_env({name: value})


def test_load_dotenv_reads_values(tmp_path, monkeypatch) -> None:
    fake_env: dict[str, str] = {}
    monkeypatch.setattr(os, "environ", fake_env)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comentario\n"
        "VIRALCLIP_TEST_VALUE=hola\n"
        "OTRA=\"entre comillas\"\n"
        "SIN_VALOR=\n"
        "LINEA_INVALIDA\n",
        encoding="utf-8",
    )

    _load_dotenv(env_file)

    assert fake_env["VIRALCLIP_TEST_VALUE"] == "hola"
    assert fake_env["OTRA"] == "entre comillas"
    assert fake_env["SIN_VALOR"] == ""


def test_load_dotenv_does_not_override_real_environment(tmp_path, monkeypatch) -> None:
    fake_env = {"VIRALCLIP_TEST_VALUE": "real"}
    monkeypatch.setattr(os, "environ", fake_env)
    env_file = tmp_path / ".env"
    env_file.write_text("VIRALCLIP_TEST_VALUE=archivo\n", encoding="utf-8")

    _load_dotenv(env_file)

    assert fake_env["VIRALCLIP_TEST_VALUE"] == "real"


def test_load_dotenv_ignores_missing_file(tmp_path, monkeypatch) -> None:
    fake_env: dict[str, str] = {}
    monkeypatch.setattr(os, "environ", fake_env)

    _load_dotenv(tmp_path / "no-existe.env")

    assert fake_env == {}
