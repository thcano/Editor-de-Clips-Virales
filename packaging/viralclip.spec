# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para el ejecutable de Windows (onedir, ventana)."""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

PACKAGING = Path(SPECPATH).resolve()
ROOT = PACKAGING.parent
SRC = ROOT / "src"
ICON = PACKAGING / "viralclip.ico"

#: El ejecutable es una aplicación de ventana: `console=False` evita que
#: aparezca una consola de Windows detrás de la interfaz. Se puede forzar una
#: build de consola con `set VIRALCLIP_CONSOLE=1` antes de lanzar build.bat,
#: útil para depurar.
CONSOLE = os.environ.get("VIRALCLIP_CONSOLE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

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
    # pywebview: motor de la ventana de escritorio (WebView2 en Windows).
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "webview.http",
    "clr",
    "clr_loader",
    "pythonnet",
    "System",
    "System.Windows.Forms",
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

# pywebview necesita los ensamblados de interoperabilidad de WebView2 y los
# binarios nativos del runtime; sin ellos la ventana no arranca.
try:
    import webview as _webview

    _webview_dir = Path(_webview.__file__).resolve().parent
    for _dll in _webview_dir.glob("lib/*.dll"):
        datas.append((str(_dll), "webview/lib"))
    _runtimes = _webview_dir / "lib" / "runtimes"
    if _runtimes.is_dir():
        for _native in _runtimes.rglob("*"):
            if _native.is_file():
                _rel = _native.relative_to(_webview_dir / "lib")
                binaries.append((str(_native), str(_rel.parent)))
except Exception as exc:  # pragma: no cover - si falta pywebview se avisa luego
    print(f"Aviso: no se pudieron collects los assets de pywebview: {exc}")

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
    console=CONSOLE,
    disable_windowed_traceback=False,
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
