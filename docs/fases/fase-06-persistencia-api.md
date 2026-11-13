# Fase 6 — Persistencia SQLite + API FastAPI

> **Proyecto:** Editor de Clips Virales
> **Fase:** 6 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Entradas:** pipeline `analyze()` (Fases 3–5), `Settings` y cliente Ollama (Fase 5)

---

## 1. Resumen ejecutivo

Esta fase convierte el núcleo de dominio en una aplicación local ejecutable: persiste los
análisis en **SQLite (WAL)** y los expone con una **API FastAPI** que respeta el contrato
`v1.0` y el borrador OpenAPI.

El análisis se ejecuta en segundo plano con `BackgroundTasks`, de modo que `POST
/api/analyses` responde `202` de inmediato y el cliente consulta el estado por `GET
/api/analyses/{id}` o por un stream SSE básico. Todos los errores del dominio se traducen
a códigos `VC-xxxx` estables con `request_id`, y la app funciona sin Ollama degradando el
motor a heurístico.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Implementar y probar:

- esquema SQLite con WAL, claves foráneas e índices;
- repositorio `Storage` con consultas parametrizadas y lock reentrante;
- trabajos de análisis persistidos y ejecutados en segundo plano;
- API FastAPI con health, config, analyses, export, flags y eventos;
- traducción de errores de dominio a respuestas HTTP;
- API key opcional, `X-Request-ID` y auditoría de acciones;
- pruebas de integración con `TestClient` y SQLite temporal.

### 2.2 Alcance

#### Incluye

- `src/viralclip/storage.py`
- `src/viralclip/api/__init__.py`
- `src/viralclip/api/app.py`
- `src/viralclip/api/routes.py`
- `src/viralclip/api/schemas.py`
- `src/viralclip/api/security.py`
- `src/viralclip/api/errors.py`
- `src/viralclip/api/jobs.py`
- nuevos errores `VC-2001`, `VC-2002`, `VC-3001` en `src/viralclip/errors.py`
- `tests/test_storage.py`, `tests/test_api.py`, `tests/test_jobs.py`, `tests/conftest.py`
- reconciliación de `docs/openapi.yaml` y de la tabla de errores de la Fase 1

#### No incluye

- Frontend HTML/CSS/JS (Fase 7).
- SSE avanzado con heartbeats, `Last-Event-ID` y reconexión (Fase 8).
- Evaluación de calidad del LLM (Fase 9).
- Empaquetado de escritorio (Fase 10).
- Renderizado o corte de video (fuera de alcance del proyecto).

### 2.3 Diseño de persistencia

Base local en `data/viralclip.db` con `journal_mode=WAL`, `foreign_keys=ON` y
`busy_timeout=5000`. Una conexión por proceso protegida con `threading.RLock`.

| Tabla | Contenido |
|---|---|
| `jobs` | Entrada, estado, parámetros, resultado JSON, motor, modelo, degradación, error y `request_id` |
| `clips` | Clips normalizados para consulta y exportación (FK a `jobs` con `ON DELETE CASCADE`) |
| `settings` | Preferencias locales clave/valor |
| `feature_flags` | Flags con dueño, expiración y descripción |
| `audit_log` | Acciones destructivas y accesos sensibles |
| `evaluations` | Reservada para la Fase 9 |

Índices: `jobs(created_at DESC)`, `clips(job_id, rank)` y `audit_log(created_at DESC)`.

Estados del trabajo: `queued → running → done | error`. Al arrancar, los trabajos
`queued`/`running` se marcan como `error` con `VC-5001` para no dejarlos colgados.

Flags por defecto: `export_srt` y `sse_progress`.

### 2.4 API

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/api/health` | Estado de la app, base de datos y Ollama |
| `GET` | `/api/config` | Límites, plataformas y flags activos |
| `POST` | `/api/analyses` | Encolar análisis (`202`, `events_url`) |
| `GET` | `/api/analyses` | Historial paginado (`limit`, `offset`) |
| `GET` | `/api/analyses/{id}` | Estado, motor, error y clips |
| `DELETE` | `/api/analyses/{id}` | Borrar análisis y clips (`204`) |
| `GET` | `/api/analyses/{id}/events` | SSE básico de progreso/estado final |
| `GET` | `/api/analyses/{id}/export` | Exportar `json`, `spec`, `srt` o `vtt` |
| `GET` | `/api/analyses/{id}/clips/{clip_id}/srt` | SRT de un clip |
| `GET` | `/api/flags` | Listar feature flags |
| `PATCH` | `/api/flags` | Activar/desactivar un flag |

Comportamiento:

- `POST /api/analyses` valida el tamaño del payload, normaliza la transcripción, crea el
  trabajo y encola `run_analysis_job`.
- `use_llm` viaja en el trabajo; el pipeline decide heurístico, `heuristic+ollama` o
  degradación.
- La exportación `json` devuelve el contrato completo; `spec` el formato mínimo de
  `SKILLS.md`; `srt`/`vtt` se descargan como adjuntos.
- Un trabajo sin resultado devuelve `409 VC-2002`.

### 2.5 Seguridad y observabilidad

- API key opcional: si `VIRALCLIP_API_KEY` está definida, todas las rutas `/api/*` exigen
  `X-API-Key` (comparación con `secrets.compare_digest`). Si está vacía, no se exige.
- `X-Request-ID`: se propaga el recibido o se genera uno; se devuelve en la respuesta y se
  incluye en los errores.
- Auditoría de `analysis.create`, `analysis.delete` y `flag.update`.
- CORS configurable por `VIRALCLIP_CORS_ORIGINS`.

### 2.6 Manejo de errores

| Código | HTTP | Origen |
|---|---|---|
| `VC-1001` | 400 | Transcripción inválida |
| `VC-1002` | 413 | Payload demasiado grande |
| `VC-1003` | 422 | Parámetros fuera de rango o validación |
| `VC-2001` | 404 | Análisis o clip no encontrado |
| `VC-2002` | 409 | Análisis no listo para exportar |
| `VC-3001` | 401 | API key ausente o inválida |
| `VC-4001` | 502 | Ollama no disponible (degradado, no fatal) |
| `VC-5001` | 500 | Error interno |

### 2.7 Actividades

1. Definir el esquema y el repositorio `Storage`.
2. Crear la capa API: esquemas, seguridad, errores, trabajos y rutas.
3. Cablear `create_app` con dependencias inyectables y ciclo de vida.
4. Reconciliar `docs/openapi.yaml` con la implementación.
5. Escribir pruebas de persistencia, API y trabajos.
6. Ejecutar suite, cobertura, `ruff` y smoke real con Ollama.
7. Documentar el cierre y el handoff a la Fase 7.

### 2.8 Criterios de aceptación

- [ ] El análisis se persiste y sobrevive a la consulta posterior.
- [ ] `POST /api/analyses` responde `202` y el trabajo termina en `done`.
- [ ] Los errores de dominio devuelven su `VC-xxxx` y `request_id`.
- [ ] La API key se exige solo cuando está configurada.
- [ ] El historial pagina correctamente y el borrado elimina los clips.
- [ ] La exportación `json`/`spec`/`srt`/`vtt` funciona.
- [ ] Un análisis pendiente devuelve `409 VC-2002`.
- [ ] `/api/health` refleja el estado de SQLite y Ollama.
- [ ] Los trabajos interrumpidos se marcan como error al reiniciar.
- [ ] `pytest` pasa y `ruff` no reporta errores.

### 2.9 Riesgos

| Riesgo | Mitigación |
|---|---|
| Escrituras concurrentes en SQLite | WAL, `busy_timeout` y lock reentrante |
| Trabajo colgado tras reinicio | `mark_interrupted_jobs()` al arrancar |
| Fuga de la API key | Comparación constante y clave opcional en local |
| Errores sin contexto | `request_id` en respuestas y auditoría |
| Resultado inválido en base | Validación Pydantic al leer (`result_for`) |
| Crecimiento de la base | Borrado con `ON DELETE CASCADE` |

### 2.10 Evidencia esperada

- Código en `src/viralclip/storage.py` y `src/viralclip/api/`.
- Pruebas de persistencia, API y trabajos.
- Resultados de `pytest`, cobertura, `ruff` y smoke real.

---

## 3. Cierre de fase

### 3.1 Resultado

La app ya es ejecutable de extremo a extremo sobre SQLite y FastAPI:

- `Storage` inicializa el esquema WAL, siembra flags y expone jobs, clips, settings,
  flags, auditoría y evaluaciones;
- `create_app` inyecta `Settings`, `Storage` y un `OllamaClient` opcional, propaga
  `X-Request-ID` y registra manejadores de error;
- `run_analysis_job` ejecuta el pipeline en segundo plano y guarda resultado o error;
- las rutas cubren health, config, analyses, export, flags y SSE básico;
- la API key es opcional y la auditoría registra las acciones destructivas;
- el contrato OpenAPI y la tabla de errores quedaron reconciliados.

### 3.2 Evidencia

Código:

- `src/viralclip/storage.py`
- `src/viralclip/api/__init__.py`
- `src/viralclip/api/app.py`
- `src/viralclip/api/routes.py`
- `src/viralclip/api/schemas.py`
- `src/viralclip/api/security.py`
- `src/viralclip/api/errors.py`
- `src/viralclip/api/jobs.py`
- `src/viralclip/errors.py` (`VC-2001`, `VC-2002`, `VC-3001`)
- `docs/openapi.yaml` (409, SRT por clip, `notes` del motor)
- `docs/fases/fase-01-arquitectura.md` (tabla de errores y `PATCH /api/flags`)

Pruebas:

- `tests/test_storage.py`
- `tests/test_api.py`
- `tests/test_jobs.py`
- `tests/conftest.py`

Comandos y resultados:

```text
$ python -m pytest -o addopts="" -q
209 passed, 1 warning in 11.09s

$ python -m ruff check src tests scripts
All checks passed!

$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
TOTAL  1793 stmts  123 miss  514 branch  93 partial  90% cover
209 passed, 1 warning in 9.96s
```

La advertencia es de Starlette sobre `httpx`/`httpx2` en `TestClient`; no afecta la
aplicación.

Smoke real con SQLite temporal y Ollama (`llama3.2:latest`):

```text
health: {'status': 'ok', 'version': '0.1.0', 'database': 'ok',
         'ollama': {'available': True, 'model': 'llama3.2:latest',
                    'message': 'Ollama disponible'}}
post: 202 {'id': '7c8caa3a-...', 'status': 'queued',
           'events_url': '/api/analyses/7c8caa3a-.../events'}
job: done {'name': 'heuristic', 'model': None, 'degraded': True,
           'notes': 'Ollama respondió, pero ningún gancho superó la validación; se usó el motor heurístico.'}
hooks: ['El dato que cambia todo sobre preguntar']
spec: 200 [{'start_time': '00:05', 'end_time': '00:20', ...}]
```

El caso real confirma la degradación esperada: el LLM respondió con un gancho inválido, el
pipeline cayó al heurístico y el trabajo quedó `done` con `degraded=True` en lugar de
fallar.

### 3.3 Criterios de aceptación

- [x] El análisis se persiste y sobrevive a la consulta posterior.
- [x] `POST /api/analyses` responde `202` y el trabajo termina en `done`.
- [x] Los errores de dominio devuelven su `VC-xxxx` y `request_id`.
- [x] La API key se exige solo cuando está configurada.
- [x] El historial pagina correctamente y el borrado elimina los clips.
- [x] La exportación `json`/`spec`/`srt`/`vtt` funciona.
- [x] Un análisis pendiente devuelve `409 VC-2002`.
- [x] `/api/health` refleja el estado de SQLite y Ollama.
- [x] Los trabajos interrumpidos se marcan como error al reiniciar.
- [x] `pytest` pasa (209 pruebas) y `ruff` no reporta errores.

### 3.4 Deuda consciente

- `BackgroundTasks` ejecuta el trabajo en el proceso del servidor: si el proceso muere, el
  trabajo se marca como error al reiniciar, pero no se reanuda. Una cola persistente con
  reintentos queda para una fase posterior si se necesita.
- El SSE es básico: estado actual y sondeo cada 0,5 s, sin heartbeats ni `Last-Event-ID`.
  La Fase 8 lo endurece.
- `progress` usa valores discretos (`queued=0`, `running=50`, `done=100`); el progreso real
  por etapa llegará con el SSE de la Fase 8.
- La carga automática de `.env` no está integrada; `Settings` lee el entorno del proceso.
  El arranque documentado usa variables de entorno o el gestor que se defina en la Fase 10.
- No hay autenticación multiusuario: la API key es una barrera local simple.
- La tabla `evaluations` existe pero aún no se usa (Fase 9).

### 3.5 Handoff a la Fase 7

La Fase 7 construirá sobre esta API:

- frontend sin build (HTML + CSS + módulos ES) servido por la app;
- formulario de carga de transcripción JSON y selección de plataforma;
- lista de análisis, detalle de clips y copia de ganchos/hashtags;
- descarga de exportaciones `json`/`spec`/`srt`/`vtt`;
- estados de carga, error y degradación visibles;
- accesibilidad WCAG 2.2 AA y diseño responsive.

### 3.6 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 7 — Frontend accesible y
responsive**.
