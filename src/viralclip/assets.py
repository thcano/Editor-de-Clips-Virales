"""Gestión de los assets del frontend: versionado y política de caché.

El frontend es estático (sin build step), pero eso no significa que sea
inmutable: cada vez que cambia ``styles.css`` el navegador debe recibir la
versión nueva. Sin prendre cuidado, el navegador puede quedarse durante días
con la copia anterior guardada, porque:

- ``StaticFiles`` de Starlette no envía ``Cache-Control``, de modo que el
  navegador fija la vigencia con la *caché heurística* (10 % de la antigüedad
  del fichero) y puede devolver una copia antigua **sin preguntar al servidor**;
- la app se sirve siempre desde ``127.0.0.1``, así que el ejecutable y el clon
  del repositorio comparten origen y URL: una copia obsoleta se queda pegada en
  ambos.

Este módulo centraliza la solución:

- :class:`AssetVersion` calcula un hash corto del contenido de los assets, que
  se usa como *cache busting* en las URLs (``styles.css?v=abc123``);
- el lanzador abre el navegador en una URL versionada, de modo que la propia
  página de entrada nunca se resuelve desde una caché obsoleta;
- la respuesta de ``/`` pide al navegador vaciar su caché cuando la versión de
  los assets ha cambiado.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Carpeta con el frontend estático.
WEB_DIR = Path(__file__).resolve().parent / "web"

#: Documento principal de la interfaz.
INDEX_HTML = WEB_DIR / "index.html"

#: Cookie que recuerda la versión de los assets ya servida al navegador.
ASSET_VERSION_COOKIE = "viralclip_assets"

#: Cabecera que invalida la caché HTTP del origen en el navegador.
CLEAR_CACHE_HEADER = "Clear-Site-Data"

#: Assets del frontend cuya URL incluye la versión para evitar cachés viejas.
VERSIONED_ASSETS = ("styles.css", "app.js", "favicon.svg")


class AssetVersion:
    """Versión corta (hash del contenido) del conjunto de assets del frontend.

    Al incluirla en la URL de ``styles.css``, ``app.js`` y ``favicon.svg``,
    cualquier cambio de contenido produce una URL nueva, de modo que el
    navegador no puede reutilizar una copia anterior.
    """

    def __init__(self, web_dir: Path | None = None) -> None:
        self._web_dir = web_dir or WEB_DIR
        self._stamp: tuple[tuple[str, int, int], ...] = ()
        self._value = ""

    def _files(self) -> list[Path]:
        files = [self._web_dir / name for name in VERSIONED_ASSETS]
        fonts = self._web_dir / "fonts"
        if fonts.is_dir():
            files.extend(sorted(p for p in fonts.iterdir() if p.is_file()))
        return [f for f in files if f.is_file()]

    def get(self) -> str:
        """Devuelve el hash corto del contenido de los assets."""

        files = self._files()
        stamp = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in files)
        if stamp != self._stamp:
            digest = hashlib.sha256()
            for path in files:
                digest.update(path.read_bytes())
            self._value = digest.hexdigest()[:10]
            self._stamp = stamp
        return self._value


def versioned_url(path: str, version: str) -> str:
    """Añade la versión del frontend a la URL de un asset."""

    separator = "&" if "?" in path else "?"
    return f"{path}{separator}v={version}"
