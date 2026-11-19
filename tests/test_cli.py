from __future__ import annotations

from pathlib import Path

import pytest

from viralclip import __version__, cli
from viralclip.config import Settings


class FakeServer:
    def __init__(self) -> None:
        self.started = False
        self.should_exit = False
        self.run_called = False

    def run(self) -> None:
        self.run_called = True
        self.started = True


class NeverStartedServer:
    started = False
    should_exit = False

    def run(self) -> None:
        return


def test_build_parser_defaults() -> None:
    args = cli.build_parser().parse_args([])

    assert args.host is None
    assert args.port is None
    assert args.db is None
    assert args.no_browser is False
    assert args.transcribe is None
    assert args.output is None
    assert args.model is None
    assert args.language is None
    assert args.compute_type is None


def test_apply_overrides() -> None:
    settings = Settings(db_path=Path("base.db"), host="127.0.0.1", port=8000)
    args = cli.build_parser().parse_args(
        ["--host", "0.0.0.0", "--port", "9000", "--db", "otra.db"]
    )

    updated = cli.apply_overrides(settings, args)

    assert updated.host == "0.0.0.0"
    assert updated.port == 9000
    assert updated.db_path == Path("otra.db")


def test_apply_overrides_without_changes_keeps_settings() -> None:
    settings = Settings(db_path=Path("base.db"))
    args = cli.build_parser().parse_args([])

    assert cli.apply_overrides(settings, args) is settings


def test_resolve_port_returns_requested() -> None:
    assert cli.resolve_port("127.0.0.1", 8123) == 8123


def test_resolve_port_zero_returns_free_port() -> None:
    port = cli.resolve_port("127.0.0.1", 0)

    assert 0 < port <= 65535


def test_build_url() -> None:
    assert cli.build_url("127.0.0.1", 8000) == "http://127.0.0.1:8000"
    assert cli.build_url("127.0.0.1", 8000, "abc123") == "http://127.0.0.1:8000?v=abc123"


def test_serve_opens_browser_and_stops() -> None:
    opened: list[str] = []
    server = FakeServer()

    cli.serve(
        object(),
        "127.0.0.1",
        8123,
        server_factory=lambda *args: server,
        browser_open=opened.append,
    )

    assert server.run_called is True
    assert server.should_exit is True
    # El navegador se abre con una URL versionada para que una copia en caché
    # de la interfaz no impida ver la versión vigente del diseño.
    assert len(opened) == 1
    assert opened[0].startswith("http://127.0.0.1:8123?v=")
    assert len(opened[0].split("v=")[1]) == 10


def test_serve_without_browser() -> None:
    opened: list[str] = []
    server = FakeServer()

    cli.serve(
        object(),
        "127.0.0.1",
        8124,
        open_browser=False,
        server_factory=lambda *args: server,
        browser_open=opened.append,
    )

    assert opened == []


def test_serve_raises_when_server_does_not_start() -> None:
    server = NeverStartedServer()

    with pytest.raises(RuntimeError):
        cli.serve(
            object(),
            "127.0.0.1",
            8125,
            start_timeout=0.1,
            server_factory=lambda *args: server,
            browser_open=lambda url: True,
        )

    assert server.should_exit is True


def test_main_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])

    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_main_delegates_to_serve(monkeypatch, tmp_path) -> None:
    calls: list[tuple[object, str, int, dict]] = []

    def fake_serve(app, host, port, **kwargs) -> None:
        calls.append((app, host, port, kwargs))

    settings = Settings(db_path=tmp_path / "base.db", llm_enabled=False)
    monkeypatch.setattr(
        cli.Settings, "from_env", classmethod(lambda cls: settings)
    )
    monkeypatch.setattr(cli, "create_app", lambda settings=None: object())
    monkeypatch.setattr(cli, "serve", fake_serve)

    code = cli.main(
        ["--host", "127.0.0.1", "--port", "0", "--db", str(tmp_path / "x.db"), "--no-browser"]
    )

    assert code == 0
    assert len(calls) == 1
    _, host, port, kwargs = calls[0]
    assert host == "127.0.0.1"
    assert 0 < port <= 65535
    assert kwargs["open_browser"] is False


def test_main_returns_error_when_server_fails(monkeypatch, tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "base.db", llm_enabled=False)
    monkeypatch.setattr(
        cli.Settings, "from_env", classmethod(lambda cls: settings)
    )
    monkeypatch.setattr(cli, "create_app", lambda settings=None: object())

    def failing_serve(*args, **kwargs) -> None:
        raise RuntimeError("sin arranque")

    monkeypatch.setattr(cli, "serve", failing_serve)

    assert cli.main(["--no-browser", "--port", "0"]) == 1


def test_main_uses_desktop_window_by_default(monkeypatch, tmp_path) -> None:
    """Por defecto la app se abre en su propia ventana, no en el navegador."""

    calls: list[dict] = []

    def fake_serve_window(app, host, port, **kwargs) -> int:
        calls.append({"host": host, "port": port, **kwargs})
        return 0

    settings = Settings(db_path=tmp_path / "base.db", llm_enabled=False)
    monkeypatch.setattr(
        cli.Settings, "from_env", classmethod(lambda cls: settings)
    )
    monkeypatch.setattr(cli, "create_app", lambda settings=None: object())
    monkeypatch.setattr(cli, "serve_window", fake_serve_window)
    monkeypatch.setattr(
        cli, "serve", lambda *a, **k: pytest.fail("no debe usarse el navegador")
    )

    code = cli.main(["--host", "127.0.0.1", "--port", "0"])

    assert code == 0
    assert len(calls) == 1
    assert calls[0]["host"] == "127.0.0.1"
    assert 0 < calls[0]["port"] <= 65535


def test_main_browser_flag_uses_serve(monkeypatch, tmp_path) -> None:
    calls: list[dict] = []

    def fake_serve(app, host, port, **kwargs) -> None:
        calls.append({"host": host, "port": port, **kwargs})

    settings = Settings(db_path=tmp_path / "base.db", llm_enabled=False)
    monkeypatch.setattr(
        cli.Settings, "from_env", classmethod(lambda cls: settings)
    )
    monkeypatch.setattr(cli, "create_app", lambda settings=None: object())
    monkeypatch.setattr(cli, "serve", fake_serve)
    monkeypatch.setattr(
        cli, "serve_window", lambda *a, **k: pytest.fail("no debe abrirse la ventana")
    )

    code = cli.main(["--browser", "--port", "0"])

    assert code == 0
    assert len(calls) == 1
    assert calls[0]["open_browser"] is True


def test_serve_window_opens_versioned_url_and_stops_server(monkeypatch) -> None:
    opened: list[dict] = []

    def fake_factory(app, host, port, log_level):
        return FakeServer()

    def fake_runner(url, **kwargs):
        opened.append({"url": url, **kwargs})
        kwargs["on_closed"]()
        return 0

    cli.serve_window(
        object(),
        "127.0.0.1",
        8123,
        server_factory=fake_factory,
        window_runner=fake_runner,
    )

    assert len(opened) == 1
    assert opened[0]["url"].startswith("http://127.0.0.1:8123?v=")
    assert callable(opened[0]["on_closed"])


class FakeTranscriber:
    def __init__(self, transcript, *, error: Exception | None = None) -> None:
        self.transcript = transcript
        self.error = error
        self.kwargs: dict = {}
        self.media: str | None = None
        self.stages: list[tuple[int, str]] = []

    def transcribe(self, media, *, on_stage=None):
        self.media = media
        if on_stage is not None:
            on_stage(5, "extrayendo")
            self.stages.append((5, "extrayendo"))
        if self.error is not None:
            raise self.error
        return self.transcript


def _sample_transcript():
    from viralclip.transcript import normalize_transcript

    return normalize_transcript(
        {
            "language": "es",
            "duration": 3.0,
            "segments": [{"start": 0.0, "end": 2.0, "text": "Hola mundo"}],
        }
    )


def test_transcribe_command_writes_json(monkeypatch, tmp_path, capsys) -> None:
    import viralclip.transcription as transcription_module

    fake = FakeTranscriber(_sample_transcript())

    def factory(**kwargs):
        fake.kwargs = kwargs
        return fake

    monkeypatch.setattr(transcription_module, "WhisperTranscriber", factory)
    media = tmp_path / "video.mp4"
    media.write_bytes(b"datos")
    output = tmp_path / "salida.json"
    settings = Settings(
        db_path=tmp_path / "base.db",
        whisper_model_dir=tmp_path / "models",
    )
    args = cli.build_parser().parse_args(
        [
            "--transcribe",
            str(media),
            "--output",
            str(output),
            "--model",
            "medium",
            "--language",
            "es",
            "--compute-type",
            "int8",
        ]
    )

    code = cli.transcribe_command(args, settings)

    assert code == 0
    assert fake.media == str(media)
    assert fake.kwargs["model_size"] == "medium"
    assert fake.kwargs["language"] == "es"
    assert fake.kwargs["compute_type"] == "int8"
    assert output.is_file()
    assert '"language": "es"' in output.read_text(encoding="utf-8")
    assert "Transcripción guardada" in capsys.readouterr().out


def test_transcribe_command_reports_error(monkeypatch, tmp_path, capsys) -> None:
    import viralclip.transcription as transcription_module
    from viralclip.errors import FFmpegUnavailableError

    fake = FakeTranscriber(
        _sample_transcript(), error=FFmpegUnavailableError("FFmpeg no está")
    )
    monkeypatch.setattr(
        transcription_module,
        "WhisperTranscriber",
        lambda **kwargs: fake,
    )
    media = tmp_path / "video.mp4"
    media.write_bytes(b"datos")
    args = cli.build_parser().parse_args(["--transcribe", str(media)])
    settings = Settings(
        db_path=tmp_path / "base.db",
        whisper_model_dir=tmp_path / "models",
    )

    code = cli.transcribe_command(args, settings)

    assert code == 1
    assert "VC-1103" in capsys.readouterr().err
    assert not (tmp_path / "video.transcript.json").exists()

def _render_analysis(tmp_path):
    from datetime import UTC, datetime

    from viralclip.models import AnalysisResult, Clip, EngineInfo, SourceInfo

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
        hashtags=["#ventas"],
        score=0.8,
        reason="Señales: curiosidad",
    )
    result = AnalysisResult(
        generated_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        source=SourceInfo(language="es", duration=10.0, segment_count=1),
        engine=EngineInfo(name="heuristic", model=None, degraded=False),
        clips=[clip],
    )
    path = tmp_path / "analisis.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    return path


class FakeRenderer:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.kwargs: dict = {}

    def render(self, **kwargs):
        from viralclip.render import RenderResult

        self.kwargs = kwargs
        output = Path(self.settings.render_dir) / "clip.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        thumbnail = output.with_suffix(".jpg")
        thumbnail.write_bytes(b"jpg")
        return RenderResult(
            output_path=output,
            thumbnail_path=thumbnail,
            width=1080,
            height=1920,
            duration=10.0,
            size_bytes=3,
        )


def test_render_command_writes_output(monkeypatch, tmp_path, capsys) -> None:
    import viralclip.render as render_module

    analysis = _render_analysis(tmp_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"datos")
    fake = FakeRenderer(Settings(render_dir=tmp_path / "renders"))

    def factory(settings):
        fake.settings = settings
        return fake

    monkeypatch.setattr(render_module, "FFmpegRenderer", factory)
    args = cli.build_parser().parse_args(
        [
            "--render",
            str(analysis),
            "--clip",
            "clip_001",
            "--video",
            str(video),
            "--render-output",
            str(tmp_path / "salida"),
        ]
    )
    settings = Settings(db_path=tmp_path / "base.db")

    code = cli.render_command(args, settings)

    assert code == 0
    assert fake.kwargs["source_path"] == str(video)
    assert fake.kwargs["clip"].id == "clip_001"
    assert fake.settings.render_dir == tmp_path / "salida"
    out = capsys.readouterr().out
    assert "Video renderizado" in out
    assert "Miniatura" in out


def test_render_command_requires_video(tmp_path, capsys) -> None:
    analysis = _render_analysis(tmp_path)
    args = cli.build_parser().parse_args(["--render", str(analysis)])

    code = cli.render_command(args, Settings(db_path=tmp_path / "base.db"))

    assert code == 1
    assert "requiere --video" in capsys.readouterr().err


def test_render_command_rejects_unknown_clip(tmp_path, capsys) -> None:
    analysis = _render_analysis(tmp_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"datos")
    args = cli.build_parser().parse_args(
        ["--render", str(analysis), "--clip", "clip_999", "--video", str(video)]
    )

    code = cli.render_command(args, Settings(db_path=tmp_path / "base.db"))

    assert code == 1
    assert "no existe el clip" in capsys.readouterr().err


def test_render_command_rejects_missing_analysis(tmp_path, capsys) -> None:
    args = cli.build_parser().parse_args(
        ["--render", str(tmp_path / "no.json"), "--video", "v.mp4"]
    )

    code = cli.render_command(args, Settings(db_path=tmp_path / "base.db"))

    assert code == 1
    assert "no existe el análisis" in capsys.readouterr().err
