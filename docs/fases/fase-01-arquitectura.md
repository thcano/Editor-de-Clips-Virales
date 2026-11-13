# Fase 1 — Arquitectura, stack, ADRs y contratos

> **Proyecto:** Editor de Clips Virales
> **Fase:** 1 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Entradas:** `docs/fases/fase-00-descubrimiento.md`, respuestas del usuario

---

## 1. Resumen ejecutivo

Se define una arquitectura **monolito modular local-first**:

- **Backend Python 3.11+ / FastAPI** con un núcleo de dominio independiente de la API.
- **Frontend web** en HTML/CSS/JS sin paso de build, servido por el propio backend.
- **SQLite** en modo WAL para historial, clips, ajustes, feature flags y auditoría.
- **Ollama opcional** para refinamiento semántico y redacción de ganchos, con **fallback
  heurístico determinista**.
- **SSE** para progreso en tiempo real y **exportación** JSON/SRT/VTT.
- **Contratos versionados** para la transcripción de entrada y la salida de clips.

La app funciona sin conexión a internet y sin Ollama. La nube no es un requisito.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Convertir las decisiones de producto en una arquitectura ejecutable, con:

- mapa de componentes y responsabilidades,
- ADRs que justifican cada decisión,
- contratos de datos versionados,
- borrador de API OpenAPI,
- estrategia de pruebas, seguridad y observabilidad,
- estructura de repositorio y dependencias.

### 2.2 Principios de diseño

1. **Núcleo puro y testeable:** el pipeline no depende de FastAPI ni de SQLite.
2. **Degradación explícita:** sin Ollama se usan heurísticas; la UI lo comunica.
3. **Local-first:** nada sale del equipo por defecto; sin telemetría externa.
4. **Contratos primero:** validar entrada y salida con esquemas antes de persistir.
5. **Explicabilidad:** cada clip lleva `score` y `reason`.
6. **Accesibilidad desde el inicio:** HTML semántico, teclado, contraste y movimiento reducido.
7. **Fallar con códigos estables:** errores `VC-xxxx` con mensaje para usuario y traza.
8. **Sin estado local en la capa web:** la API puede reiniciarse sin perder trabajos.

### 2.3 Mapa de componentes

```
┌──────────────────────────────────────────────────────────────┐
│  web/  (HTML + CSS + JS, sin build)                          │
│  accesible · responsive · SSE · sin acceso a Node            │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP/JSON + SSE
┌───────────────────────────▼──────────────────────────────────┐
│  src/viralclip/api/  (FastAPI)                               │
│  routes · security · sse · errors · observability            │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  src/viralclip/pipeline.py  (orquestador)                    │
│  parse → segment → score → select → hooks → subs → metadata  │
└──────┬───────────────┬───────────────┬───────────────────────┘
       │               │               │
┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────────┐
│ transcript  │ │ analyzer    │ │ hooks / subtitles│
│ platforms   │ │ (heurística)│ │ / platforms      │
└──────┬──────┘ └──────┬──────┘ └──────┬──────────┘
       │               │               │
       │        ┌──────▼──────┐        │
       │        │ llm/ollama  │        │
       │        │ (opcional)  │        │
       │        └─────────────┘        │
┌──────▼────────────────────────────────▼──────────────────────┐
│  src/viralclip/storage.py  (SQLite WAL)                      │
│  jobs · clips · settings · feature_flags · audit_log         │
└──────────────────────────────────────────────────────────────┘
```

### 2.4 Responsabilidades por módulo

| Módulo | Responsabilidad | No debe hacer |
|---|---|---|
| `config.py` | Leer variables de entorno y valores por defecto | Contener reglas de negocio |
| `models.py` | Modelos Pydantic de entrada, salida y API | Acceder a disco o red |
| `transcript.py` | Normalizar y validar transcripciones | Puntuar contenido |
| `analyzer.py` | Segmentar, puntuar y seleccionar candidatos | Redactar ganchos finales |
| `hooks.py` | Generar y validar ganchos | Inventar timestamps |
| `subtitles.py` | Partir líneas, resaltar y exportar SRT/VTT | Decidir qué clip elegir |
| `platforms.py` | Hashtags, títulos y descripciones por plataforma | Persistir datos |
| `pipeline.py` | Orquestar el flujo completo | Conocer HTTP o SQL |
| `llm/ollama.py` | Cliente Ollama con timeout, streaming y circuito | Bloquear la app si no está |
| `storage.py` | Persistencia SQLite y consultas parametrizadas | Lógica de análisis |
| `api/` | Contratos HTTP, seguridad, SSE y errores | Reglas de negocio profundas |
| `web/` | Interacción y presentación | Acceder a Node o al sistema |
| `desktop/` | Shell Electron seguro (fase 10) | Exponer APIs innecesarias |

### 2.5 Contratos de datos

#### Entrada: transcripción

Se aceptan tres formas equivalentes:

1. **Array raíz de segmentos** (formato mínimo).
2. **Objeto con `segments`** (formato recomendado).
3. **Salida verbose de Whisper** (objeto con `segments`, `language`, `duration`).

Cada segmento requiere `start`, `end` y `text`. `words` es opcional; si falta, los tiempos
se distribuyen proporcionalmente al número de palabras.

```json
{
  "language": "es",
  "duration": 123.4,
  "segments": [
    {
      "start": 0.0,
      "end": 3.2,
      "text": "Esto es lo que nadie te cuenta sobre vender.",
      "words": [
        {"word": "Esto", "start": 0.0, "end": 0.3},
        {"word": "es", "start": 0.3, "end": 0.5}
      ]
    }
  ]
}
```

Reglas de validación:

- `start >= 0`, `end > start`, `end <= 86 400` segundos.
- Timestamps aceptados como número de segundos o cadena `HH:MM:SS(.mmm)`.
- Segmentos ordenados y sin solapamientos negativos.
- Máximo 20 000 segmentos y 2 MB de payload por defecto.
- Texto no vacío; se rechazan rutas y binarios.

Esquema completo: `docs/contratos/transcripcion.schema.json`.

#### Salida: clips

```json
{
  "version": "1.0",
  "generated_at": "2026-11-09T12:00:00Z",
  "source": {"language": "es", "duration": 123.4, "segment_count": 42},
  "engine": {"name": "heuristic+ollama", "model": "llama3.2:latest", "degraded": false},
  "clips": [
    {
      "id": "clip_001",
      "rank": 1,
      "start_time": "00:00",
      "end_time": "00:45",
      "start_seconds": 0.0,
      "end_seconds": 45.0,
      "duration_seconds": 45.0,
      "platform": "tiktok",
      "hook": "Nadie te cuenta esto sobre vender",
      "title": "El error que frena tus ventas",
      "description": "Un consejo directo para vender más sin sonar corporativo.",
      "caption_text": "Esto es lo que nadie te cuenta sobre vender.",
      "hashtags": ["#ventas", "#emprendimiento", "#tips"],
      "score": 0.87,
      "reason": "Pregunta directa + dato + lenguaje conversacional",
      "keywords": ["vender", "nadie"],
      "subtitles": [
        {
          "index": 1,
          "start": 0.0,
          "end": 1.2,
          "text": "Esto es lo que",
          "words": [
            {"word": "Esto", "start": 0.0, "end": 0.3, "highlight": false}
          ]
        }
      ]
    }
  ]
}
```

Esquema completo: `docs/contratos/salida.schema.json`.

#### Exportación compatible con la especificación

Además del formato enriquecido, la app ofrece `GET /api/analyses/{id}/export?format=spec`
con exactamente la forma pedida en `SKILLS.md`:

```json
[
  {
    "start_time": "00:00",
    "end_time": "00:45",
    "hook": "Nadie te cuenta esto sobre vender",
    "caption_text": "Esto es lo que nadie te cuenta sobre vender.",
    "hashtags": ["#ventas", "#emprendimiento", "#tips"]
  }
]
```

### 2.6 API (borrador OpenAPI)

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/api/health` | Estado de la app, versión y disponibilidad de Ollama |
| `GET` | `/api/config` | Límites, plataformas y feature flags activos |
| `POST` | `/api/analyses` | Crear análisis desde JSON o archivo |
| `GET` | `/api/analyses` | Listar historial paginado |
| `GET` | `/api/analyses/{id}` | Estado y resultado del análisis |
| `DELETE` | `/api/analyses/{id}` | Borrar análisis y clips |
| `GET` | `/api/analyses/{id}/events` | Progreso por SSE |
| `GET` | `/api/analyses/{id}/export` | Exportar `json`, `spec`, `srt` o `vtt` |
| `GET` | `/api/analyses/{id}/clips/{clip_id}/srt` | Subtítulos SRT de un clip |
| `GET` | `/api/flags` | Listar feature flags |
| `PATCH` | `/api/flags` | Activar/desactivar un flag (local, `{name, enabled}`) |

Contrato completo: `docs/openapi.yaml`.

Códigos de error estables:

| Código | HTTP | Significado |
|---|---|---|
| `VC-1001` | 400 | Transcripción inválida |
| `VC-1002` | 413 | Payload demasiado grande |
| `VC-1003` | 422 | Parámetros fuera de rango |
| `VC-2001` | 404 | Análisis o clip no encontrado |
| `VC-2002` | 409 | Análisis todavía no listo para exportar |
| `VC-2003` | 403 | Función desactivada por un feature flag local |
| `VC-3001` | 401 | API key ausente o inválida |
| `VC-4001` | 502 | Ollama no disponible (degradado, no fatal) |
| `VC-5001` | 500 | Error interno |

### 2.7 Persistencia

SQLite en modo WAL con claves foráneas activas. Tablas:

- `jobs`: análisis, estado, entrada, resultado, motor, modelo, error y `request_id`.
- `clips`: clips normalizados para consulta y exportación.
- `settings`: preferencias locales.
- `feature_flags`: flags con dueño y expiración.
- `audit_log`: acciones destructivas y accesos sensibles.
- `evaluations`: resultados de evaluación de IA por modelo y prompt.

Índices en `jobs(created_at)`, `clips(job_id, rank)` y `audit_log(created_at)`.

### 2.8 Seguridad

- API key opcional (`VIRALCLIP_API_KEY`); si está definida, obligatoria en `/api/*`.
- CORS restringido a orígenes locales configurables.
- Validación de entrada en servidor con Pydantic y límites de tamaño.
- Sin rutas construidas con entrada del usuario; archivos con UUID.
- Consultas SQL parametrizadas; sin concatenación.
- Logs estructurados sin PII ni secretos; `request_id` por petición.
- Borrado de análisis elimina clips y metadatos asociados.
- Electron (fase 10) con `contextIsolation: true`, `nodeIntegration: false` y preload mínimo.

### 2.9 Observabilidad

- Middleware de `X-Request-ID` (genera o propaga).
- Logs JSON con `level`, `event`, `request_id`, `route`, `duration_ms`, `error_code`.
- Redacción de campos sensibles (`api_key`, `authorization`, `transcript` en logs de nivel INFO).
- `/api/health` con checks de base de datos y Ollama (con timeout corto).
- Errores con código estable, mensaje para usuario y detalle solo en logs.

### 2.10 Estrategia de pruebas

| Nivel | Herramienta | Cobertura |
|---|---|---|
| Unidad | `pytest` | Parser, analyzer, hooks, subtitles, platforms, storage |
| Contrato | `pytest` + JSON Schema | Entrada/salida válidas e inválidas |
| Integración | `fastapi.testclient` | Endpoints, errores, SSE básico |
| Accesibilidad | Revisión estática + `axe` (fase 9) | Teclado, etiquetas, contraste, foco |
| Carga | `k6` o `Locust` (fase 9) | p95/p99 y tasa de error |
| IA | Set de casos de oro (fase 9) | Formato, fidelidad, utilidad |

### 2.11 Estructura del repositorio

```
.
├── docs/
│   ├── fases/                 # planeación y cierre por fase
│   ├── adr/                   # decisiones de arquitectura
│   ├── contratos/             # JSON Schemas
│   ├── openapi.yaml           # borrador de contrato HTTP
│   ├── manual-usuario.md
│   ├── runbook.md
│   └── seguridad.md
├── src/viralclip/
│   ├── api/
│   ├── llm/
│   ├── config.py
│   ├── models.py
│   ├── transcript.py
│   ├── analyzer.py
│   ├── hooks.py
│   ├── subtitles.py
│   ├── platforms.py
│   ├── pipeline.py
│   ├── storage.py
│   └── cli.py
├── web/
├── desktop/
├── tests/
├── scripts/
├── data/
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── README.md
└── CHANGELOG.md
```

### 2.12 Dependencias

Producción: `fastapi`, `uvicorn[standard]`, `httpx`, `python-multipart`.
Desarrollo: `pytest`, `pytest-cov`, `ruff`.
Sin dependencias de NLP pesadas en el MVP: el análisis léxico usa listas propias en español.

### 2.13 ADRs

| ADR | Decisión |
|---|---|
| [ADR-001](../adr/ADR-001-python-fastapi.md) | Python 3.11+ y FastAPI para el backend |
| [ADR-002](../adr/ADR-002-frontend-web-sin-build.md) | Frontend web sin build (HTML/CSS/JS) |
| [ADR-003](../adr/ADR-003-sqlite-local.md) | SQLite local en modo WAL |
| [ADR-004](../adr/ADR-004-ollama-opcional.md) | Ollama opcional con fallback heurístico |
| [ADR-005](../adr/ADR-005-sse-progreso.md) | SSE para progreso unidireccional |
| [ADR-006](../adr/ADR-006-contrato-salida.md) | Contrato de salida versionado + export spec |
| [ADR-007](../adr/ADR-007-local-first.md) | Local-first y privacidad por defecto |

### 2.14 Riesgos arquitectónicos

| Riesgo | Mitigación |
|---|---|
| Acoplar el núcleo a FastAPI | El pipeline recibe y devuelve modelos, sin HTTP |
| Crecimiento del frontend sin build | Módulos ES nativos y CSS con variables |
| SQLite bloqueado por escrituras concurrentes | WAL, transacciones cortas, un proceso de escritura |
| Ollama lento o colgado | Timeout, cancelación y circuit breaker |
| Contrato de salida inestable | Versión `1.0` y pruebas de esquema |
| SSE bufferizado por proxies | `X-Accel-Buffering: no`, heartbeats y prueba local |

### 2.15 Criterios de aceptación de la fase

- [x] Mapa de componentes con responsabilidades y límites.
- [x] Stack y dependencias justificados con ADRs.
- [x] Contrato de entrada versionado y validable.
- [x] Contrato de salida versionado y export compatible con la especificación.
- [x] Borrador OpenAPI con endpoints, errores y límites.
- [x] Modelo de persistencia y estrategia de seguridad/observabilidad.
- [x] Estrategia de pruebas por nivel.
- [x] Estructura de repositorio y configuración base.

### 2.16 Actividades realizadas

1. Revisión de las decisiones de la Fase 0.
2. Diseño del monolito modular y del pipeline.
3. Definición de contratos JSON de entrada y salida.
4. Borrador OpenAPI con códigos de error estables.
5. Diseño del esquema SQLite y de la estrategia de seguridad.
6. Redacción de 7 ADRs.
7. Creación de la estructura de carpetas, `pyproject.toml`, requirements y `.env.example`.

### 2.17 Evidencia

- `docs/fases/fase-01-arquitectura.md` (este documento).
- `docs/adr/ADR-001…007`.
- `docs/contratos/transcripcion.schema.json`.
- `docs/contratos/salida.schema.json`.
- `docs/openapi.yaml`.
- `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `.env.example`, `.gitignore`.
- `README.md` inicial y `docs/fases/README.md`.

---

## 3. Cierre de fase

### 3.1 Resultado

La arquitectura queda definida y es ejecutable: hay stack, módulos, contratos, API,
persistencia, seguridad, observabilidad y plan de pruebas. No se implementó lógica de
negocio todavía.

### 3.2 Decisiones clave registradas

- Monolito modular Python + FastAPI, frontend sin build y SQLite local.
- Ollama opcional con degradación a heurísticas.
- SSE para progreso; sin WebSockets en el MVP.
- Salida enriquecida `v1.0` y exportación `spec` compatible con `SKILLS.md`.
- Local-first: sin nube, sin telemetría externa.

### 3.3 Deuda consciente

- El OpenAPI es un borrador; en la Fase 6 se generará desde FastAPI y se validará.
- El empaquetado de escritorio se difiere a la Fase 10.
- La evaluación de IA con casos de oro se difiere a la Fase 9.
- No se instala `spacy`/`nltk`: el MVP usa léxicos propios y el LLM opcional.

### 3.4 Handoff a la Fase 2

La Fase 2 implementará:

- modelos Pydantic de entrada/salida,
- parser y normalizador de transcripciones,
- validaciones y errores `VC-1001`/`VC-1002`,
- pruebas unitarias y de contrato,
- ejemplos/fixtures de transcripción.

### 3.5 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 2 — Ingesta y validación
de transcripciones**.
