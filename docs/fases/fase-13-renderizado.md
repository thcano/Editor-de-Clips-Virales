# Fase 13 — Renderizado con FFmpeg

> **Proyecto:** Editor de Clips Virales
> **Fase:** 13 (ciclo audiovisual, segunda parte)
> **Estado:** en planeación (aprobación de decisiones pendiente)
> **Fecha de inicio:** 2026-11-09
> **Entradas:** app 0.3.0, transcripción con tiempos por palabra, análisis con clips y
> subtítulos, FFmpeg 8.1 con `libass`/`libx264`

---

## 1. Resumen ejecutivo

La app ya transcribe y analiza, pero el clip final se monta a mano. Esta fase cierra el
pipeline: toma un clip del análisis y el video de origen, y produce un **MP4 vertical
1080×1920** listo para publicar, con:

- corte exacto por las marcas de tiempo del clip;
- reencuadre 9:16 con **fondo desenfocado** y video centrado;
- **zoom suave** de 1.0 a 1.06 durante el clip;
- **subtítulos `.ass` quemados** (blanco con palabras clave en amarillo);
- **miniatura JPG**;
- descarga local del video y la miniatura.

Todo se ejecuta con el **FFmpeg del sistema**; no hay servicios externos ni telemetría.

---

## 2. Planeación

### 2.1 Objetivo

Que una persona pueda pasar de un video y su análisis a un archivo publicable sin abrir un
editor de video:

1. elegir un clip analizado,
2. confirmar el video de origen (automático si vino de una transcripción),
3. renderizar con progreso,
4. previsualizar, descargar el MP4 y la miniatura.

### 2.2 Decisiones aprobadas por el usuario (2026-11-09)

| Decisión | Opción elegida | Consecuencia |
|---|---|---|
| Origen del video | **Automático desde la transcripción + ruta manual** | Los análisis manuales piden ruta; los de transcripción la heredan |
| Formato | **1080×1920, 30 fps, H.264 CRF 20** | Calidad alta; más lento en CPU |
| Audio | AAC 192 kbps, sin normalización agresiva | Conserva el audio original |
| Subtítulos | **ASS quemados, blancos con resaltado amarillo** | Requiere `libass` en FFmpeg |
| Reencuadre | **Fondo desenfocado + video centrado + zoom 1.0→1.06** | Filtro complejo con `boxblur` y `overlay` |
| Miniatura | **JPG del primer segundo** | Se extrae del clip renderizado |
| Salida | **`%LOCALAPPDATA%\ViralClip\renders`** | Fuera de OneDrive; botón de descarga |
| Progreso | SSE + sondeo, una renderización a la vez | Evita saturar la CPU |

### 2.3 Alcance

#### Incluye

- Módulo `src/viralclip/render.py`:
  - validación de video, clip y rutas;
  - sonda de dimensiones/duración con `ffprobe`;
  - generación de subtítulos `.ass` desde `clip.subtitles`;
  - grafo de filtros de reencuadre, fondo, zoom y subtítulos;
  - renderizado, miniatura y limpieza de temporales.
- Tabla `renders` en SQLite con estado, progreso, rutas y error.
- Columna `source_path` en `jobs` (nullable) para recordar el video de la transcripción.
- API:
  - `POST /api/analyses/{analysis_id}/clips/{clip_id}/render`,
  - `GET /api/renders`, `GET /api/renders/{id}`,
  - `GET /api/renders/{id}/events` (SSE),
  - `GET /api/renders/{id}/download`,
  - `GET /api/renders/{id}/thumbnail`,
  - `DELETE /api/renders/{id}`.
- Runner en segundo plano serializado, con progreso por etapas.
- Botón **Renderizar clip** en el detalle del análisis, con ruta manual si hace falta,
  barra de progreso, `<video>` de vista previa y descargas.
- Comando `viralclip --render <analysis.json> --clip clip_001 --video video.mp4`.
- Variables de entorno, pruebas unitarias/API y smoke real con FFmpeg.
- Documentación: fase, manual, API/OpenAPI, ADR, CHANGELOG y versión `0.4.0`.

#### No incluye

- Publicación automática en redes sociales.
- Edición multipista, transiciones, música de fondo ni voz en off.
- Detección de caras o seguimiento inteligente del encuadre.
- Renderizado en GPU (se usa `libx264` en CPU).
- Cola distribuida o renderizado paralelo.
- Revisión visual automática del resultado (la validación es técnica + smoke humano).

### 2.4 Arquitectura

```text
Análisis (jobs + clips)
        │  clip_id, start_seconds, end_seconds, subtitles[]
        ▼
[render.py] valida video y clip
        │
        ├─► escribe subtítulos.ass (tiempos relativos al clip)
        ├─► ffprobe: dimensiones, duración, audio
        ▼
[FFmpeg] -ss start -t duration
        │  fondo: scale+crop+boxblur+eq
        │  frente: scale animado 1.0→1.06
        │  overlay centrado + ass + yuv420p
        │  libx264 CRF 20 + AAC 192k
        ▼
MP4 1080×1920 + miniatura JPG
        │
        ├─► tabla renders (estado, progreso, rutas)
        ├─► SSE /api/renders/{id}/events
        └─► descarga /api/renders/{id}/download
```

### 2.5 Modelo de datos

Nueva tabla `renders`:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | TEXT PK | UUID |
| `job_id` | TEXT | Análisis de origen |
| `clip_id` | TEXT | `clip_001`, etc. |
| `transcription_id` | TEXT NULL | Si el video vino de una transcripción |
| `status` | TEXT | `queued`, `running`, `done`, `error` |
| `stage` | TEXT | `validando`, `preparando`, `renderizando`, `miniatura`, `done`, `error` |
| `progress` | INTEGER | 0–100 |
| `source_path` | TEXT | Video usado |
| `output_path` | TEXT | MP4 generado |
| `thumbnail_path` | TEXT | JPG generado |
| `width` / `height` | INTEGER | 1080 / 1920 |
| `duration` | REAL | Duración renderizada |
| `size_bytes` | INTEGER | Tamaño del MP4 |
| `error_code` / `error_message` | TEXT | Error estable |
| `created_at` / `updated_at` | TEXT | ISO 8601 UTC |

`jobs` gana `source_path TEXT` (nullable) para los análisis creados desde una
transcripción. La migración usa `ALTER TABLE` protegido para bases existentes.

### 2.6 Filtros FFmpeg

Fondo:

```text
scale=1080:1920:force_original_aspect_ratio=increase,
crop=1080:1920,
boxblur=20:2,
eq=brightness=-0.10:saturation=0.9
```

Frente (video completo, centrado, sin recortar los lados):

```text
scale=w='trunc(1080*(1+0.06*t/D)/2)*2':h=-2:eval=frame
```

Composición:

```text
[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto,ass=subtitulos.ass,format=yuv420p
```

Notas:

- `D` es la duración del clip; el zoom llega a 1.06 al final.
- Si el video es vertical, el frente se escala por altura para no salirse del marco.
- El `.ass` se escribe en el directorio de trabajo temporal y se referencia por nombre
  para evitar problemas de escapado de rutas en Windows.
- Si el video no tiene audio, se añade silencio con `anullsrc` para que el MP4 sea
  reproducible en todas las plataformas.

### 2.7 Subtítulos `.ass`

- Estilo base: `Arial` (fallback del sistema), 54 px, blanco, borde negro de 3 px,
  alineación inferior centrada, margen vertical 220 px.
- Palabras con `highlight=true`: amarillo `#FFD400` (BGR `&H00D4FF&`).
- Tiempos: `clip.subtitles` viene en segundos absolutos; se restan `start_seconds` y se
  recortan a `[0, duración]`.
- Se conservan los saltos de 4–5 palabras ya calculados por `build_subtitles`.
- Se escapan llaves, saltos de línea y barras invertidas.

### 2.8 API

Solicitud:

```http
POST /api/analyses/{analysis_id}/clips/{clip_id}/render
Content-Type: application/json

{
  "video_path": "C:/videos/entrevista.mp4",   // opcional si hay source_path
  "force": false
}
```

Respuesta `202`:

```json
{
  "id": "…",
  "status": "queued",
  "events_url": "/api/renders/…/events"
}
```

Errores nuevos:

| Código | HTTP | Significado |
|---|---|---|
| `VC-1201` | 400 | Video de origen ausente, inexistente o no soportado |
| `VC-1202` | 503 | FFmpeg/ffprobe no disponible |
| `VC-1203` | 500 | Fallo de renderizado |
| `VC-1204` | 409 | Ya hay un render activo para ese clip |
| `VC-2005` | 404 | Render no encontrado |

Se reutilizan `VC-2001` (análisis/clip no encontrado) y `VC-2003` (flag desactivado).

### 2.9 Configuración nueva

| Variable | Defecto | Descripción |
|---|---|---|
| `VIRALCLIP_RENDER_DIR` | datos/renders | Carpeta de MP4 y miniaturas |
| `VIRALCLIP_RENDER_WIDTH` | `1080` | Ancho de salida |
| `VIRALCLIP_RENDER_HEIGHT` | `1920` | Alto de salida |
| `VIRALCLIP_RENDER_FPS` | `30` | Fotogramas por segundo |
| `VIRALCLIP_RENDER_CRF` | `20` | Calidad H.264 (menor = mejor) |
| `VIRALCLIP_RENDER_PRESET` | `veryfast` | Preset de libx264 |
| `VIRALCLIP_RENDER_ZOOM` | `0.06` | Zoom final (0 = sin zoom) |
| `VIRALCLIP_RENDER_FONT` | `Arial` | Fuente de los subtítulos |
| `VIRALCLIP_RENDER_FONT_SIZE` | `54` | Tamaño en píxeles |
| `VIRALCLIP_RENDER_TIMEOUT` | `1800` | Segundos máximos por clip |

### 2.10 Interfaz

En el panel **Resultado**, cada clip muestra:

- botón **Renderizar clip**;
- campo de ruta solo si el análisis no tiene `source_path`;
- barra de progreso con etapa;
- reproductor `<video>` y miniatura cuando termina;
- botones **Descargar MP4** y **Descargar miniatura**;
- estado del render guardado al volver al historial.

### 2.11 Actividades

1. Documentar esta planeación y confirmar las decisiones abiertas.
2. Implementar `render.py` (sonda, ASS, filtros, render, miniatura).
3. Añadir tabla `renders`, columna `source_path` y migración.
4. Implementar endpoints, runner serializado y SSE.
5. Integrar el botón y la vista previa en el frontend.
6. Añadir el comando `--render` y el script de apoyo.
7. Escribir pruebas unitarias/API con renderizador falso.
8. Smoke real: renderizar un clip del video de prueba y verificar con `ffprobe`.
9. Actualizar documentación, versión `0.4.0` y empaquetado.
10. Cerrar la fase con evidencia.

### 2.12 Criterios de aceptación

- [ ] Un clip del análisis se renderiza a MP4 1080×1920, 30 fps, H.264/AAC.
- [ ] El video conserva el encuadre centrado y el fondo desenfocado.
- [ ] El zoom suave se aplica sin deformar ni recortar el contenido principal.
- [ ] Los subtítulos `.ass` aparecen quemados, sincronizados y con resaltado amarillo.
- [ ] La miniatura JPG se genera y se puede descargar.
- [ ] El render usa automáticamente el video de la transcripción y admite ruta manual.
- [ ] El progreso se ve por SSE y por sondeo; solo hay un render a la vez.
- [ ] Los errores de FFmpeg, video ausente y clip inválido tienen códigos estables.
- [ ] Los renders se guardan fuera de OneDrive y se borran con su registro.
- [ ] `pytest`, `ruff`, `node --check` y el smoke real pasan.
- [ ] El `.exe` sigue funcionando y renderiza con el FFmpeg del sistema.

### 2.13 Riesgos

| Riesgo | Mitigación |
|---|---|
| Render lento en CPU (i5, 7,7 GB) | `veryfast`, 30 fps, una cola, progreso y límite de duración |
| Rutas con espacios/acentos en filtros | `.ass` en directorio temporal y referencias relativas |
| Fuente Arial ausente en otros equipos | Fallback a `DejaVu Sans`/`Liberation Sans` y aviso |
| Video sin audio | Pista de silencio con `anullsrc` |
| Video vertical u origen 4:3 | Cálculo de escala por dimensiones con `ffprobe` |
| Zoom animado inestable | Validar con smoke; fallback a zoom constante 1.03 |
| Clip con tiempos fuera del video | Validar `start/end` contra la duración real |
| Disco lleno | Validar espacio y borrar temporales; el usuario puede borrar renders |
| `libass` no disponible | Comprobar `ffmpeg -filters` y devolver `VC-1202` |

### 2.14 Evidencia esperada

- `render.py`, tabla `renders`, endpoints y UI.
- Pruebas unitarias/API en verde.
- MP4 real de un clip con `ffprobe` mostrando 1080×1920, 30 fps, H.264/AAC.
- Miniatura JPG real.
- Documento de cierre, manual, OpenAPI, ADR y CHANGELOG `0.4.0`.

---

## 3. Decisiones abiertas antes de implementar

Ninguna bloqueante: las cinco decisiones de producto ya fueron aprobadas. Durante la
implementación se confirmarán detalles menores (fuente exacta disponible en el equipo,
preset final y manejo de videos sin audio) y se documentarán en el ADR-010.

## 4. Cierre de fase

_Pendiente de implementación y aprobación._
