# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para el ejecutable de Windows (onedir, consola)."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

PACKAGING = Path(SPECPATH).resolve()
ROOT = PACKAGING.parent
SRC = ROOT / "src"
ICON = PACKAGING / "viralclip.ico"

hiddenimports = [
    "anyio._backends._asyncio",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

if sys.platform != "win32":
    hiddenimports.append("uvicorn.loops.uvloop")

datas = [(str(SRC / "viralclip" / "web"), "viralclip/web")]
binaries = []

# faster-whisper necesita su modelo VAD (assets) y CTranslate2 sus DLLs nativas.
# PyAV, ONNX Runtime y tokenizers ya los cubren sus hooks de PyInstaller; no se
# usa collect_all porque arrastra herramientas CLI y convertidores innecesarios.
datas += collect_data_files("faster_whisper")
binaries += collect_dynamic_libs("ctranslate2")
hiddenimports += ["ctranslate2._ext"]

a = Analysis(
    [str(PACKAGING / "launcher.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "playwright",
        "axe_playwright_python",
        "ruff",
        "PIL",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ViralClip",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ViralClip",
)
