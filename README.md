# Editor de Clips Virales

Herramienta **local-first** que transcribe un video con Whisper y analiza el texto para
identificar los momentos con mayor potencial viral y generar clips de formato vertical con:

- **gancho** de menos de 10 palabras para los primeros 3 segundos,
- **subtítulos dinámicos** de 4–5 palabras por línea con palabras clave resaltadas,
- **título, descripción y hashtags** adaptados a TikTok/Reels o YouTube Shorts.

> Esta versión (0.5.0) transcribe, analiza y **renderiza** el clip final en MP4 vertical
> 1080×1920 con fondo desenfocado, zoom suave y subtítulos quemados. Todo se ejecuta en
> local con el FFmpeg del sistema.
>
> La interfaz usa **exclusivamente** el estilo **Kinetic Typography**: fondo negro,
> tipografía display Syne mayúscula, texto en JetBrains Mono y acento amarillo.
>
> El ejecutable de Windows es una **aplicación de escritorio nativa**: abre su propia
> ventana (Edge WebView2 embebido), **sin lanzar el navegador**.

## Estado del proyecto

| Fase | Estado |
|---|---|
| 0 — Descubrimiento | Cerrada |
| 1 — Arquitectura y contratos | Cerrada |
| 2 — Ingesta y validación | Cerrada |
| 3 — Motor de análisis y ganchos | Cerrada |
| 4 — Subtítulos y plataformas | Cerrada |
| 5 — Integración Ollama | Cerrada |
| 6 — SQLite + API | Cerrada |
| 7 — Frontend accesible | Cerrada |
| 8 — SSE y flags | Cerrada |
| 9 — Calidad y evaluación | Cerrada |
| 10 — Documentación y escritorio | Cerrada |
| 11 — Empaquetado ejecutable | Cerrada |
| 12 — Transcripción local con Whisper | Cerrada |
| 13 — Renderizado con FFmpeg | Cerrada |

La documentación de cada fase (planeación + cierre) vive en [`docs/fases/`](docs/fases/).

Versión actual: **0.5.0** (ver [CHANGELOG](CHANGELOG.md)).

## Stack

- **Backend:** Python 3.11+ / FastAPI / Pydantic.
- **Frontend:** HTML + CSS + módulos ES (sin build).
- **Datos:** SQLite en modo WAL.
- **Transcripción:** faster-whisper (CTranslate2) en CPU/GPU + FFmpeg.
- **Renderizado:** FFmpeg (`libx264`, `libass`, AAC) sobre el equipo local.
- **IA:** Ollama opcional (`llama3.2` por defecto) con fallback heurístico.
- **Tiempo real:** SSE.

## Requisitos

- Python 3.11 o superior.
- [FFmpeg](https://ffmpeg.org/) en `PATH` con `libx264` y `libass` (extrae audio y
  renderiza el clip final). Se recomienda FFmpeg 7 u 8.
- (Opcional) [Ollama](https://ollama.com/) con un modelo instalado, por ejemplo:
  `ollama pull llama3.2`.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements-dev.txt
copy .env.example .env           # Windows
# cp .env.example .env           # macOS/Linux
```

## Arranque del backend

```bash
uvicorn viralclip.api.app:create_app --factory --reload
```

Abre `http://127.0.0.1:8000` para la interfaz web y
`http://127.0.0.1:8000/docs` para Swagger UI. La base SQLite se crea en
`data/viralclip.db` salvo que definas `VIRALCLIP_DB_PATH`.

## Arranque rápido (escritorio)

La forma más simple de usar la app es el lanzador, que arranca la API y abre el navegador:

```bash
pip install -e .
viralclip
```

Sin instalar el paquete, usa los lanzadores incluidos:

```bat
:: Windows
run.bat
```

```bash
# macOS / Linux
./run.sh
```

Opciones:

```bash
viralclip --port 0          # puerto libre automático
viralclip --no-browser      # no abre el navegador
viralclip --db data/otra.db # otra base SQLite
viralclip --transcribe video.mp4 --model small --language es
viralclip --render analisis.json --clip clip_001 --video video.mp4
viralclip --version
```

La transcripción por línea de comandos guarda `video.transcript.json` junto al video (o en
la ruta indicada con `--output`) y no arranca el servidor.

El render por línea de comandos toma un análisis JSON y un video, y escribe el MP4 y su
miniatura en `%LOCALAPPDATA%\ViralClip\renders` (o en `--render-output`).

## Ejecutable para Windows

> **Clonar el repo:** el bundle usa **git-lfs** (`.dll`, `.exe`, `.pyd`). Ejecuta
> `git lfs install` antes de clonar; sin los binarios reales, el ejecutable
> clonado no arranca.

### Descarga directa (versión 0.5.0)

**[`ViralClip-0.5.0-win64.zip` (102 MB)](https://github.com/thcano/Editor-de-Clips-Virales/releases/download/v0.5.0/ViralClip-0.5.0-win64.zip)**

Descomprime el ZIP **completo** y ejecuta `ViralClip.exe`. La carpeta `_internal/` es
necesaria: sin ella la app no arranca. No requiere Python instalado.

Notas de la release: [v0.5.0](https://github.com/thcano/Editor-de-Clips-Virales/releases/tag/v0.5.0).

> **Aplicación de escritorio, no un sitio web.** Desde la 0.5.0 el ejecutable abre
> **su propia ventana** de Windows (con icono y barra de título) y **no abre el
> navegador**. La ventana usa Edge WebView2, que ya viene instalado en Windows 11 y
> en las actualizaciones recientes de Windows 10. Al cerrarla se detiene todo: no
> queda ningún proceso en segundo plano.

> **¿Sigues viendo el diseño anterior?** La 0.4.1 corrigió la caché del navegador que
> mantenía el estilo previo en pantalla; la 0.5.0 lo resuelve de raíz con la URL
> versionada y las cabeceras `Clear-Site-Data`. Si aún persiste, pulsa `Ctrl+F5`.
> Detalle en el
> [manual de usuario](docs/manual/manual-usuario.md#la-interfaz-se-ve-con-el-diseño-anterior).

### Generar el ejecutable desde el código

```bat
build.bat
```

Genera `dist\ViralClip\ViralClip.exe` (modo `onedir`, ventana propia e icono). La base
se guarda en `%LOCALAPPDATA%\ViralClip\viralclip.db` salvo que definas `VIRALCLIP_DB_PATH`.

Para depurar, genera una build **con consola** (el launcher redirige la salida al log
del usuario en el build normal):

```bat
set VIRALCLIP_CONSOLE=1
build.bat
```

| Artefacto | Tamaño |
|---|---|
| `ViralClip.exe` | 14,63 MB |
| Carpeta `dist\ViralClip` completa | 254,3 MB (232 archivos) |
| `ViralClip-0.5.0-win64.zip` | 102 MB |

> El ZIP se publica como **GitHub Release**, no dentro del repo: GitHub rechaza ficheros
> de más de 100 MB en un push.

Consulta la [guía de empaquetado](docs/manual/empaquetado.md) para requisitos, uso,
antivirus y limitaciones.

## Documentación

| Documento | Para quién |
|---|---|
| [Manual de usuario](docs/manual/manual-usuario.md) | Quien usa la app: flujo paso a paso, renderizado, ajustes y solución de problemas |
| [Manual técnico](docs/manual/manual-tecnico.md) | Desarrollo: arquitectura, módulos, API, configuración, persistencia y diagnóstico |
| [Manual de despliegue](docs/manual/despliegue.md) | Instalación y distribución: portable, `pip` y servidor local |
| [Manual de empaquetado](docs/manual/empaquetado.md) | Generación del ejecutable con PyInstaller |
| [OpenAPI](docs/openapi.yaml) | Contrato de la API (`/docs` en la app) |
| [Ejemplos de API](docs/api/ejemplos.md) | Peticiones y respuestas de ejemplo |
| [ADRs](docs/adr/) | Decisiones de arquitectura y su justificación |
| [Fases](docs/fases/) | Planificación y cierre de cada fase del proyecto |

## Configuración

Copia `.env.example` a `.env` y ajusta lo necesario. El lanzador y la API cargan `.env`
automáticamente; las variables ya definidas en el entorno tienen prioridad.

| Variable | Defecto | Descripción |
|---|---|---|
| `VIRALCLIP_ENV` | `development` | Entorno lógico |
| `VIRALCLIP_HOST` | `127.0.0.1` | Host de escucha |
| `VIRALCLIP_PORT` | `8000` | Puerto |
| `VIRALCLIP_DB_PATH` | `data/viralclip.db` | Ruta de SQLite |
| `VIRALCLIP_API_KEY` | vacío | Si se define, protege `/api/*` con `X-API-Key` |
| `VIRALCLIP_CORS_ORIGINS` | localhost | Orígenes CORS separados por comas |
| `VIRALCLIP_MAX_INPUT_BYTES` | `2000000` | Tamaño máximo de entrada |
| `VIRALCLIP_MAX_CLIPS` | `8` | Clips máximos por análisis |
| `VIRALCLIP_MAX_SEGMENTS` | `20000` | Segmentos máximos |
| `VIRALCLIP_WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3` |
| `VIRALCLIP_WHISPER_DEVICE` | `auto` | `auto`, `cpu`, `cuda` |
| `VIRALCLIP_WHISPER_COMPUTE_TYPE` | `auto` | `int8` en CPU, `float16` en GPU |
| `VIRALCLIP_WHISPER_LANGUAGE` | `auto` | Idioma forzado o detección automática |
| `VIRALCLIP_WHISPER_MODEL_DIR` | `%LOCALAPPDATA%\ViralClip\models` | Caché de modelos |
| `VIRALCLIP_WHISPER_BEAM_SIZE` | `5` | Beam size de Whisper |
| `VIRALCLIP_WHISPER_VAD` | `true` | Filtro de voz (VAD) |
| `VIRALCLIP_UPLOAD_DIR` | `%LOCALAPPDATA%\ViralClip\uploads` | Videos subidos |
| `VIRALCLIP_UPLOAD_MAX_BYTES` | `2000000000` | Límite de subida (2 GB) |
| `VIRALCLIP_FFMPEG` | `ffmpeg` | Binario o ruta de FFmpeg |
| `VIRALCLIP_FFPROBE` | `ffprobe` | Binario o ruta de ffprobe |
| `VIRALCLIP_RENDER_DIR` | `%LOCALAPPDATA%\ViralClip\renders` | Carpeta de MP4 y miniaturas |
| `VIRALCLIP_RENDER_WIDTH` | `1080` | Ancho de salida |
| `VIRALCLIP_RENDER_HEIGHT` | `1920` | Alto de salida |
| `VIRALCLIP_RENDER_FPS` | `30` | Fotogramas por segundo |
| `VIRALCLIP_RENDER_CRF` | `20` | Calidad H.264 (menor = mejor) |
| `VIRALCLIP_RENDER_PRESET` | `veryfast` | Preset de `libx264` |
| `VIRALCLIP_RENDER_ZOOM` | `0.06` | Zoom final (0 = sin zoom) |
| `VIRALCLIP_RENDER_FONT` | `Arial` | Fuente de los subtítulos |
| `VIRALCLIP_RENDER_FONT_SIZE` | `54` | Tamaño de fuente en píxeles |
| `VIRALCLIP_RENDER_TIMEOUT` | `1800` | Segundos máximos por clip |
| `VIRALCLIP_LLM_ENABLED` | `true` | Activa Ollama |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Endpoint de Ollama |
| `OLLAMA_MODEL` | `llama3.2:latest` | Modelo |
| `VIRALCLIP_OLLAMA_TIMEOUT` | `60` | Timeout de generación (s) |
| `VIRALCLIP_OLLAMA_HEALTH_TIMEOUT` | `2` | Timeout de healthcheck (s) |
| `VIRALCLIP_OLLAMA_CIRCUIT_FAILURES` | `3` | Fallos antes de abrir el circuito |
| `VIRALCLIP_OLLAMA_CIRCUIT_COOLDOWN` | `60` | Enfriamiento del circuito (s) |
| `VIRALCLIP_LOG_LEVEL` | `INFO` | Nivel de log |

## Calidad y pruebas

```bash
# Suite completa + cobertura
.venv\Scripts\python.exe -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q

# Lint y sintaxis del frontend
.venv\Scripts\python.exe -m ruff check src tests scripts
node --check src/viralclip/web/app.js

# E2E reales con Playwright + Chromium
.venv\Scripts\python.exe -m pytest -o addopts="" tests/e2e -q

# Carga local con umbrales p95 y tasa de error
.venv\Scripts\python.exe scripts\load_test.py

# Evaluación determinista del set de oro (sin Ollama)
.venv\Scripts\python.exe scripts\evaluate_hooks.py

# Evaluación con juez Ollama y persistencia en SQLite (opcional)
.venv\Scripts\python.exe scripts\evaluate_hooks.py --judge --persist
```

Las pruebas E2E se omiten automáticamente si Playwright o Chromium no están instalados.
El juez LLM es opcional: las métricas deterministas son la fuente de verdad.

## Documentación

- [Manual de usuario](docs/manual/manual-usuario.md)
- [Guía de empaquetado](docs/manual/empaquetado.md)
- [Ejemplos de API](docs/api/ejemplos.md)
- [Changelog](CHANGELOG.md)
- [Índice de fases](docs/fases/README.md)
- [Fase 6 — Persistencia SQLite + API FastAPI](docs/fases/fase-06-persistencia-api.md)
- [Fase 7 — Frontend accesible y responsive](docs/fases/fase-07-frontend.md)
- [Fase 8 — SSE, feature flags e integraciones](docs/fases/fase-08-sse-flags.md)
- [Fase 9 — Calidad: E2E, carga, accesibilidad, evaluación IA](docs/fases/fase-09-calidad.md)
- [Fase 10 — Documentación final, manual y escritorio](docs/fases/fase-10-documentacion-escritorio.md)
- [Fase 11 — Empaquetado ejecutable para Windows](docs/fases/fase-11-empaquetado.md)
- [Fase 12 — Transcripción local con Whisper](docs/fases/fase-12-transcripcion.md)
- [Fase 13 — Renderizado con FFmpeg](docs/fases/fase-13-renderizado.md)
- [Set de oro para evaluación de ganchos](docs/evaluacion/casos-oro.json)
- [ADRs](docs/adr/)
- [Contrato de entrada](docs/contratos/transcripcion.schema.json)
- [Contrato de salida](docs/contratos/salida.schema.json)
- [OpenAPI](docs/openapi.yaml)

## Principios

1. Núcleo de dominio independiente de HTTP y SQLite.
2. Ollama opcional: la app funciona sin IA generativa.
3. Local-first: sin telemetría ni nube por defecto.
4. Contratos validados y versionados.
5. Accesibilidad WCAG 2.2 AA desde el diseño.

## Licencia

MIT.
