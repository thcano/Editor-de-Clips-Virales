from __future__ import annotations

from pathlib import Path

from viralclip.desktop import DB_ENV, default_data_dir, prepare_environment


def test_prepare_environment_does_nothing_when_not_frozen() -> None:
    environ: dict[str, str] = {}

    assert prepare_environment(environ, frozen=False, platform="win32") is None
    assert DB_ENV not in environ


def test_prepare_environment_respects_existing_path(tmp_path) -> None:
    environ = {DB_ENV: str(tmp_path / "custom.db")}

    assert prepare_environment(environ, frozen=True, platform="win32") is None
    assert environ[DB_ENV] == str(tmp_path / "custom.db")


def test_prepare_environment_uses_localappdata_on_windows(tmp_path) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}

    result = prepare_environment(environ, frozen=True, platform="win32")

    expected = tmp_path / "ViralClip" / "viralclip.db"
    assert result == str(expected)
    assert environ[DB_ENV] == str(expected)
    assert expected.parent.is_dir()


def test_prepare_environment_falls_back_without_localappdata(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    environ: dict[str, str] = {}

    result = prepare_environment(environ, frozen=True, platform="win32")

    expected = tmp_path / "AppData" / "Local" / "ViralClip" / "viralclip.db"
    assert result == str(expected)
    assert expected.parent.is_dir()


def test_prepare_environment_macos(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    environ: dict[str, str] = {}

    result = prepare_environment(environ, frozen=True, platform="darwin")

    expected = tmp_path / "Library" / "Application Support" / "ViralClip" / "viralclip.db"
    assert result == str(expected)


def test_prepare_environment_linux_uses_xdg(tmp_path) -> None:
    environ = {"XDG_DATA_HOME": str(tmp_path / "share")}

    result = prepare_environment(environ, frozen=True, platform="linux")

    expected = tmp_path / "share" / "ViralClip" / "viralclip.db"
    assert result == str(expected)


def test_default_data_dir_without_xdg(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert default_data_dir({}, "linux") == tmp_path / ".local" / "share" / "ViralClip"
