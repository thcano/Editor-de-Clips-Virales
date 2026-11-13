"""Utilidades para la ejecución empaquetada de escritorio."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, MutableMapping
from pathlib import Path

DB_ENV = "VIRALCLIP_DB_PATH"
APP_DIR_NAME = "ViralClip"


def default_data_dir(
    environ: Mapping[str, str],
    platform: str | None = None,
) -> Path:
    """Devuelve el directorio de datos por usuario para la app empaquetada."""

    platform = platform or sys.platform
    if platform == "win32":
        base = environ.get("LOCALAPPDATA") or environ.get("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / APP_DIR_NAME
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    xdg = environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def prepare_environment(
    environ: MutableMapping[str, str] | None = None,
    *,
    frozen: bool | None = None,
    platform: str | None = None,
) -> str | None:
    """Ajusta ``VIRALCLIP_DB_PATH`` cuando la app corre empaquetada.

    Devuelve la ruta usada o ``None`` si no se cambió nada. Respeta una ruta
    definida explícitamente por el usuario.
    """

    env = os.environ if environ is None else environ
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if platform is None:
        platform = sys.platform

    if not frozen or env.get(DB_ENV):
        return None

    data_dir = default_data_dir(env, platform)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "viralclip.db"
    env[DB_ENV] = str(db_path)
    return str(db_path)
