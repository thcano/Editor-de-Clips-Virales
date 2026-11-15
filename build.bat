@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No se encontro el entorno virtual .venv.
  echo Crea el entorno con:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
  exit /b 1
)

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

echo Instalando dependencias de build...
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt --quiet
if errorlevel 1 exit /b 1

echo Generando icono...
".venv\Scripts\python.exe" packaging\make_icon.py
if errorlevel 1 exit /b 1

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Empaquetando con PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean packaging\viralclip.spec
if errorlevel 1 exit /b 1

echo.
echo Ejecutable: %CD%\dist\ViralClip\ViralClip.exe
