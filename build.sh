#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "No se encontro el entorno virtual .venv."
  echo "Crea el entorno con:"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/python -m pip install -r requirements-dev.txt"
  exit 1
fi

export PYTHONPATH="src:${PYTHONPATH:-}"

echo "Instalando dependencias de build..."
.venv/bin/python -m pip install -r requirements-build.txt --quiet

echo "Generando icono..."
.venv/bin/python packaging/make_icon.py

rm -rf build dist

echo "Empaquetando con PyInstaller..."
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/viralclip.spec

echo
echo "Ejecutable: $(pwd)/dist/ViralClip/ViralClip"
