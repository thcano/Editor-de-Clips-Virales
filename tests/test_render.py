"""Pruebas del módulo de renderizado con FFmpeg."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from viralclip import render
from viralclip.errors import (
    InvalidSourceError,
    RenderFailedError,
    RenderToolUnavailableError,
)
from viralclip.models import Clip, SubtitleLine, SubtitleWord


def make_clip() -> Clip:
    words = [
        SubtitleWord(word="Nadie", start=0.0, end=0.4, highlight=True),
        SubtitleWord(word="te", start=0.4, end=0.6),
        SubtitleWord(word="cuenta", start=0.6, end=1.0, highlight=True),
    ]
    line = SubtitleLine(
        index=1, start=0.0, end=1.0, text="Nadie te cuenta", words=words
    )
    return Clip(
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
        subtitles=[line],
    )


def test_ass_timestamp_formats_centiseconds() -> None:
    assert render._ass_timestamp(0) == "0:00:00.00"
    assert render._ass_timestamp(65.5) == "0:01:05.50"
    assert render._ass_timestamp(3661.99) == "1:01:01.99"
    assert render._ass_timestamp(-3) == "0:00:00.00"


def test_ass_escapes_special_characters() -> None:
    assert render._escape_ass_text("a{b}c\\d\ne") == "a(b)c/d e"


def test_build_ass_subtitles_includes_style_and_highlight() -> None:
    content = render.build_ass_subtitles(
        make_clip(), width=1080, height=1920, font="Arial", font_size=54
    )

    assert "[Script Info]" in content
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "Style: Default,Arial,54" in content
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Default" in content
    assert render.ASS_YELLOW in content
    assert "Nadie" in content


def test_build_ass_subtitles_skips_empty_and_out_of_range() -> None:
    clip = make_clip()
    clip.subtitles[0] = SubtitleLine(
        index=1, start=20.0, end=22.0, text="Fuera", words=[]
    )
    content = render.build_ass_subtitles(clip, width=1080, height=1920)
    assert "Dialogue:" not in content


def test_build_ass_subtitles_clamps_end_to_clip() -> None:
    clip = make_clip()
    clip.subtitles[0] = SubtitleLine(
        index=1, start=9.5, end=15.0, text="Final", words=[]
    )
    content = render.build_ass_subtitles(clip, width=1080, height=1920)
    assert "Dialogue: 0,0:00:09.50,0:00:10.00" in content


def test_build_filter_graph_has_background_foreground_and_ass() -> None:
    graph = render.build_filter_graph(
        width=1080,
        height=1920,
        zoom=0.06,
        clip_duration=10.0,
        subtitles_name="subtitles.ass",
    )

    assert "split=2[bg][fg]" in graph
    assert "boxblur=20:2" in graph
    assert "force_original_aspect_ratio=decrease" in graph
    assert "eval=frame" in graph
    assert "overlay=(W-w)/2:(H-h)/2" in graph
    assert "ass=subtitles.ass" in graph
    assert graph.endswith("format=yuv420p[vout]")


def test_build_filter_graph_without_zoom_or_subtitles() -> None:
    graph = render.build_filter_graph(
        width=720,
        height=1280,
        zoom=0.0,
        clip_duration=10.0,
        subtitles_name=None,
    )
    assert "eval=frame" not in graph
    assert "ass=" not in graph


def test_parse_progress_line() -> None:
    assert render._parse_progress_line("out_time_us=5000000") == 5.0
    assert render._parse_progress_line("out_time_ms=2500000") == 2.5
    assert render._parse_progress_line("out_time=00:00:03.500000") == 3.5
    assert render._parse_progress_line("frame=42") is None
    assert render._parse_progress_line("out_time_us=") is None
    assert render._parse_progress_line("out_time_us=abc") is None
    assert render._parse_progress_line("out_time=bad") is None


def test_validate_source_accepts_existing_video(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"datos")
    assert render.validate_source(video) == video.resolve()


def test_validate_source_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(InvalidSourceError):
        render.validate_source(tmp_path / "no.mp4")


def test_validate_source_rejects_extension(tmp_path: Path) -> None:
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"datos")
    with pytest.raises(InvalidSourceError):
        render.validate_source(audio)


def test_validate_clip_range() -> None:
    info = render.VideoInfo(width=1920, height=1080, duration=10.0, has_audio=True)
    clip = make_clip()
    render.validate_clip(clip, info)

    clip.end_seconds = 20.0
    with pytest.raises(InvalidSourceError):
        render.validate_clip(clip, info)


def test_probe_video_parses_streams(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"datos")
    payload = {
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080, "duration": "12.5"},
            {"codec_type": "audio"},
        ],
        "format": {"duration": "12.5"},
    }
    completed = SimpleNamespace(returncode=0, stdout=__import__("json").dumps(payload), stderr="")
    monkeypatch.setattr(render.subprocess, "run", lambda *a, **k: completed)
    monkeypatch.setattr(render, "_resolve_tool", lambda *a, **k: "ffprobe")

    info = render.probe_video(video)

    assert info.width == 1920
    assert info.height == 1080
    assert info.duration == 12.5
    assert info.has_audio is True


def test_probe_video_without_audio(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"datos")
    payload = {
        "streams": [{"codec_type": "video", "width": 640, "height": 480}],
        "format": {"duration": "4.0"},
    }
    completed = SimpleNamespace(returncode=0, stdout=__import__("json").dumps(payload), stderr="")
    monkeypatch.setattr(render.subprocess, "run", lambda *a, **k: completed)
    monkeypatch.setattr(render, "_resolve_tool", lambda *a, **k: "ffprobe")

    assert render.probe_video(video).has_audio is False


def test_probe_video_rejects_non_video(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"datos")
    payload = {"streams": [{"codec_type": "audio"}], "format": {"duration": "4.0"}}
    completed = SimpleNamespace(returncode=0, stdout=__import__("json").dumps(payload), stderr="")
    monkeypatch.setattr(render.subprocess, "run", lambda *a, **k: completed)
    monkeypatch.setattr(render, "_resolve_tool", lambda *a, **k: "ffprobe")

    with pytest.raises(InvalidSourceError):
        render.probe_video(video)


def test_probe_video_ffprobe_error(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"datos")
    completed = SimpleNamespace(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(render.subprocess, "run", lambda *a, **k: completed)
    monkeypatch.setattr(render, "_resolve_tool", lambda *a, **k: "ffprobe")

    with pytest.raises(InvalidSourceError):
        render.probe_video(video)


def test_resolve_tool_missing() -> None:
    with pytest.raises(RenderToolUnavailableError):
        render._resolve_tool("no-existe-jamas", label="ffmpeg")


def test_ffprobe_available(monkeypatch) -> None:
    monkeypatch.setattr(render, "_resolve_tool", lambda *a, **k: "ffprobe")
    assert render.ffprobe_available() is True

    def fail(*args, **kwargs):
        raise RenderToolUnavailableError("no")

    monkeypatch.setattr(render, "_resolve_tool", fail)
    assert render.ffprobe_available() is False


def test_build_ffmpeg_command_with_audio() -> None:
    from viralclip.config import Settings

    settings = Settings(render_dir=Path("renders"))
    command = render.build_ffmpeg_command(
        ffmpeg_binary="ffmpeg",
        source=Path("video.mp4"),
        output=Path("out.mp4"),
        clip=make_clip(),
        info=render.VideoInfo(width=1920, height=1080, duration=10.0, has_audio=True),
        settings=settings,
        subtitles_name="subtitles.ass",
    )

    assert "-filter_complex" in command
    assert "-map" in command
    assert "0:a:0?" in command
    assert "libx264" in command
    assert "aac" in command
    assert command[-1] == "out.mp4"


def test_build_ffmpeg_command_without_audio_adds_silence() -> None:
    from viralclip.config import Settings

    settings = Settings(render_dir=Path("renders"))
    command = render.build_ffmpeg_command(
        ffmpeg_binary="ffmpeg",
        source=Path("video.mp4"),
        output=Path("out.mp4"),
        clip=make_clip(),
        info=render.VideoInfo(width=1920, height=1080, duration=10.0, has_audio=False),
        settings=settings,
        subtitles_name=None,
    )

    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in command
    assert "1:a:0" in command
    assert "-shortest" in command


def test_run_ffmpeg_reports_progress(monkeypatch) -> None:
    class FakeStdout:
        def __init__(self) -> None:
            self.lines = iter(
                [
                    "out_time_us=1000000\n",
                    "out_time_us=5000000\n",
                    "frame=90\n",
                ]
            )

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.lines)

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeStdout()

        def wait(self) -> int:
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(
        render.subprocess, "Popen", lambda *a, **k: FakeProcess()
    )
    seen: list[tuple[int, str]] = []

    render._run_ffmpeg(
        ["ffmpeg"],
        duration=10.0,
        timeout=5,
        progress=lambda p, s: seen.append((p, s)),
    )

    assert seen[0][0] == 18
    assert seen[-1][0] == 50
    assert all(stage == "renderizando" for _, stage in seen)


def test_run_ffmpeg_failure(monkeypatch) -> None:
    class FakeStdout:
        def __iter__(self):
            return iter(["error de ffmpeg\n"])

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeStdout()

        def wait(self) -> int:
            return 1

        def poll(self):
            return 1

    monkeypatch.setattr(
        render.subprocess, "Popen", lambda *a, **k: FakeProcess()
    )

    with pytest.raises(RenderFailedError):
        render._run_ffmpeg(["ffmpeg"], duration=10.0, timeout=5, progress=None)


def test_extract_thumbnail_handles_failure(monkeypatch, tmp_path: Path) -> None:
    completed = SimpleNamespace(returncode=1, stderr="sin miniatura")
    monkeypatch.setattr(render.subprocess, "run", lambda *a, **k: completed)

    result = render._extract_thumbnail(
        "ffmpeg",
        output=tmp_path / "out.mp4",
        thumbnail=tmp_path / "out.jpg",
        duration=5.0,
        timeout=30,
    )

    assert result is None


def test_extract_thumbnail_success(monkeypatch, tmp_path: Path) -> None:
    thumbnail = tmp_path / "out.jpg"

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"jpg")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(render.subprocess, "run", fake_run)

    result = render._extract_thumbnail(
        "ffmpeg",
        output=tmp_path / "out.mp4",
        thumbnail=thumbnail,
        duration=5.0,
        timeout=30,
    )

    assert result == thumbnail
    assert thumbnail.is_file()


def test_run_ffmpeg_raises_when_popen_fails(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise OSError("no se pudo iniciar")

    monkeypatch.setattr(render.subprocess, "Popen", fail)

    with pytest.raises(RenderToolUnavailableError):
        render._run_ffmpeg(["ffmpeg"], duration=1.0, timeout=5, progress=None)


def test_ffmpeg_renderer_render(monkeypatch, tmp_path: Path) -> None:
    from viralclip.config import Settings

    settings = Settings(render_dir=tmp_path / "renders")
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    info = render.VideoInfo(width=1920, height=1080, duration=10.0, has_audio=True)
    monkeypatch.setattr(render, "_resolve_tool", lambda *a, **k: "ffmpeg")
    monkeypatch.setattr(render, "probe_video", lambda *a, **k: info)

    def fake_run(command, *, duration, timeout, progress, cwd=None):
        Path(command[-1]).write_bytes(b"mp4")
        if progress is not None:
            progress(50, "renderizando")

    def fake_thumbnail(binary, *, output, thumbnail, duration, timeout):
        thumbnail.write_bytes(b"jpg")
        return thumbnail

    monkeypatch.setattr(render, "_run_ffmpeg", fake_run)
    monkeypatch.setattr(render, "_extract_thumbnail", fake_thumbnail)
    stages: list[tuple[int, str]] = []

    result = render.FFmpegRenderer(settings).render(
        source_path=source,
        clip=make_clip(),
        render_id="r1",
        job_id="j1",
        progress=lambda p, s: stages.append((p, s)),
    )

    assert result.output_path.is_file()
    assert result.thumbnail_path is not None
    assert result.thumbnail_path.is_file()
    assert result.width == 1080
    assert result.height == 1920
    assert result.size_bytes == 3
    assert stages[0] == (2, "validando")
    assert stages[-1] == (100, "done")


def test_ffmpeg_renderer_render_without_subtitles(monkeypatch, tmp_path: Path) -> None:
    from viralclip.config import Settings

    settings = Settings(render_dir=tmp_path / "renders")
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    clip = make_clip()
    clip.subtitles = []
    info = render.VideoInfo(width=1920, height=1080, duration=10.0, has_audio=False)
    monkeypatch.setattr(render, "_resolve_tool", lambda *a, **k: "ffmpeg")
    monkeypatch.setattr(render, "probe_video", lambda *a, **k: info)

    def fake_run(command, *, duration, timeout, progress, cwd=None):
        Path(command[-1]).write_bytes(b"mp4")

    monkeypatch.setattr(render, "_run_ffmpeg", fake_run)
    monkeypatch.setattr(
        render, "_extract_thumbnail", lambda *a, **k: None
    )

    result = render.FFmpegRenderer(settings).render(
        source_path=source,
        clip=clip,
        render_id="r2",
        job_id="j2",
    )

    assert result.thumbnail_path is None
    assert result.output_path.is_file()


def test_ffmpeg_renderer_fails_without_output(monkeypatch, tmp_path: Path) -> None:
    from viralclip.config import Settings

    settings = Settings(render_dir=tmp_path / "renders")
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    info = render.VideoInfo(width=1920, height=1080, duration=10.0, has_audio=True)
    monkeypatch.setattr(render, "_resolve_tool", lambda *a, **k: "ffmpeg")
    monkeypatch.setattr(render, "probe_video", lambda *a, **k: info)
    monkeypatch.setattr(render, "_run_ffmpeg", lambda *a, **k: None)

    with pytest.raises(RenderFailedError):
        render.FFmpegRenderer(settings).render(
            source_path=source,
            clip=make_clip(),
            render_id="r3",
            job_id="j3",
        )
