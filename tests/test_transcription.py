"""Pruebas de la transcripción local (sin descargar modelos ni usar GPU)."""

from __future__ import annotations

import sys
import types
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from viralclip import transcription
from viralclip.errors import (
    FFmpegUnavailableError,
    InvalidMediaError,
    InvalidParameterError,
    MediaTooLargeError,
    TranscriptionFailedError,
)
from viralclip.transcription import (
    WhisperTranscriber,
    audio_command,
    build_document,
    detect_device,
    ffmpeg_available,
    ffmpeg_binary,
    normalize_language,
    normalize_model,
    read_wav,
    reset_model_cache,
    resolve_compute_type,
    validate_media,
)

# ---------------------------------------------------------------------------
# Normalización de opciones
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["tiny", "base", "small", "medium", "large-v3"])
def test_normalize_model_accepts_known_models(value: str) -> None:
    assert normalize_model(value) == value


def test_normalize_model_accepts_large_alias() -> None:
    assert normalize_model("large") == "large-v3"


def test_normalize_model_uses_default() -> None:
    assert normalize_model(None) == "small"
    assert normalize_model("  SMALL  ") == "small"


def test_normalize_model_rejects_unknown() -> None:
    with pytest.raises(InvalidParameterError):
        normalize_model("gigante")


@pytest.mark.parametrize("value", ["auto", "es", "en", "pt-BR"])
def test_normalize_language_accepts_valid(value: str) -> None:
    assert normalize_language(value) == value.lower()


def test_normalize_language_rejects_invalid() -> None:
    with pytest.raises(InvalidParameterError):
        normalize_language("español!")


def test_detect_device_respects_forced_values() -> None:
    assert detect_device("cpu") == "cpu"
    assert detect_device("cuda") == "cuda"


def test_detect_device_auto_uses_ctranslate2(monkeypatch) -> None:
    fake = types.ModuleType("ctranslate2")
    fake.get_cuda_device_count = lambda: 2  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ctranslate2", fake)

    assert detect_device("auto") == "cuda"


def test_detect_device_auto_without_cuda(monkeypatch) -> None:
    fake = types.ModuleType("ctranslate2")
    fake.get_cuda_device_count = lambda: 0  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ctranslate2", fake)

    assert detect_device("auto") == "cpu"


def test_detect_device_auto_survives_import_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "ctranslate2", None)

    assert detect_device("auto") == "cpu"


def test_detect_device_rejects_unknown() -> None:
    with pytest.raises(InvalidParameterError):
        detect_device("tpu")


def test_resolve_compute_type_auto() -> None:
    assert resolve_compute_type("cpu", "auto") == "int8"
    assert resolve_compute_type("cuda", "auto") == "float16"


def test_resolve_compute_type_keeps_explicit_value() -> None:
    assert resolve_compute_type("cuda", "int8") == "int8"


def test_resolve_compute_type_falls_back_on_cpu() -> None:
    assert resolve_compute_type("cpu", "float16") == "int8"


def test_resolve_compute_type_rejects_unknown() -> None:
    with pytest.raises(InvalidParameterError):
        resolve_compute_type("cpu", "bfloat16")


# ---------------------------------------------------------------------------
# FFmpeg y archivos
# ---------------------------------------------------------------------------


def test_ffmpeg_binary_raises_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(transcription.shutil, "which", lambda _: None)
    monkeypatch.setattr(transcription.Path, "is_file", lambda self: False)

    with pytest.raises(FFmpegUnavailableError):
        ffmpeg_binary("ffmpeg")


def test_ffmpeg_binary_returns_path(monkeypatch) -> None:
    monkeypatch.setattr(
        transcription.shutil, "which", lambda _: "C:/ffmpeg/bin/ffmpeg.exe"
    )
    monkeypatch.setattr(
        transcription.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout=""),
    )

    assert ffmpeg_binary("ffmpeg") == "C:/ffmpeg/bin/ffmpeg.exe"


def test_ffmpeg_binary_reports_nonzero_exit(monkeypatch) -> None:
    monkeypatch.setattr(transcription.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(
        transcription.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stderr="boom", stdout=""
        ),
    )

    with pytest.raises(FFmpegUnavailableError):
        ffmpeg_binary("ffmpeg")


def test_ffmpeg_available_true_and_false(monkeypatch) -> None:
    monkeypatch.setattr(transcription, "ffmpeg_binary", lambda _: "ffmpeg")
    assert ffmpeg_available() is True

    def broken(_: str) -> str:
        raise FFmpegUnavailableError("no")

    monkeypatch.setattr(transcription, "ffmpeg_binary", broken)
    assert ffmpeg_available() is False


def test_audio_command_extracts_wav_16k_mono(tmp_path) -> None:
    command = audio_command("ffmpeg", tmp_path / "v.mp4", tmp_path / "a.wav")

    assert command[0] == "ffmpeg"
    assert "-vn" in command
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-ar") + 1] == "16000"
    assert command[command.index("-c:a") + 1] == "pcm_s16le"
    assert command[-1].endswith("a.wav")


def test_validate_media_accepts_supported_file(tmp_path) -> None:
    media = tmp_path / "clip.MP4"
    media.write_bytes(b"datos")

    assert validate_media(media) == media


def test_validate_media_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(InvalidMediaError):
        validate_media(tmp_path / "no-existe.mp4")


def test_validate_media_rejects_unsupported_extension(tmp_path) -> None:
    media = tmp_path / "notas.txt"
    media.write_text("hola", encoding="utf-8")

    with pytest.raises(InvalidMediaError):
        validate_media(media)


def test_validate_media_rejects_too_large(tmp_path) -> None:
    media = tmp_path / "grande.mp4"
    media.write_bytes(b"12345")

    with pytest.raises(MediaTooLargeError):
        validate_media(media, max_bytes=3)


def _write_wav(path: Path, samples: np.ndarray, *, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(transcription.SAMPLE_RATE)
        handle.writeframes(samples.astype(np.int16).tobytes())


def test_read_wav_returns_float_samples(tmp_path) -> None:
    wav = tmp_path / "audio.wav"
    _write_wav(wav, np.array([0, 16384, -16384], dtype=np.int16))

    audio, duration = read_wav(wav)

    assert audio.dtype == np.float32
    assert audio.shape == (3,)
    assert duration == pytest.approx(3 / transcription.SAMPLE_RATE)
    assert audio[1] == pytest.approx(0.5, abs=1e-4)
    assert audio[2] == pytest.approx(-0.5, abs=1e-4)


def test_read_wav_rejects_invalid_file(tmp_path) -> None:
    wav = tmp_path / "audio.wav"
    wav.write_text("no es audio", encoding="utf-8")

    with pytest.raises(TranscriptionFailedError):
        read_wav(wav)


def test_read_wav_rejects_stereo(tmp_path) -> None:
    wav = tmp_path / "audio.wav"
    _write_wav(wav, np.array([1, 2, 3, 4], dtype=np.int16), channels=2)

    with pytest.raises(TranscriptionFailedError):
        read_wav(wav)


def test_build_document_uses_last_end_as_minimum_duration() -> None:
    document = build_document(
        "es",
        1.0,
        [{"start": 0.0, "end": 5.0, "text": "hola", "words": []}],
    )

    assert document["language"] == "es"
    assert document["duration"] == 5.0


# ---------------------------------------------------------------------------
# Caché de modelos
# ---------------------------------------------------------------------------


def test_model_cache_reuses_single_instance(monkeypatch, tmp_path) -> None:
    created: list[object] = []

    class FakeModel:
        def __init__(self, *args, **kwargs) -> None:
            created.append(self)

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    reset_model_cache()

    first = transcription._get_model("small", "cpu", "int8", tmp_path)
    second = transcription._get_model("small", "cpu", "int8", tmp_path)
    reset_model_cache()
    third = transcription._get_model("small", "cpu", "int8", tmp_path)

    assert first is second
    assert first is not third
    assert len(created) == 2


# ---------------------------------------------------------------------------
# WhisperTranscriber con modelo falso
# ---------------------------------------------------------------------------


class FakeWord:
    def __init__(self, word: str, start: float, end: float, probability: float) -> None:
        self.word = word
        self.start = start
        self.end = end
        self.probability = probability


class FakeSegment:
    def __init__(self, start: float, end: float, text: str, words: list[FakeWord]):
        self.start = start
        self.end = end
        self.text = text
        self.words = words


class FakeModel:
    def __init__(self, segments: list[FakeSegment], info: SimpleNamespace) -> None:
        self._segments = segments
        self._info = info
        self.calls: list[dict] = []

    def transcribe(self, audio, **kwargs):
        self.calls.append({"audio": audio, **kwargs})
        return iter(self._segments), self._info


def _fake_environment(monkeypatch, tmp_path, segments, info) -> FakeModel:
    model = FakeModel(segments, info)
    monkeypatch.setattr(transcription, "ffmpeg_binary", lambda _: "ffmpeg")
    monkeypatch.setattr(transcription, "extract_audio", lambda *a, **k: None)
    monkeypatch.setattr(
        transcription,
        "read_wav",
        lambda _: (np.zeros(16000, dtype=np.float32), 10.0),
    )
    monkeypatch.setattr(
        transcription, "_get_model", lambda *args, **kwargs: model
    )
    return model


def test_transcriber_builds_normalized_transcript(monkeypatch, tmp_path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"datos")
    segments = [
        FakeSegment(
            0.5,
            3.0,
            "Hola mundo",
            [FakeWord("Hola", 0.5, 1.0, 0.9), FakeWord("mundo", 1.0, 1.5, 0.8)],
        )
    ]
    info = SimpleNamespace(language="es", duration=10.0)
    model = _fake_environment(monkeypatch, tmp_path, segments, info)
    stages: list[tuple[int, str]] = []

    transcriber = WhisperTranscriber(
        model_size="small",
        device="cpu",
        compute_type="int8",
        language="auto",
        model_dir=tmp_path / "models",
    )
    transcript = transcriber.transcribe(media, on_stage=lambda p, s: stages.append((p, s)))

    assert transcript.language == "es"
    assert transcript.duration == 10.0
    assert len(transcript.segments) == 1
    assert transcript.segments[0].text == "Hola mundo"
    assert [word.word for word in transcript.segments[0].words] == ["Hola", "mundo"]
    assert stages[0] == (5, "extrayendo")
    assert stages[-1] == (98, "guardando")
    assert model.calls[0]["language"] is None
    assert model.calls[0]["word_timestamps"] is True


def test_transcriber_forces_language(monkeypatch, tmp_path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"datos")
    segments = [FakeSegment(0.0, 1.0, "Hello", [FakeWord("Hello", 0.0, 1.0, 1.0)])]
    info = SimpleNamespace(language="en", duration=1.0)
    model = _fake_environment(monkeypatch, tmp_path, segments, info)

    transcriber = WhisperTranscriber(
        model_size="small",
        device="cpu",
        compute_type="int8",
        language="en",
        model_dir=tmp_path / "models",
    )
    transcriber.transcribe(media)

    assert model.calls[0]["language"] == "en"


def test_transcriber_fails_without_speech(monkeypatch, tmp_path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"datos")
    info = SimpleNamespace(language="es", duration=10.0)
    _fake_environment(monkeypatch, tmp_path, [], info)

    transcriber = WhisperTranscriber(
        model_size="small",
        device="cpu",
        compute_type="int8",
        model_dir=tmp_path / "models",
    )

    with pytest.raises(TranscriptionFailedError):
        transcriber.transcribe(media)


def test_transcriber_rejects_invalid_model(tmp_path) -> None:
    with pytest.raises(InvalidParameterError):
        WhisperTranscriber(model_size="inventado", model_dir=tmp_path)
