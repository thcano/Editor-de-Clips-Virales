# Manual técnico — Editor de Clips Virales

> Versión documentada: **0.5.0**
> Audiencia: equipo de desarrollo, revisores de código y mantenedores del proyecto.
> Documento de referencia para comprendre, modificar, construir y dar soporte al sistema.

---

## 1. Resumen de la arquitectura

El Editor de Clips Virales es una aplicación **local-first** de un solo usuario: transcribe
un video local con Whisper, analiza la transcripción para proponer clips candidatos con
gancho, subtítulos y hashtags, y renderiza el clip final con FFmpeg. Todo el procesamiento
ocurre en el equipo del usuario; no hay telemetría ni nube por defecto.

```text
┌─────────────────────────────────────────────────────────────────┐
│  Navegador (UI estática, sin build)                             │
│  index.html · styles.css (Kinetic Typography) · app.js         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/JSON + SSE
┌───────────────────────────▼─────────────────────────────────────┐
│  FastAPI + Uvicorn (127.0.0.1)                                  │
│  ┌──────────┬──────────────┬──────────────┬──────────────────┐  │
│  │  API     │  Pipeline    │  Storage     │  LLM (opcional)  │  │
│  │  HTTP    │  análisis    │  SQLite WAL  │  Ollama          │  │
│  └──────────┴──────┬───────┴──────┬───────┴──────────────────┘  │
│                    │              │                             │
│         ┌──────────▼───────┐  ┌───▼──────────┐                  │
│         │ Transcription    │  │  Render      │                  │
│         │ Whisper/FFmpeg   │  │  FFmpeg      │                  │
│         └──────────────────┘  └──────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

### Decisiones de diseño (ADR)

| ADR | Decisión |
|---|---|
| [ADR-001](../adr/ADR-001-python-fastapi.md) | Python 3.11+ con FastAPI + Pydantic v2 + Uvicorn |
| [ADR-002](../adr/ADR-002-frontend-web-sin-build.md) | Frontend web sin build: HTML/CSS/JS nativo servido como estáticos |
| [ADR-003](../adr/ADR-003-sqlite-local.md) | SQLite local en modo WAL |
| [ADR-004](../adr/ADR-004-ollama-opcional.md) | Ollama como refinado opcional, nunca bloqueante |
| [ADR-005](../adr/ADR-005-sse-progreso.md) | SSE para el progreso con fallback de polling |
| [ADR-006](../adr/ADR-006-contrato-salida.md) | Contrato JSON de salida versionado |
| [ADR-007](../adr/ADR-007-local-first.md) | Local-first: sin telemetría |
| [ADR-008](../adr/ADR-008-lanzador-escritorio.md) | Lanzador de escritorio (ventana nativa propia desde 0.5.0) |
| [ADR-009](../adr/ADR-009-transcripcion-local-whisper.md) | Transcripción local con faster-whisper |
| [ADR-010](../adr/ADR-010-renderizado-ffmpeg.md) | Renderizado con FFmpeg (`libx264` + `libass`) |

---

## 2. Estructura del repositorio

```text
Editor de Clips Virales/
├─ src/viralclip/              Paquete Python (código de producción)
│  ├─ __init__.py              Versión (__version__)
│  ├─ cli.py                   CLI: serve, --transcribe, --render
│  ├─ config.py                Settings desde variables de entorno
│  ├─ assets.py                Versionado y caché de los assets del frontend
│  ├─ desktop.py               Rutas de datos por usuario (paquete congelado)
│  ├─ desktop_window.py        Ventana de escritorio nativa (pywebview/WebView2)
│  ├─ analyzer.py              Núcleo de análisis: ganchos, score, razón
│  ├─ platform.py              Adaptadores por red social (TikTok/Reels/Shorts)
│  ├─ lexicon.py               Léxico de phrases y palabras clave
│  ├─ subtitles.py             Segmentación y marcado de subtítulos
│  ├─ transcript.py            Normalización de transcripciones
│  ├─ transcription.py         Orquestación de Whisper + FFmpeg
│  ├─ render.py                Renderizado del clip con FFmpeg
│  ├─ pipeline.py              Tubería análisis → clips
│  ├─ storage.py               Persistencia SQLite
│  ├─ models.py                Modelos Pydantic de dominio
│  ├─ evaluation.py            Métricas de evaluación
│  ├─ hooks.py                 Ganchos de extensibilidad
│  ├─ errors.py                Jerarquía de errores de dominio
│  ├─ api/                     Capa HTTP
│  │  ├─ app.py                Factoría de la app FastAPI y cabeceras
│  │  ├─ routes.py             Análisis, historial, configuración
│  │  ├─ transcriptions.py     Jobs de transcripción (SSE)
│  │  ├─ renders.py            Jobs de renderizado
│  │  └─ security.py           Cabeceras y validación de API key
│  ├─ llm/                     Integración opcional con Ollama
│  │  ├─ ollama.py             Cliente HTTP + circuit breaker
│  │  └─ prompts.py            Plantillas de prompt
│  └─ web/                     Frontend estático
│     ├─ index.html
│     ├─ styles.css            Kinetic Typography
│     ├─ app.js                Lógica de UI (módulo ES)
│     ├─ favicon.svg
│     └─ fonts/                Syne + JetBrains Mono (woff2, self-hosted)
├─ tests/                      Suite pytest
│  ├─ unitarios/               tests/test_*.py
│  ├─ e2e/                     Playwright + axe-core
│  └─ fixtures/                JSON de ejemplo
├─ docs/
│  ├─ adr/                     Decisiones de arquitectura
│  ├─ api/                     Ejemplos y OpenAPI
│  ├─ contratos/               Esquemas JSON
│  ├─ fases/                   Plan de fases del proyecto
│  ├─ evaluacion/              Casos de oro
│  └─ manual/                  Este manual, usuario, despliegue y empaquetado
├─ packaging/                  Spec de PyInstaller, launcher, generación de icono
├─ kinetic-typography/         Catálogo de estilos visuales (referencia)
├─ build.bat / build.sh        Scripts de empaquetado
└─ pyproject.toml              Metadatos, dependencias y configuración
```

---

## 3. Entorno de desarrollo

### Requisitos

- Windows 10/11 de 64 bits (validado también en macOS/Linux para desarrollo).
- Python **3.11 o superior** (desarrollo validado con 3.14).
- [FFmpeg](https://ffmpeg.org/) con `libx264` y `libass` en el `PATH`.
- (Opcional) [Ollama](https://ollama.com/) para el refinado de ganchos.

### Preparación

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
```

### Ejecución en desarrollo

```powershell
# API con recarga automática (recomendado al tocar código Python)
.venv\Scripts\python.exe -m uvicorn viralclip.api.app:create_app --factory --reload --port 8000
```

El frontend se monta en `/static` y se sirve desde `src/viralclip/web`. Al usar `--reload`,
los cambios en `styles.css`, `app.js` e `index.html` se reflejan al recargar; no hace falta
compilar nada.

> El frontend **no tiene build step** (ADR-002). No hay bundler, ni `npm`, ni transpilación.
> Esto es intencionado: reduce el mantenimiento y mantiene el proyecto legible.

### Calidad

```powershell
.venv\Scripts\python.exe -m pytest              # suite completa
.venv\Scripts\python.exe -m pytest --ignore=tests/e2e   # solo unitarios (rápido)
.venv\Scripts\python.exe -m ruff check src tests
```

| Comando | Qué hace |
|---|---|
| `pytest` | Ejecuta unitarios + e2e. Los e2e requieren los navegadores de Playwright: `playwright install chromium` |
| `pytest --ignore=tests/e2e` | Solo unitarios. No necesita navegador |
| `ruff check src tests` | Lint con reglas `E`, `F`, `I`, `B`, `UP` |

Cobertura configurada en `pyproject.toml` (`source = ["viralclip"]`, `branch = true`).

---

## 4. Capa web (frontend)

### Enfoque

Frontend **sin build** (ADR-002): tres archivos estáticos servidos por FastAPI con
`StaticFiles`. No hay framework, ni bundler, ni dependencias npm.

| Archivo | Responsabilidad |
|---|---|
| `index.html` | Estructura semántica, plantillas (`<template>`), iconos SVG |
| `styles.css` | Sistema de diseño Kinetic Typography |
| `app.js` | Módulo ES con toda la lógica de UI |

### Sistema de diseño: Kinetic Typography

El proyecto usa el estilo **Kinetic Typography** tomado de `kinetic-typography/`, cuyo
principio es que *la tipografía es la protagonista*: el texto se mueve y sustituye a la
imagen.

**Tokens** (`styles.css`, bloque `:root`):

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#0A0A0A` | Fondo de página |
| `--surface` | `#141414` | Paneles y tarjetas |
| `--surface-2` | `#1F1F1F` | Superficies anidadas |
| `--fg` | `#FFFFFF` | Texto principal |
| `--muted` | `#BDBDBD` | Texto secundario |
| `--accent` | `#FFE600` | Acento primario (botones, foco) |
| `--accent-2` | `#FF3D00` | Acento secundario (contornos, badges) |
| `--border` | `#333333` | Bordes |
| `--font-head` | `Syne` | Display, pesos 800, mayúsculas, tracking `-0.05em` |
| `--font-body` | `JetBrains Mono` | Texto de interfaz y datos |

**Animaciones cinéticas** implementadas:

| Animación | Elemento | Técnica |
|---|---|---|
| `kin-marquee` | `.marquee-track` | `translateX(0 → -50%)` sobre dos copias idénticas → bucle continuo |
| `kin-blink` | `.hero-technical` | `steps(1)` con opacidad 1 → 0.35 en el 89–92 % del ciclo |
| `kin-rotate` | `.hero-rotate` | `translateY` + `skewX` alternos (4,8 s) |
| `kin-underline` | `.hero-rotate::after` | `scaleX(0 → 1)` sincronizado con la rotación |
| `app-aurora` | `.app-bg::after` | Aurora de fondo con `blur(18px)` y `translate3d` |
| `app-blob` | `.hero-glow` | Forma orgánica con `border-radius` animado |
| `hero-in` | `.hero` | Entrada con `opacity` + `translateY` |

**Contorno de texto**: `.hero-title::after` usa `-webkit-text-stroke: 1px var(--accent)`
con `color: transparent` para repetir el nombre del estilo en contorno — el recurso
"superposición con contornos" descrito en `kinetic-typography/meta.json`.

### Accesibilidad

- `prefers-reduced-motion: reduce` desactiva **todas** las animaciones y transiciones.
- Contraste verificado con axe-core en la suite e2e (0 violaciones `critical`/`serious`).
- Enlace de salto (`skip-link`) como primer elemento enfocable.
- Todos los campos tienen `<label for>`; los estados dinámicos usan `role="status"` y
  `aria-live="polite"`.
- El diálogo de ajustes usa `<dialog>` nativo (`showModal`), con foco gestionado por el
  navegador y cierre con `Escape`.

### CSP y por qué las fuentes son locales

`api/app.py` sirve `/` con la cabecera:

```text
default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self';
connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
```

`font-src` no está declarado, por lo que hereda `default-src 'self'`: **no se puede
cargar una fuente desde un CDN**. Por eso `src/viralclip/web/fonts/` incluye Syne y
JetBrains Mono autoalojadas (woff2 variables, 66 KB en total). Consecuencia práctica: la
app funciona **sin red** y sin peticiones a terceros.

### Caché de los assets: por qué el diseño se quedaba obsoleto

Un frontend sin *build step* tiene una trampa: los ficheros de `web/` son el
"compilado" de la aplicación. Si el navegador los cachea, un cambio de diseño no
llega a verse hasta que la caché expira.

El problema tiene **dos causas independientes**, ambas resueltas en `api/app.py` y
`assets.py`:

| Causa | Comportamiento del navegador | Solución |
|---|---|---|
| `StaticFiles` de Starlette no envía `Cache-Control` | El navegador aplica **caché heurística** (10 % de la antigüedad del fichero) y puede devolver el `styles.css` antiguo **sin contactar con el servidor** | `Cache-Control: no-cache` + `Pragma` + `Expires: 0` en todos los assets |
| Starlette acepta `If-Modified-Since` | Responde `304` si la fecha cacheada es ≥ que el `Last-Modified` del fichero. Tras reinstalar o clonar el repo la fecha del fichero puede ser **anterior**, así que el servidor confirmaba como "no modificado" un CSS obsoleto | La revalidación solo se acepta por **`ETag`**, calculado sobre el **hash del contenido**; `If-Modified-Since` se ignora |

Como la app se sirve siempre desde `127.0.0.1`, el ejecutable y el clon del
repositorio comparten origen y URL: una copia obsoleta se quedaba pegada en ambos.

La solución completa añade tres capas (`src/viralclip/assets.py`):

1. **Versionado por hash.** `AssetVersion.get()` calcula un hash corto del
   contenido de `styles.css`, `app.js`, `favicon.svg` y las fuentes. Ese valor se
   añade a las URLs (`?v=c174d578e6`), de modo que cualquier cambio produce una
   URL **nueva** que el navegador no puede reutilizar.
2. **URL de entrada versionada.** El lanzador (`cli.py::serve_window`) abre la
   ventana de escritorio en `http://127.0.0.1:8000/?v=<hash>`. Es imprescindible:
   si la propia página de entrada está cacheada, el navegador no pide nada y nunca
   ve las URLs versionadas.
3. **Purga de la caché obsoleta.** La respuesta de `/` envía `Clear-Site-Data:
   "cache"` cuando la versión ha cambiado, controlado con la cookie
   `viralclip_assets`. Así desaparece cualquier copia del diseño anterior y la
   URL sin parámetro también funciona.

> **Consecuencia:** un `304` significa siempre "los bytes son idénticos". Si el
> navegador no puede compararlos por `ETag`, recibe el fichero completo (200)
> en lugar de un `304` engañoso.

Comprobación rápida tras tocar el CSS:

```powershell
curl -s -D - -o NUL http://127.0.0.1:8000/static/styles.css
# cache-control: no-cache
# etag: "17965603b93efa021b36102fc1eb624e"
```

---

## 5. Capa API

### Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Interfaz web (HTML con CSP) |
| `GET` | `/static/*` | Frontend estático |
| `GET` | `/api/health` | Estado del servicio |
| `GET` | `/api/config` | Configuración pública (modelos, disponibilidad de FFmpeg/Ollama) |
| `POST` | `/api/analyze` | Analiza una transcripción y devuelve clips candidatos |
| `GET` | `/api/history` | Historial de análisis |
| `GET` | `/api/history/{id}` | Detalle de un análisis |
| `DELETE` | `/api/history/{id}` | Elimina un análisis |
| `POST` | `/api/transcriptions` | Inicia un job de transcripción |
| `GET` | `/api/transcriptions/{id}` | Estado y progreso del job (SSE) |
| `POST` | `/api/renders` | Inicia un job de renderizado |
| `GET` | `/api/renders/{id}` | Estado y artefactos del render |

La especificación OpenAPI completa está en [`docs/openapi.yaml`](../openapi.yaml) y se
genera en vivo en `/docs` (Swagger UI).

### Cabeceras de seguridad

`api/app.py` aplica un middleware que añade a cada respuesta:

| Cabecera | Valor | Motivo |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Evita MIME sniffing |
| `Referrer-Policy` | `no-referrer` | No filtra URLs a terceros |
| `X-Request-ID` | UUID hex | Trazabilidad de peticiones en logs |
| `Content-Security-Policy` | (ver arriba) | Solo recursos propios |

La API key (opcional) se valida en `api/security.py`; si se define
`VIRALCLIP_API_KEY`, las rutas de escritura la exigen.

---

## 6. Configuración

Todas las variables usan el prefijo `VIRALCLIP_`. Se leen desde el entorno y desde un
archivo `.env` en el directorio de trabajo (`config.py::_load_dotenv`, que **no**
sobrescribe variables ya definidas).

| Variable | Por defecto | Descripción |
|---|---|---|
| `VIRALCLIP_ENV` | `development` | Entorno lógico |
| `VIRALCLIP_HOST` | `127.0.0.1` | Interfaz de escucha |
| `VIRALCLIP_PORT` | `8000` | Puerto |
| `VIRALCLIP_DB_PATH` | `data/viralclip.db` | Ruta de la base SQLite |
| `VIRALCLIP_API_KEY` | *(sin)* | API key para las rutas de escritura |
| `VIRALCLIP_CORS_ORIGINS` | `http://127.0.0.1:8000,http://localhost:8000` | Orígenes permitidos |
| `VIRALCLIP_MAX_INPUT_BYTES` | `2000000` | Tope del JSON de entrada |
| `VIRALCLIP_MAX_CLIPS` | `8` | Máximo de clips por análisis |
| `VIRALCLIP_MAX_SEGMENTS` | `20000` | Máximo de segmentos |
| `VIRALCLIP_WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium` |
| `VIRALCLIP_WHISPER_DEVICE` | `auto` | `auto`, `cpu`, `cuda` |
| `VIRALCLIP_WHISPER_COMPUTE_TYPE` | `auto` | Tipo de cómputo de CTranslate2 |
| `VIRALCLIP_WHISPER_LANGUAGE` | `auto` | `auto`, `es`, `en`, … |
| `VIRALCLIP_WHISPER_MODEL_DIR` | `<data_dir>/models` | Caché de modelos |
| `VIRALCLIP_WHISPER_VAD` | `true` | Filtro de voz de Silero |
| `VIRALCLIP_UPLOAD_DIR` | `<data_dir>/uploads` | Videos subidos |
| `VIRALCLIP_UPLOAD_MAX_BYTES` | `2000000000` | Tope de subida (2 GB) |
| `VIRALCLIP_FFMPEG_PATH` | `ffmpeg` | Ruta al binario |
| `VIRALCLIP_FFPROBE_PATH` | `ffprobe` | Ruta al binario |
| `VIRALCLIP_RENDER_DIR` | `<data_dir>/renders` | Salidas de render |
| `VIRALCLIP_RENDER_WIDTH` / `_HEIGHT` | `1080` / `1920` | Resolución vertical |
| `VIRALCLIP_RENDER_FPS` | `30` | Fotogramas por segundo |
| `VIRALCLIP_RENDER_CRF` | `20` | Calidad x264 (menor = mejor) |
| `VIRALCLIP_RENDER_PRESET` | `veryfast` | Perfil de x264 |
| `VIRALCLIP_RENDER_ZOOM` | `0.06` | Zoom ( Ken Burns ) del render |
| `VIRALCLIP_RENDER_FONT` / `_FONT_SIZE` | `Arial` / `54` | Tipografía de los subtítulos |
| `VIRALCLIP_RENDER_TIMEOUT` | `1800` | Segundos máximos por render |
| `VIRALCLIP_LLM_ENABLED` | `true` | Habilita el refinado con Ollama |
| `VIRALCLIP_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Endpoint de Ollama |
| `VIRALCLIP_OLLAMA_MODEL` | `llama3.2:latest` | Modelo usado |
| `VIRALCLIP_OLLAMA_TIMEOUT` | `60` | Timeout de inferencia |
| `VIRALCLIP_OLLAMA_CIRCUIT_FAILURES` | `3` | Fallos antes de abrir el circuito |
| `VIRALCLIP_OLLAMA_CIRCUIT_COOLDOWN` | `60` | Segundos de enfriamiento |
| `VIRALCLIP_LOG_LEVEL` | `INFO` | Nivel de log de Uvicorn |

---

## 7. Flujos internos

### 7.1 Análisis

```text
transcripción (JSON)
   └─ transcript.py       normaliza a lista de segmentos {start, end, text}
        └─ analyzer.py    puntúa ventanas candidatas (gancho, score, reason)
             └─ platforms.py  adapta longitudes y formato a la red
                  └─ subtitles.py  segmenta en 4-5 palabras y resalta keywords
                       └─ pipeline.py  arma el contrato de salida
                            └─ storage.py  persiste en SQLite
```

`analyzer.py` es el núcleo: produce un **gancho** (los primeros ~3 s), un **score**
explicable y una **reason** en lenguaje natural. `score` y `reason` se exponen en la UI
para que el usuario entienda *por qué* se propone un clip.

### 7.2 Transcripción

`transcription.py` coordina: extracción de audio con FFmpeg → `faster-whisper`
(CTranslate2) → normalización. Los modelos se descargan la primera vez al directorio de
datos del usuario y se cachean ahí.

El progreso se comunica con **SSE** (ADR-005) y la UI tiene fallback de *polling* si
`EventSource` falla. `app.js` gestiona ambos: `EventSource` primero, polling como red de
seguridad.

### 7.3 Renderizado

`render.py` invoca FFmpeg con:

- `-vf` con `scale`, `crop`, `zoompan` (efecto Ken Burns) y `subtitles` (filtro `ass`).
- `-c:v libx264` con `CRF` y `preset` configurables.
- `-c:a aac` para el audio.

La ruta de subtítulos usa el filtro `ass`, que requiere `libass` en la build de FFmpeg.

### 7.4 Integración con Ollama

`llm/ollama.py` implementa un **circuit breaker**: tras `OLLAMA_CIRCUIT_FAILURES` fallos
consecutivos, deja de llamar a Ollama durante `OLLAMA_CIRCUIT_COOLDOWN` segundos. Es
garantía de que una caída de Ollama **nunca** bloquea el análisis (ADR-004). El refinado
es opcional y el resultado degrada con elegancia al análisis determinista.

---

## 8. Persistencia

SQLite en modo **WAL** (ADR-003). Las rutas están en `storage.py` (~1150 líneas).

- WAL permite lecturas concurrentes mientras se escribe → la UI no se bloquea durante un
  análisis largo.
- Junto a la base aparecen `viralclip.db-wal` y `viralclip.db-shm`: es normal.
- Al arrancar, `api/app.py` marca como *interrumpidos* los jobs que quedaron en curso
  (transcripciones y renders) para que no queden colgados tras un cierre abrupto.

Esquemas de contrato en [`docs/contratos/`](../contratos/).

---

## 9. Empaquetado

Ver el detalle en [`empaquetado.md`](empaquetado.md). Resumen:

- PyInstaller en modo **`onedir`** con el spec `packaging/viralclip.spec`.
- `packaging/launcher.py` es el entry point: garantiza que `sys.stdout`/`sys.stderr`
  no sean `None`, redirige la salida al log del usuario y llama a
  `desktop.prepare_environment()` antes de delegar en `viralclip.cli`.
- `packaging/make_icon.py` genera `packaging/viralclip.ico` con Pillow.
- `build.bat` (Windows) y `build.sh` (macOS/Linux) orquestan: dependencias → icono →
  limpieza → PyInstaller.

```powershell
build.bat
# → dist\ViralClip\ViralClip.exe
```

El ejecutable **no escribe dentro de su carpeta**: los datos van a
`%LOCALAPPDATA%\ViralClip\`.

---

## 9-bis. Ventana de escritorio nativa

Desde la **0.5.0** el ejecutable es una aplicación de escritorio de verdad: abre
**su propia ventana** y no lanza el navegador del sistema.

### Arquitectura

```text
ViralClip.exe (console=False)
   └─ packaging/launcher.py
        ├─ ensure_streams()          sys.stdout/stderr nunca son None
        ├─ redirect_output_to_log()  → %LOCALAPPDATA%\ViralClip\viralclip.log
        └─ viralclip.cli.main()
             └─ cli.serve_window()
                  ├─ _start_server()  Uvicorn en hilo daemon
                  ├─ desktop_window.run_desktop_window(url)
                  │    └─ pywebview  → Edge WebView2 (Chromium embebido)
                  └─ _stop_server()  al cerrar la ventana
```

### Módulo `src/viralclip/desktop_window.py`

| Símbolo | Función |
|---|---|
| `run_desktop_window(url, ...)` | Crea la ventana, espera a que se cierre y devuelve el código de salida |
| `redirect_output_to_log(path)` | Envía stdout/stderr al log del usuario (tee a consola si existe) |
| `ensure_streams()` | Sustituye `None` por un flujo descartable (`_NullStream`) |
| `show_error(title, message)` | Diálogo nativo de error (`MessageBoxW`) en Windows |

La ventana usa **WebView2** (Edge Chromium embebido), que viene instalado de serie en
Windows 11 y en las actualizaciones recientes de Windows 10. Por eso los procesos
`msedgewebview2.exe` que aparecen son **hijos del EXE** (el motor embebido), no un
navegador abierto.

### Modos de arranque

| Comando | Comportamiento |
|---|---|
| `viralclip` / `ViralClip.exe` | **Ventana de escritorio** (por defecto) |
| `viralclip --browser` | Interfaz en el navegador del sistema |
| `viralclip --no-browser` | Solo el servidor local, sin interfaz |

### Arranque sin consola: por qué fallaba

El build de PyInstaller usa `console=False`, así que el intérprete deja
`sys.stdout = None` y `sys.stderr = None`. Uvicorn, al construir su `Config`,
configura el logging y sus formateadores llaman a `sys.stdout.isatty()`:

```python
# uvicorn/logging.py (v0.54.0)
self.use_colors = sys.stdout.isatty()   # ← AttributeError si stdout es None
```

El error que veía el usuario era:

```text
AttributeError: 'NoneType' object has no attribute 'isatty'
ValueError: Unable to configure formatter 'default'
```

La causa inmediata era que `packaging/launcher.py` llamaba a
`default_data_dir()` sin su argumento obligatorio `environ`, lanzando un `TypeError`
que un `except Exception: pass` ocultaba; la redirección al log no se aplicaba y
`sys.stdout` seguía a `None`.

La corrección aplica **tres capas**:

1. **Causa raíz** — `launcher.py` pasa `os.environ` y ya no oculta los errores.
2. **Garantía** — `ensure_streams()` instala un `_NullStream` cuando no hay consola,
   de modo que `sys.stdout.isatty()` nunca falla (llamado al inicio de `cli.main()`
   y en `_default_server_factory`).
3. **Defensa en profundidad** — `cli._uvicorn_log_config()` clona la configuración de
   logging de Uvicorn con `use_colors=False`, así que el formateador nunca consulta
   `isatty()`.

Los tests de regresión viven en `tests/test_no_console_startup.py`.

---

## 10. Extensibilidad

`hooks.py` define puntos de extensión para añadir comportamiento sin tocar el núcleo
(por ejemplo, plataformas adicionales o reglas de análisis propias). `platforms.py`
encapsula las diferencias entre TikTok, Reels y Shorts: añadir una red nueva implica
implementar su adaptador, no modificar el pipeline.

---

## 11. Rendimiento

| Aspecto | Medida |
|---|---|
| Análisis (texto) | < 100 ms para 20 000 segmentos |
| Transcripción | Dominada por Whisper; `small` en CPU ~1× tiempo real |
| Render | 1080×1920 @ 30 fps, `veryfast`, CRF 20 |
| Tamaño del bundle | ~254 MB (232 archivos) — incluye CTranslate2, PyAV, ONNX, NumPy, WebView2 |
| Tamaño del JSON de entrada | Tope de 2 MB |

---

## 12. Seguridad

| Medida | Implementación |
|---|---|
| Aislamiento de red | El servidor escucha en `127.0.0.1` por defecto |
| CSP | `default-src 'self'`; sin fuentes ni scripts de terceros |
| Sin telemetría | Ninguna llamada saliente salvo Ollama local y la descarga del modelo |
| Validación de entrada | Límite de bytes y de segmentos; validación Pydantic |
| API key opcional | `X-API-Key` / cabecera, solo si se define `VIRALCLIP_API_KEY` |
| Subida de archivos | Tope de 2 GB (`VIRALCLIP_UPLOAD_MAX_BYTES`) |
| Avoiding shells | FFmpeg se invoca con lista de argumentos, sin `shell=True` |

---

## 13. Diagnóstico

| Síntoma | Causa probable | Acción |
|---|---|---|
| La interfaz carga sin estilos | Assets no incluidos en el bundle | Revisar `datas` del spec y reconstruir |
| `ModuleNotFoundError: uvicorn...` | Falta un `hiddenimport` | Añadirlo a `packaging/viralclip.spec` |
| `ffmpeg not found` | FFmpeg no está en el `PATH` | Instalar FFmpeg o definir `VIRALCLIP_FFMPEG_PATH` |
| El render falla al escribir | Ruta sin permisos | Definir `VIRALCLIP_RENDER_DIR` en una ruta escribible |
| Ollama no responde | Servicio caído | El análisis sigue funcionando sin refinado (circuit breaker) |
| Error 403 al hacer push | Token sin permisos de escritura | Usar SSH o un PAT con scope `repo` |
| El antivirus borra el `.exe` | Falso positivo de PyInstaller | Firmar el binario o excluir localmente |

---

## 14. Referencias internas

- Manual de usuario → [manual-usuario.md](manual-usuario.md)
- Manual de despliegue → [despliegue.md](despliegue.md)
- Manual de empaquetado → [empaquetado.md](empaquetado.md)
- Fases del proyecto → [`../fases/`](../fases/)
- OpenAPI → [`../openapi.yaml`](../openapi.yaml)
- Ejemplos de API → [`../api/ejemplos.md`](../api/ejemplos.md)
