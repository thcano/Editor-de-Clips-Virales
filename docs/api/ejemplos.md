# API — ejemplos de uso

> Contrato completo: [`docs/openapi.yaml`](../openapi.yaml) · Swagger UI: `http://127.0.0.1:8000/docs`

URL base por defecto: `http://127.0.0.1:8000`

---

## Autenticación

La API es local y no exige autenticación por defecto. Si defines `VIRALCLIP_API_KEY`,
todas las rutas `/api/*` requieren la cabecera:

```http
X-API-Key: tu-clave
```

Cada respuesta incluye `X-Request-ID`; puedes enviar el tuyo para correlacionar:

```http
X-Request-ID: prueba-123
```

---

## Estado del servicio

```bash
curl http://127.0.0.1:8000/api/health
```

```json
{
  "status": "ok",
  "version": "0.3.0",
  "database": "ok",
  "ollama": {
    "available": true,
    "model": "llama3.2:latest",
    "message": "Ollama disponible"
  }
}
```

`status` es `degraded` si la base falla o si Ollama está habilitado pero no responde.

---

## Configuración

```bash
curl http://127.0.0.1:8000/api/config
```

```json
{
  "max_clips": 8,
  "max_input_bytes": 2000000,
  "platforms": ["tiktok", "reels", "shorts"],
  "llm_enabled": true,
  "flags": ["export_srt", "sse_progress"],
  "whisper_models": ["tiny", "base", "small", "medium", "large-v3"],
  "whisper_model": "small",
  "whisper_device": "cpu",
  "whisper_language": "auto",
  "upload_max_bytes": 2000000000,
  "ffmpeg_available": true
}
```

---

## Transcribir un video

### Subida por multipart

```bash
curl -X POST http://127.0.0.1:8000/api/transcriptions/upload \
  -F "file=@video.mp4" \
  -F "model=small" \
  -F "language=es"
```

### Ruta local

```bash
curl -X POST http://127.0.0.1:8000/api/transcriptions \
  -H "Content-Type: application/json" \
  -d '{"path": "C:/videos/entrevista.mp4", "model": "medium", "language": "auto"}'
```

Ambas responden `202 Accepted`:

```json
{
  "id": "6f1c8d2a-6d07-4980-9386-00a40635d6c6",
  "status": "queued",
  "events_url": "/api/transcriptions/6f1c8d2a-6d07-4980-9386-00a40635d6c6/events"
}
```

### Consultar el resultado

```bash
curl http://127.0.0.1:8000/api/transcriptions/6f1c8d2a-6d07-4980-9386-00a40635d6c6
```

```json
{
  "id": "6f1c8d2a-6d07-4980-9386-00a40635d6c6",
  "status": "done",
  "progress": 100,
  "stage": "done",
  "filename": "video.mp4",
  "model": "small",
  "device": "cpu",
  "language": "es",
  "duration": 11.703,
  "error": null,
  "transcript": {
    "language": "es",
    "duration": 11.703,
    "segments": [
      {
        "start": 0.0,
        "end": 4.62,
        "text": "Nadie te cuenta esto…",
        "words": [
          {"word": "Nadie", "start": 0.0, "end": 0.28, "confidence": 0.91}
        ]
      }
    ]
  }
}
```

### Progreso por SSE

```bash
curl -N http://127.0.0.1:8000/api/transcriptions/6f1c8d2a-6d07-4980-9386-00a40635d6c6/events
```

Emite eventos `progress`, `done` o `error` con `id`, `status`, `progress`, `stage` y
`updated_at`.

### Analizar la transcripción

```bash
curl -X POST http://127.0.0.1:8000/api/transcriptions/6f1c8d2a-6d07-4980-9386-00a40635d6c6/analyze \
  -H "Content-Type: application/json" \
  -d '{"platform": "tiktok", "max_clips": 3, "use_llm": false}'
```

Devuelve el mismo `JobAccepted` que `POST /api/analyses`.

### Borrar

```bash
curl -X DELETE http://127.0.0.1:8000/api/transcriptions/6f1c8d2a-6d07-4980-9386-00a40635d6c6
```

Responde `204` y borra el video subido si estaba en la carpeta de subidas.

---

## Crear un análisis

```bash
curl -X POST http://127.0.0.1:8000/api/analyses \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": [
      {"start": 0, "end": 6, "text": "Nadie te cuenta esto: el 80% de las ventas se pierde por no preguntar."},
      {"start": 6, "end": 12, "text": "El error que frena tus ventas es hablar demasiado."},
      {"start": 12, "end": 18, "text": "Tienes que dejar de hablar y empezar a escuchar."},
      {"start": 18, "end": 24, "text": "La pregunta más poderosa es: ¿qué te impide comprar hoy?"},
      {"start": 24, "end": 30, "text": "Cuando la haces, el cliente te dice exactamente qué necesita."}
    ],
    "platform": "tiktok",
    "max_clips": 3,
    "use_llm": false,
    "min_duration": 15,
    "max_duration": 30
  }'
```

Respuesta `202 Accepted`:

```json
{
  "id": "2cd182b3-6d07-4980-9386-00a40635d6c6",
  "status": "queued",
  "events_url": "/api/analyses/2cd182b3-6d07-4980-9386-00a40635d6c6/events"
}
```

Campos de la petición:

| Campo | Tipo | Defecto | Límites |
|---|---|---|---|
| `transcript` | objeto o lista | — | requerido; ver formatos aceptados |
| `platform` | string | `tiktok` | `tiktok`, `reels`, `shorts` |
| `max_clips` | entero | `5` | 1–20 (limitado por `VIRALCLIP_MAX_CLIPS`) |
| `use_llm` | booleano | `true` | usa Ollama si está disponible |
| `min_duration` | número | `15` | 5–180 |
| `max_duration` | número | `60` | 10–180 y mayor que `min_duration` |

---

## Consultar un análisis

```bash
curl http://127.0.0.1:8000/api/analyses/2cd182b3-6d07-4980-9386-00a40635d6c6
```

```json
{
  "id": "2cd182b3-6d07-4980-9386-00a40635d6c6",
  "status": "done",
  "created_at": "2026-11-09T23:15:20.930624Z",
  "updated_at": "2026-11-09T23:15:20.945175Z",
  "platform": "tiktok",
  "progress": 100,
  "stage": "done",
  "engine": {
    "name": "heuristic",
    "model": null,
    "degraded": false,
    "notes": "Ollama está desactivado por configuración."
  },
  "error": null,
  "clips": [
    {
      "id": "clip_001",
      "rank": 1,
      "start_time": "00:00",
      "end_time": "00:24",
      "start_seconds": 0.0,
      "end_seconds": 24.0,
      "duration_seconds": 24.0,
      "platform": "tiktok",
      "hook": "¿Y si todo lo que sabes de ventas está mal?",
      "title": "¿Y si todo lo que sabes de ventas está mal?",
      "description": "Nadie te cuenta esto: el 80% de las ventas se pierde por no preguntar.",
      "caption_text": "Nadie te cuenta esto: el 80% de las ventas se pierde por no preguntar. El error que frena tus ventas es hablar demasiado.",
      "hashtags": ["#ventas", "#tiktok", "#emprendimiento"],
      "score": 0.91,
      "reason": "Dato impactante + error común + consejo práctico.",
      "keywords": ["ventas", "preguntar", "error"],
      "subtitles": [
        {"start": 0.0, "end": 1.8, "text": "Nadie te cuenta esto:", "highlight": "cuenta"},
        {"start": 1.8, "end": 3.6, "text": "el 80% de las ventas", "highlight": "80%"}
      ]
    }
  ]
}
```

Estados: `queued`, `running`, `done`, `error`. `progress` va de 0 a 100 y `stage` indica la
etapa legible (`queued`, `validando`, `preparando`, `candidatos`, `ganchos`, `clips`,
`done`, `error`).

---

## Listar análisis

```bash
curl "http://127.0.0.1:8000/api/analyses?limit=20&offset=0&status=done"
```

```json
{
  "items": [
    {
      "id": "2cd182b3-6d07-4980-9386-00a40635d6c6",
      "status": "done",
      "platform": "tiktok",
      "progress": 100,
      "stage": "done",
      "created_at": "2026-11-09T23:15:20.930624Z",
      "updated_at": "2026-11-09T23:15:20.945175Z",
      "engine": {"name": "heuristic", "model": null, "degraded": false, "notes": null},
      "error": null,
      "clips": []
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

Parámetros: `limit` (1–100), `offset` (≥ 0) y `status` opcional.

---

## Borrar un análisis

```bash
curl -X DELETE http://127.0.0.1:8000/api/analyses/2cd182b3-6d07-4980-9386-00a40635d6c6
```

Respuesta `204 No Content`. Si no existe: `404 VC-2001`.

---

## Exportar

```bash
curl -o resultado.json  "http://127.0.0.1:8000/api/analyses/{id}/export?format=json"
curl -o resultado.spec  "http://127.0.0.1:8000/api/analyses/{id}/export?format=spec"
curl -o resultado.srt   "http://127.0.0.1:8000/api/analyses/{id}/export?format=srt"
curl -o resultado.vtt   "http://127.0.0.1:8000/api/analyses/{id}/export?format=vtt"
```

| Formato | Tipo | Notas |
|---|---|---|
| `json` | `application/json` | Resultado completo |
| `spec` | `application/json` | Formato mínimo de `SKILLS.md` |
| `srt` | `application/x-subrip` | Requiere `export_srt` activo |
| `vtt` | `text/vtt` | Requiere `export_srt` activo |

SRT de un clip concreto:

```bash
curl -o clip_001.srt "http://127.0.0.1:8000/api/analyses/{id}/clips/clip_001/srt"
```

Si el flag está apagado: `403 VC-2003`. Si el análisis no terminó: `409 VC-2002`.

---

## Progreso por SSE

```bash
curl -N "http://127.0.0.1:8000/api/analyses/{id}/events" \
  -H "Last-Event-ID: 5"
```

```text
retry: 3000

id: 6
event: progress
data: {"id":"...","status":"running","progress":40,"stage":"candidatos","updated_at":"..."}

id: 7
event: done
data: {"id":"...","status":"done","progress":100,"stage":"done","updated_at":"..."}
```

- `retry: 3000` indica al cliente cuándo reconectar.
- `id` es incremental; `Last-Event-ID` continúa desde el último recibido.
- `event` puede ser `progress`, `done` o `error`.
- Se envían heartbeats `: ping` cada 15 s.
- El stream termina en estado terminal o tras 10 minutos de seguridad.

---

## Feature flags

```bash
curl http://127.0.0.1:8000/api/flags
```

```json
[
  {
    "name": "export_srt",
    "enabled": true,
    "owner": "equipo",
    "expires_at": null,
    "description": "Habilita la exportación SRT/VTT."
  },
  {
    "name": "sse_progress",
    "enabled": true,
    "owner": "equipo",
    "expires_at": null,
    "description": "Usa SSE para el progreso en la interfaz."
  }
]
```

Actualizar:

```bash
curl -X PATCH http://127.0.0.1:8000/api/flags \
  -H "Content-Type: application/json" \
  -d '{"name": "export_srt", "enabled": false}'
```

---

## Errores

Formato estable:

```json
{
  "code": "VC-1001",
  "message": "La transcripción no es válida.",
  "detail": "El segmento 2 no tiene 'text'.",
  "request_id": "9f2c..."
}
```

| Código | HTTP | Significado |
|---|---|---|
| `VC-1001` | 400 | Transcripción inválida |
| `VC-1002` | 413 | Payload demasiado grande |
| `VC-1003` | 422 | Parámetros fuera de rango |
| `VC-1101` | 400 | Video no válido, inexistente o con extensión no soportada |
| `VC-1102` | 413 | Video demasiado grande |
| `VC-1103` | 503 | FFmpeg no disponible |
| `VC-1104` | 500 | Fallo de transcripción |
| `VC-2001` | 404 | Análisis o clip no encontrado |
| `VC-2002` | 409 | Análisis todavía no listo para exportar |
| `VC-2003` | 403 | Función desactivada por un feature flag local |
| `VC-2004` | 404 | Transcripción no encontrada |
| `VC-3001` | 401 | API key ausente o inválida |
| `VC-4001` | 502 | Ollama no disponible (degradado, no fatal) |
| `VC-5001` | 500 | Error interno |

---

## Ejemplo completo con PowerShell

```powershell
$body = @{
  transcript = @(
    @{ start = 0;  end = 6;  text = "Nadie te cuenta esto: el 80% de las ventas se pierde por no preguntar." },
    @{ start = 6;  end = 12; text = "El error que frena tus ventas es hablar demasiado." },
    @{ start = 12; end = 18; text = "Tienes que dejar de hablar y empezar a escuchar." }
  )
  platform = "tiktok"
  max_clips = 2
  use_llm = $false
} | ConvertTo-Json -Depth 5

$job = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/analyses" `
  -ContentType "application/json" -Body $body

do {
  Start-Sleep -Milliseconds 300
  $detail = Invoke-RestMethod "http://127.0.0.1:8000/api/analyses/$($job.id)"
} while ($detail.status -in @("queued", "running"))

$detail.clips | Select-Object rank, start_time, end_time, hook, score
```
