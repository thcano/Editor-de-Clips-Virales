# Fase 11 — Empaquetado ejecutable para Windows

> **Proyecto:** Editor de Clips Virales
> **Fase:** 11 (ciclo de evolución posterior a la entrega 0.1.0)
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Entradas:** lanzador `viralclip` (Fase 10), assets web, `pyproject.toml`

---

## 1. Resumen ejecutivo

La entrega 0.1.0 requiere Python instalado. Este ciclo añade un **ejecutable de Windows**
generado con **PyInstaller en modo `onedir`**, con consola visible e icono propio. El
ejecutable conserva el comportamiento del lanzador: arranca la API, elige puerto libre,
abre el navegador y se detiene con `Ctrl+C`.

El empaquetado **no incluye Ollama** (sigue siendo un servicio externo opcional) ni las
dependencias de desarrollo (Playwright, pytest, axe). La base de datos se guarda, por
defecto, en `%LOCALAPPDATA%\ViralClip\viralclip.db` cuando la app corre empaquetada, para
evitar escribir dentro de `Program Files` o de la carpeta de instalación.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Producir y verificar un ejecutable `ViralClip.exe` reproducible, documentado y con paridad
funcional con el lanzador Python:

- arranque sin Python instalado;
- assets web incluidos;
- base de datos en una ruta escribible;
- cierre ordenado;
- build reproducible con un comando.

### 2.2 Alcance

#### Incluye

- `packaging/launcher.py` (punto de entrada del ejecutable).
- `packaging/make_icon.py` (genera `packaging/viralclip.ico` con Pillow).
- `packaging/viralclip.spec` (PyInstaller `onedir`, consola, icono).
- `build.bat` y `build.sh` (build reproducible).
- `requirements-build.txt` y extra `build` en `pyproject.toml`.
- `src/viralclip/desktop.py` con la resolución de la ruta de datos cuando está empaquetado.
- `tests/test_desktop.py`.
- `docs/manual/empaquetado.md`.
- Actualización de README, CHANGELOG, versión y índices.
- Smoke real del `.exe`.

#### No incluye

- Instalador MSI/NSIS.
- Firma de código ni reputación de antivirus.
- Auto-update.
- Builds para macOS/Linux (PyInstaller no compila cruzado).
- Incluir Ollama o modelos dentro del ejecutable.
- Icono de bandeja o cierre sin consola.

### 2.3 Decisiones aprobadas por el usuario (2026-11-09)

| Decisión | Opción elegida | Consecuencia |
|---|---|---|
| Modo PyInstaller | **`onedir`** | `dist/ViralClip/` con `.exe` y dependencias; arranque rápido |
| Consola | **Mantener** | Se ven logs y URL; `Ctrl+C` cierra |
| Icono | **Sí, generado** | Pillow como dependencia de build; `.ico` reproducible |

### 2.4 Ruta de datos en modo empaquetado

Regla:

1. Si `VIRALCLIP_DB_PATH` está definida, se respeta.
2. Si la app está congelada (`sys.frozen`) y no hay variable, se usa
   `%LOCALAPPDATA%\ViralClip\viralclip.db` (o `~/.local/share/ViralClip/viralclip.db`
   fuera de Windows).
3. Si no está congelada, se mantiene `data/viralclip.db` para no cambiar el flujo de
   desarrollo ni las pruebas.

La lógica vive en `viralclip.desktop.prepare_environment()` y se prueba como función pura.

### 2.5 Contenido del ejecutable

- Código Python y dependencias de `requirements.txt`.
- `src/viralclip/web/*` como datos (`viralclip/web`).
- Módulos dinámicos de uvicorn (`loops`, `protocols`, `lifespan`, `logging`).
- Icono `packaging/viralclip.ico`.

No se incluyen:

- `tests/`, `scripts/`, `docs/`, `.venv/`.
- Playwright, axe, pytest, ruff, Pillow.
- Modelos de Ollama.

### 2.6 Build reproducible

```bat
:: Windows
build.bat
```

```bash
# macOS/Linux (solo genera el binario de esa plataforma)
./build.sh
```

El script:

1. valida `.venv`;
2. instala `requirements-build.txt` si faltan PyInstaller/Pillow;
3. genera el icono;
4. limpia `build/` y `dist/`;
5. ejecuta PyInstaller con `packaging/viralclip.spec`;
6. imprime la ruta del ejecutable.

### 2.7 Actividades

1. Documentar esta planeación.
2. Implementar `desktop.py` y sus pruebas.
3. Crear el icono y el spec.
4. Crear los scripts de build y dependencias.
5. Construir el ejecutable.
6. Ejecutar smoke del `.exe` (`--version`, `/`, `/api/health`).
7. Documentar el empaquetado y actualizar README/CHANGELOG/versión.
8. Cerrar la fase con evidencia y deuda.

### 2.8 Criterios de aceptación

- [x] `build.bat` genera `dist/ViralClip/ViralClip.exe`.
- [x] El `.exe` responde `--version`.
- [x] El `.exe` sirve `/` con los assets web.
- [x] El `.exe` responde `/api/health` con `200`.
- [x] La base se crea en `%LOCALAPPDATA%\ViralClip` si no hay variable.
- [x] `VIRALCLIP_DB_PATH` tiene prioridad.
- [x] El cierre ordenado funciona con `should_exit`/`Ctrl+C`.
- [x] No se incluyen dependencias de desarrollo en el bundle.
- [x] `pytest`, `ruff` y `node --check` pasan.
- [x] La documentación de build es reproducible.

### 2.9 Riesgos

| Riesgo | Mitigación |
|---|---|
| PyInstaller no encuentra uvicorn/pydantic | `hiddenimports` explícitos y smoke real |
| Assets web fuera del bundle | `datas` a `viralclip/web` y verificación de `/` |
| Base en ruta no escribible | `%LOCALAPPDATA%` cuando está congelado |
| Antivirus marca el `.exe` | `onedir`, build local y documentar el falso positivo |
| Tamaño del bundle | Excluir tests, docs y dev tools; documentar el tamaño |
| Build no reproducible | Spec versionado y scripts con `--clean` |
| Icono no generado | `make_icon.py` con Pillow y fallback sin icono |

### 2.10 Evidencia esperada

- `dist/ViralClip/ViralClip.exe` y su carpeta.
- Smoke con `--version`, `/` y `/api/health`.
- `tests/test_desktop.py` en verde.
- Documento de empaquetado y CHANGELOG actualizado.

---

## 3. Cierre de fase

### 3.1 Resultado

El ciclo de empaquetado entrega un ejecutable de Windows reproducible y con paridad funcional
con el lanzador:

- **`dist/ViralClip/ViralClip.exe`** generado con PyInstaller 6.22.3 en modo `onedir`,
  consola visible e icono propio.
- **Punto de entrada** `packaging/launcher.py`: configura UTF-8, prepara la ruta de datos y
  delega en `viralclip.cli.main()`.
- **Ruta de datos congelada:** `%LOCALAPPDATA%\ViralClip\viralclip.db` cuando corre
  empaquetado y no hay `VIRALCLIP_DB_PATH`; `--db` y la variable de entorno tienen
  prioridad.
- **Icono reproducible** `packaging/viralclip.ico` generado con Pillow.
- **Build en un comando** (`build.bat` / `build.sh`) con instalación de dependencias,
  generación de icono, limpieza y PyInstaller.
- **Versión 0.2.0** en `pyproject.toml`, `__init__.py`, manual y CHANGELOG.
- **Documentación** `docs/manual/empaquetado.md` con requisitos, uso, rutas, antivirus,
  verificación y deuda.
- **Bug real corregido:** `SPECPATH` se interpretaba como carpeta del spec y la raíz del
  proyecto se resolvía un nivel arriba; ahora se usa `PACKAGING = Path(SPECPATH).resolve()`
  y `ROOT = PACKAGING.parent`.

### 3.2 Evidencia

Código y empaquetado:

- `src/viralclip/desktop.py` (`default_data_dir`, `prepare_environment`)
- `packaging/launcher.py`, `packaging/make_icon.py`, `packaging/viralclip.spec`
- `packaging/viralclip.ico` (11 246 bytes)
- `requirements-build.txt`, `build.bat`, `build.sh`
- `pyproject.toml` (versión `0.2.0`, extra `build`)

Pruebas:

- `tests/test_desktop.py`: 7 pruebas (no congelado, ruta explícita, Windows con y sin
  `LOCALAPPDATA`, macOS, Linux con XDG y fallback sin XDG).

Comandos y resultados:

```text
$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
TOTAL  2176 stmts  160 miss  616 branch  103 partial  90% cover
263 passed, 1 warning

$ python -m ruff check src tests scripts
All checks passed!

$ node --check src/viralclip/web/app.js
(sin errores de sintaxis)

$ cmd /c "build.bat"
PyInstaller: 6.22.3 · Python 3.14.7 · Windows-11-10.0.26300-SP0
Ejecutable: ...\dist\ViralClip\ViralClip.exe
```

Smoke real del ejecutable:

```text
$ ViralClip.exe --version
viralclip 0.2.0

$ ViralClip.exe --no-browser --port 0 --db <tmp>\explicit.db
root: 200 True
app.js: 200 True
health: 200 ok
config: 200 ['tiktok', 'reels', 'shorts']
db explicita: True

$ ViralClip.exe --no-browser --port 0   (LOCALAPPDATA redirigido)
health frozen: 200 ok
db frozen: True <tmp>\ViralClip\viralclip.db
```

Tamaño del bundle:

| Elemento | Valor |
|---|---|
| `ViralClip.exe` | 10 129 208 bytes (~9,7 MB) |
| Carpeta `dist/ViralClip` | 38 183 109 bytes (~36 MB) |
| Archivos | 65 |

### 3.3 Criterios de aceptación

- [x] `build.bat` genera `dist/ViralClip/ViralClip.exe`.
- [x] El `.exe` responde `--version`.
- [x] El `.exe` sirve `/` con los assets web.
- [x] El `.exe` responde `/api/health` con `200`.
- [x] La base se crea en `%LOCALAPPDATA%\ViralClip` si no hay variable.
- [x] `VIRALCLIP_DB_PATH` tiene prioridad.
- [x] El cierre ordenado funciona con `should_exit`/`Ctrl+C`.
- [x] No se incluyen dependencias de desarrollo en el bundle.
- [x] `pytest`, `ruff` y `node --check` pasan.
- [x] La documentación de build es reproducible.

### 3.4 Deuda consciente

- Solo se validó el build de **Windows**; `build.sh` no se ejecutó en macOS/Linux.
- No hay instalador MSI/NSIS, firma de código ni auto-update.
- No hay icono de bandeja ni modo sin consola.
- `upx` está desactivado a propósito para reducir falsos positivos de antivirus.
- PyInstaller emite un aviso no bloqueante: `hidden import 'tzdata' not found`.
- El `.env` se busca en el directorio de trabajo del ejecutable; un acceso directo con
  otro directorio de trabajo no lo encontrará.
- El bundle pesa ~36 MB porque incluye todas las dependencias de FastAPI/uvicorn; no se
  hizo una poda fina de módulos.

### 3.5 Handoff al siguiente ciclo

El usuario solicitó ampliar el producto con un pipeline audiovisual completo:

1. **Transcripción local con Whisper** (audio del video → JSON con tiempos por palabra).
2. **Dirección con Ollama** (selección de momentos, hooks, subtítulos e instrucciones de
   zoom).
3. **Renderizado con FFmpeg** (corte, reencuadre 9:16, zoom dinámico, subtítulos `.ass` y
   miniatura).

Esto cambia el alcance original (que excluía renderizado) y requiere su propia planeación
por fases, decisiones de dependencias (Whisper, FFmpeg, GPU/CPU) y actualización de
`SKILLS.md`, ADRs y contratos.

### 3.6 Criterio de aprobación

El usuario aprueba este cierre y autoriza el inicio del ciclo de **transcripción y
renderizado**. Las decisiones de alcance, motor de Whisper, hardware y métodos de
reencuadre se confirmarán antes de escribir código.
