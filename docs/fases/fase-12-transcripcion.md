# Fase 12 — Transcripción local con Whisper

> **Proyecto:** Editor de Clips Virales
> **Fase:** 12 (ciclo audiovisual, primera parte)
> **Estado:** cerrada y aprobada por el usuario (2026-11-09)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Entradas:** app 0.2.0, lanzador y ejecutable, contratos de transcripción existentes

---

## 1. Resumen ejecutivo

Hasta ahora la app recibe una transcripción JSON ya hecha. Esta fase añade el primer paso
del pipeline audiovisual: **convertir un video local en una transcripción con tiempos por
palabra**, sin enviar audio a la nube.

Se usa **faster-whisper** (CTranslate2) sobre **CPU**, porque el equipo detectado no tiene
GPU NVIDIA: Intel i5-11400H (6 núcleos/12 hilos), 7,7 GB de RAM e Intel UHD. El modelo por
defecto será `small` con `int8`, configurable a `base`, `medium` o `large-v3`.

El video puede entrar por **subida desde la interfaz** o por **ruta local**. El audio se
extrae con **FFmpeg** a WAV 16 kHz mono, se transcribe y se guarda un JSON compatible con
el contrato existente. La interfaz permite después lanzar el análisis de clips con esa
transcripción.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Permitir que una persona que solo tiene un video pueda llegar a los clips sin preparar el
JSON a mano:

1. elegir un video (subida o ruta),
2. transcribirlo localmente con progreso,
3. revisar el resultado,
4. enviarlo al análisis existente con un clic.

### 2.2 Alcance

#### Incluye

- Dependencia `faster-whisper` (y `ctranslate2`, `av`, `onnxruntime` como transitivas) y
  `numpy`.
- Extracción de audio con FFmpeg (`ffmpeg -i video -vn -ac 1 -ar 16000`).
- Módulo `src/viralclip/transcription.py`:
  - detección de dispositivo (`cuda` si hay, si no `cpu`),
  - `compute_type` automático (`float16` en GPU, `int8` en CPU),
  - caché de modelos en el directorio de datos,
  - transcripción con `word_timestamps=True`,
  - salida normalizada al contrato de `normalize_transcript`.
- Lectura del WAV con `wave` y paso a Whisper como `numpy.ndarray` float32, evitando el
  decodificador de PyAV (incompatible entre faster-whisper 1.2.1 y av 19).
- Tabla `transcriptions` en SQLite y métodos de almacenamiento.
- API:
  - `POST /api/transcriptions/upload` (multipart),
  - `POST /api/transcriptions` (ruta local),
  - `GET /api/transcriptions`, `GET /api/transcriptions/{id}`,
  - `DELETE /api/transcriptions/{id}`,
  - `GET /api/transcriptions/{id}/events` (SSE de progreso),
  - `POST /api/transcriptions/{id}/analyze` para crear un análisis desde la transcripción.
- Panel **Transcribir video** en el frontend con arrastrar/soltar, ruta local, modelo,
  idioma, progreso y vista previa.
- `scripts/transcribe.py` para uso por línea de comandos.
- Variables de entorno y `.env.example`.
- Pruebas unitarias con un transcriptor falso (sin descargar modelos).
- Documentación de fase, manual, API, ADR y CHANGELOG `0.3.0`.

#### No incluye

- Renderizado, cortes, reencuadre o subtítulos quemados (Fase 13).
- Traducción automática.
- Diarización (quién habla).
- Transcripción en streaming o micrófono en vivo.
- Descarga automática de modelos dentro del ejecutable.
- GPU AMD/Intel (se usa CPU; CUDA si el usuario migra de equipo).

### 2.3 Decisiones aprobadas por el usuario (2026-11-09)

| Decisión | Opción elegida | Consecuencia |
|---|---|---|
| Orden | **Fase 12 transcripción, Fase 13 render** | Entregas separadas y verificables |
| Motor | **faster-whisper** | Wheel pip, CPU/GPU, tiempos por palabra |
| Hardware | **Detectar** | CPU `int8` por defecto en este equipo |
| Entrada | **Subida UI + ruta local** | Dos endpoints y un panel nuevo |
| Reencuadre | Centro + fondo desenfocado | Se implementa en Fase 13 |
| FFmpeg | Del sistema + ASS quemado | Fase 12 usa FFmpeg para extraer audio |

### 2.4 Arquitectura

```text
Video (upload o ruta)
        │
        ▼
[FFmpeg] extrae audio WAV 16 kHz mono
        │
        ▼
[faster-whisper] modelo small/int8 en CPU
        │  word_timestamps=True
        ▼
JSON {language, duration, segments[{start,end,text,words[]}]}
        │
        ├─► tabla transcriptions (estado, progreso, resultado)
        ├─► GET /api/transcriptions/{id}
        └─► POST /api/transcriptions/{id}/analyze → pipeline actual
```

### 2.5 Modelo de datos

Nueva tabla `transcriptions`:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | TEXT PK | UUID |
| `status` | TEXT | `queued`, `running`, `done`, `error` |
| `stage` | TEXT | `queued`, `extrayendo`, `transcribiendo`, `guardando`, `done`, `error` |
| `progress` | INTEGER | 0–100 |
| `source_path` | TEXT | Ruta del video original o copia subida |
| `filename` | TEXT | Nombre visible |
| `duration` | REAL | Duración del audio/video |
| `language` | TEXT | Idioma detectado o forzado |
| `model` | TEXT | `small`, `base`, etc. |
| `device` | TEXT | `cpu` o `cuda` |
| `error` | TEXT | Mensaje si falla |
| `result_json` | TEXT | JSON normalizado |
| `created_at` / `updated_at` | TEXT | ISO 8601 UTC |

Los archivos subidos viven en `%LOCALAPPDATA%\ViralClip\uploads` (Windows) o en el
directorio de datos del usuario. Se borran al borrar la transcripción. Los modelos se
guardan en `%LOCALAPPDATA%\ViralClip\models` para no sincronizar gigabytes en OneDrive.

### 2.6 Configuración nueva

| Variable | Defecto | Descripción |
|---|---|---|
| `VIRALCLIP_WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3` |
| `VIRALCLIP_WHISPER_DEVICE` | `auto` | `auto`, `cpu`, `cuda` |
| `VIRALCLIP_WHISPER_COMPUTE_TYPE` | `auto` | `auto`, `int8`, `float16`, `float32` |
| `VIRALCLIP_WHISPER_LANGUAGE` | `auto` | `auto`, `es`, `en`, … |
| `VIRALCLIP_WHISPER_MODEL_DIR` | datos/models | Caché de modelos (`%LOCALAPPDATA%\ViralClip\models` en Windows) |
| `VIRALCLIP_UPLOAD_MAX_BYTES` | `2000000000` | Límite de subida (2 GB) |
| `VIRALCLIP_UPLOAD_DIR` | datos/uploads | Carpeta de videos subidos (`%LOCALAPPDATA%\ViralClip\uploads`) |
| `VIRALCLIP_FFMPEG` | `ffmpeg` | Ruta o nombre del binario |

### 2.7 API

Subida:

```bash
curl -X POST http://127.0.0.1:8000/api/transcriptions/upload \
  -F "file=@video.mp4" \
  -F "model=small" \
  -F "language=es"
```

Ruta local:

```bash
curl -X POST http://127.0.0.1:8000/api/transcriptions \
  -H "Content-Type: application/json" \
  -d '{"path": "C:/videos/entrevista.mp4", "model": "small", "language": "es"}'
```

Respuesta `202`:

```json
{
  "id": "…",
  "status": "queued",
  "events_url": "/api/transcriptions/…/events"
}
```

Errores nuevos:

| Código | HTTP | Significado |
|---|---|---|
| `VC-1101` | 400 | Video no válido, no existe o extensión no soportada |
| `VC-1102` | 413 | Video demasiado grande |
| `VC-1103` | 503 | FFmpeg no disponible |
| `VC-1104` | 500 | Fallo de transcripción |

### 2.8 Interfaz

Nuevo panel **Transcribir video**, antes de **Nuevo análisis**:

- zona de arrastrar/soltar y selector de archivo;
- campo de ruta local;
- selectores de modelo e idioma;
- botón **Transcribir**;
- barra de progreso con etapa;
- vista previa de la transcripción (idioma, duración, número de segmentos);
- botón **Analizar esta transcripción** que rellena el panel de análisis.

El panel existente de pegar JSON se mantiene.

### 2.9 Actividades

1. Documentar esta planeación.
2. Añadir `faster-whisper` y comprobar la instalación real.
3. Implementar `transcription.py` y la detección de hardware.
4. Añadir la tabla y métodos en `Storage`.
5. Implementar los endpoints y el progreso.
6. Implementar el panel del frontend.
7. Crear `scripts/transcribe.py`.
8. Escribir pruebas unitarias y de API con transcriptor falso.
9. Probar con un video real corto y, si el tiempo lo permite, con uno largo.
10. Actualizar documentación, versión y empaquetado.
11. Cerrar la fase con evidencia.

### 2.10 Criterios de aceptación

- [ ] `faster-whisper` se instala y transcribe un video real en este equipo.
- [ ] La extracción de audio usa FFmpeg y falla con un error claro si no está.
- [ ] La transcripción tiene tiempos por palabra y cumple el contrato existente.
- [ ] La subida y la ruta local crean trabajos con estado y progreso.
- [ ] El resultado se guarda y se recupera desde SQLite.
- [ ] Se puede lanzar el análisis de clips desde una transcripción guardada.
- [ ] La interfaz permite transcribir sin pegar JSON.
- [ ] Las pruebas no descargan modelos ni dependen de GPU.
- [ ] `pytest`, `ruff` y `node --check` pasan.
- [ ] El `.exe` sigue funcionando (con modelos externos).

### 2.11 Riesgos

| Riesgo | Mitigación |
|---|---|
| Modelo grande y RAM limitada (7,7 GB) | `small`/`int8` por defecto; validar memoria antes |
| Transcripción de 2 h muy lenta en CPU | Progreso por etapas, aviso de tiempo y modelo configurable |
| `faster-whisper 1.2.1` incompatible con `av 19` | Extraer WAV con FFmpeg y pasar un array NumPy |
| Descarga del modelo en el primer uso | Documentar; cachear en datos/models y mostrar estado |
| FFmpeg ausente | Detección temprana y `VC-1103` con instrucciones |
| Subidas enormes llenan el disco | Límite configurable y borrado al eliminar |
| PyInstaller no incluye ctranslate2/av | `hiddenimports` y smoke del `.exe` |
| Ruta local arbitraria | API local y validación de extensión/tamaño; no se sirve el archivo |
| Modelo alucina tiempos | Whisper da tiempos; el análisis sigue validando el contrato |

### 2.12 Evidencia esperada

- `transcription.py`, tabla y endpoints.
- Panel de UI y script CLI.
- Pruebas unitarias/API en verde.
- Transcripción real de un video de prueba.
- Documento de cierre, manual y CHANGELOG `0.3.0`.

---

## 3. Cierre de fase

> **Estado:** cerrada y aprobada por el usuario el 2026-11-09.
> **Versión entregada:** 0.3.0.

### 3.1 Resultado

La app ya convierte un video local en una transcripción con tiempos por palabra y puede
lanzar el análisis de clips sin salir de la interfaz.

- `faster-whisper` 1.2.1 + CTranslate2 4.8.5 sobre CPU (`int8`), con detección de CUDA.
- Audio extraído por FFmpeg a WAV PCM 16 kHz mono y entregado a Whisper como array NumPy.
- Modelos `tiny`, `base`, `small` (defecto), `medium` y `large-v3`.
- Tabla `transcriptions`, progreso por SSE y análisis desde una transcripción terminada.
- Panel **Transcribir video** con arrastrar/soltar, ruta local, modelo, idioma y vista previa.
- Comando `viralclip --transcribe` y script `scripts/transcribe.py`.

### 3.2 Evidencia

Verificación automática:

| Comprobación | Resultado |
|---|---|
| `pytest` | **320 pruebas pasaron** |
| Cobertura | **90 %** (2736 sentencias) |
| `ruff check src tests scripts` | Limpio |
| `node --check src/viralclip/web/app.js` | Limpio |
| `docs/openapi.yaml` | 13 rutas, 15 esquemas, tag `transcripcion` |

Transcripción real del video de prueba `prueba.mp4` (11,703 s, español):

| Modelo | Resultado |
|---|---|
| `small` `int8` | 3 segmentos, 33 palabras, idioma `es` |
| `medium` `int8` | 3 segmentos, 33 palabras, idioma `es` |

Ejemplo de salida (`small`):

```text
0.00–4.62  Nadie te cuenta esto, el 80% de las ventas se pierde por no preguntar.
5.32–7.62  El error que frena tus ventas es hablar demasiado.
8.68–10.92 Tienes que dejar de hablar y empezar a escuchar.
```

Caché real de modelos: 13 archivos, **1923,4 MB** (`small` + `medium`) en
`%LOCALAPPDATA%\ViralClip\models`.

Smoke del ejecutable reconstruido:

```text
ViralClip.exe --version            → viralclip 0.3.0
GET /                              → 200 (13 136 bytes)
GET /static/app.js                 → 200 (38 104 bytes)
GET /api/health                    → 200 status ok, version 0.3.0
GET /api/config                    → 200 con whisper_models y ffmpeg_available=true
ViralClip.exe --transcribe ...     → 3 segmentos, JSON guardado
POST /api/transcriptions/upload    → 202; luego done, 3 segmentos, es
POST /api/transcriptions/{id}/analyze → 202; análisis done con 1 clip
DELETE /api/transcriptions/{id}    → 204
```

Tamaño del bundle:

| Elemento | Valor |
|---|---|
| `ViralClip.exe` | 14 551 103 bytes (~13,9 MB) |
| Carpeta `dist/ViralClip` | 263 181 209 bytes (~251 MB) |
| Archivos | 206 |

El bundle se redujo retirando `collect_all` de ONNX Runtime, PyAV, tokenizers y
huggingface_hub (sus hooks ya estaban activos) y conservando solo los datos de
`faster_whisper` y las DLL de `ctranslate2`.

### 3.3 Criterios de aceptación

- [x] `faster-whisper` se instala y transcribe un video real en este equipo.
- [x] La extracción de audio usa FFmpeg y falla con un error claro si no está.
- [x] La transcripción tiene tiempos por palabra y cumple el contrato existente.
- [x] La subida y la ruta local crean trabajos con estado y progreso.
- [x] El resultado se guarda y se recupera desde SQLite.
- [x] Se puede lanzar el análisis de clips desde una transcripción guardada.
- [x] La interfaz permite transcribir sin pegar JSON.
- [x] Las pruebas no descargan modelos ni dependen de GPU.
- [x] `pytest`, `ruff` y `node --check` pasan.
- [x] El `.exe` sigue funcionando con modelos externos y transcribe de verdad.

### 3.4 Deuda consciente

- Sin diarización (quién habla), traducción automática ni transcripción en vivo.
- Solo se valida CPU Intel/AMD; CUDA se detecta pero no se probó en este equipo.
- GPU AMD/Intel no están soportadas por CTranslate2 en esta configuración.
- El modelo se descarga en el primer uso; el `.exe` no lo incluye y necesita red una vez.
- El progreso es por etapas, no por segmento ni token.
- El bundle es grande porque incluye CTranslate2, PyAV, ONNX Runtime y tokenizers; se
  recortaron las herramientas CLI, pero no se hizo una poda más agresiva para no romper
  DLLs nativas.
- PyInstaller mantiene avisos no bloqueantes de módulos opcionales (`tzdata`, `onnx`).

### 3.5 Handoff a la Fase 13

La Fase 13 tomará el JSON de transcripción (o el análisis ya generado) y renderizará el
clip final con FFmpeg del sistema:

1. corte por marcas de tiempo;
2. reencuadre 9:16 con centro y fondo desenfocado;
3. zoom dinámico;
4. subtítulos `.ass` quemados;
5. miniatura y metadatos de salida.

Antes de escribir código se confirmará el alcance exacto (resoluciones, duración máxima,
estilo de subtítulos, manejo de errores y almacenamiento de renders).

### 3.6 Criterio de aprobación

El usuario aprobó este cierre el **2026-11-09** y autorizó el inicio de la **Fase 13 —
Renderizado con FFmpeg**. La planeación de esa fase se documenta en
[`fase-13-renderizado.md`](fase-13-renderizado.md).
