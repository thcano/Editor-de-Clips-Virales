# Fase 8 — SSE, feature flags e integraciones

> **Proyecto:** Editor de Clips Virales
> **Fase:** 8 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Entradas:** API y UI (Fases 6–7), flags en SQLite, cliente Ollama con `stream()`

---

## 1. Resumen ejecutivo

Esta fase endurece el tiempo real y conecta los **feature flags** con la experiencia de
uso. El endpoint SSE pasa de un sondeo mínimo a un stream con identificadores de evento,
`Last-Event-ID`, heartbeats y reconexión; el trabajo publica **progreso por etapas**; y la
UI elige SSE o sondeo según el flag `sse_progress`, ocultando las exportaciones SRT/VTT
cuando `export_srt` está desactivado.

El backend sigue siendo local-first y la UI mantiene un fallback a sondeo cuando SSE no
está disponible o se usa API key.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Implementar y probar:

- progreso real por etapas persistido en `jobs`;
- eventos SSE con `id`, `event`, `data`, `retry` y heartbeats;
- soporte de `Last-Event-ID` para reconexión;
- cierre del stream en estado terminal y timeout de seguridad;
- gating de exportaciones SRT/VTT por `export_srt` (`VC-2003`);
- panel de feature flags en la UI con `PATCH /api/flags`;
- elección automática SSE/sondeo según `sse_progress` y API key;
- fallback a sondeo ante errores de SSE;
- pruebas de SSE, progreso, flags y UI.

### 2.2 Alcance

#### Incluye

- `src/viralclip/errors.py` (`VC-2003`, `FeatureDisabledError`)
- `src/viralclip/storage.py` (columnas `progress` y `stage`, migración, `update_progress`)
- `src/viralclip/pipeline.py` (callback `on_stage`)
- `src/viralclip/api/jobs.py` (reporte de etapas)
- `src/viralclip/api/routes.py` (SSE robusto, gating de flags)
- `src/viralclip/api/schemas.py` (`stage`)
- `src/viralclip/web/index.html`, `styles.css`, `app.js` (flags y SSE)
- `tests/test_sse.py` o ampliación de `tests/test_api.py`, `tests/test_storage.py`,
  `tests/test_jobs.py`, `tests/test_pipeline_llm.py`
- `docs/openapi.yaml`, `docs/fases/fase-01-arquitectura.md`

#### No incluye

- WebSockets.
- Cola persistente con reintentos de trabajos.
- Progreso token a token de Ollama en la UI.
- Pruebas E2E con navegador real (Fase 9).
- Multiusuario o autorización por roles.

### 2.3 SSE

Eventos emitidos:

| Evento | Cuándo | Datos |
|---|---|---|
| `progress` | Cambia estado, progreso o etapa | `id`, `status`, `progress`, `stage`, `updated_at` |
| `done` | El trabajo terminó correctamente | Igual que `progress` |
| `error` | El trabajo falló | Igual que `progress` |

Formato:

```text
retry: 3000

id: 1
event: progress
data: {"id":"...","status":"running","progress":30,"stage":"candidatos","updated_at":"..."}

: ping
```

- `id` es un contador por conexión; en reconexión arranca en `Last-Event-ID + 1`.
- `retry: 3000` indica al navegador esperar 3 s entre reconexiones.
- Heartbeat `: ping` cada 15 s si no hay cambios.
- El stream termina en `done`/`error` o tras 10 minutos (el cliente reconecta).
- Cabeceras: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

### 2.4 Progreso por etapas

| Etapa | Progreso | Momento |
|---|---|---|
| `queued` | 0 | Trabajo creado |
| `validando` | 5 | Inicio del trabajo |
| `preparando` | 10 | Pipeline arranca |
| `candidatos` | 40 | Candidatos detectados |
| `ganchos` | 75 | Motor y ganchos resueltos |
| `clips` | 90 | Subtítulos y metadatos listos |
| `done` | 100 | Resultado persistido |
| `error` | 100 | Fallo persistido |

El pipeline recibe un callback opcional `on_stage(progress, stage)` para no acoplarse a
SQLite. El trabajo lo usa para llamar a `Storage.update_progress`.

### 2.5 Feature flags

| Flag | Efecto |
|---|---|
| `export_srt` | Si está desactivado, la API devuelve `403 VC-2003` para SRT/VTT y la UI oculta esas descargas |
| `sse_progress` | Si está activo y no hay API key, la UI usa `EventSource`; si no, sondeo |

La UI muestra ambos flags en Ajustes, con descripción, y los actualiza con
`PATCH /api/flags`. Los cambios se aplican sin recargar la página.

### 2.6 Integración en la UI

- `loadConfig()` guarda los flags activos y aplica visibilidad.
- `loadFlags()` pinta los checkboxes de Ajustes.
- `watchAnalysis(id)` elige SSE o sondeo y cancela el watcher anterior.
- `EventSource` se cierra al terminar, al cerrar el detalle o al abrir otro análisis.
- Si SSE falla, se cae a sondeo sin intervención del usuario.
- Con API key configurada se usa sondeo (EventSource no admite cabeceras).

### 2.7 Actividades

1. Documentar la planeación.
2. Añadir `VC-2003` y `FeatureDisabledError`.
3. Migrar `jobs` con `progress` y `stage`; añadir `update_progress`.
4. Añadir `on_stage` al pipeline y reportar etapas desde el trabajo.
5. Reescribir el endpoint SSE con ids, heartbeat, `Last-Event-ID` y timeout.
6. Aplicar `export_srt` en las rutas de exportación.
7. Integrar flags y SSE en la UI.
8. Escribir pruebas y actualizar OpenAPI/errores.
9. Ejecutar suite, cobertura, `ruff`, `node --check` y smoke real.
10. Documentar el cierre y el handoff a la Fase 9.

### 2.8 Criterios de aceptación

- [ ] `GET /api/analyses/{id}` devuelve `progress` y `stage` reales.
- [ ] SSE emite `retry`, `id`, `event` y `data` válidos.
- [ ] `Last-Event-ID` continúa la numeración.
- [ ] El stream termina en `done`/`error` y envía heartbeats.
- [ ] `export_srt=false` bloquea SRT/VTT con `403 VC-2003`.
- [ ] La UI muestra y actualiza flags desde Ajustes.
- [ ] La UI usa SSE cuando está disponible y sondeo como fallback.
- [ ] Las exportaciones se ocultan cuando el flag está apagado.
- [ ] La migración de una base antigua añade las columnas sin perder datos.
- [ ] `pytest` pasa y `ruff` no reporta errores.

### 2.9 Riesgos

| Riesgo | Mitigación |
|---|---|
| Cliente que no reconecta | `retry: 3000` y fallback a sondeo |
| Stream colgado | Timeout de 10 minutos y cierre en terminal |
| Pérdida de eventos | Snapshot actual en cada conexión + `Last-Event-ID` |
| Base antigua sin columnas | Migración con `PRAGMA table_info` + `ALTER TABLE` |
| API key incompatible con EventSource | Sondeo automático cuando hay clave |
| Flags inconsistentes | `PATCH` + recarga de `/api/config` |
| Bloqueo del event loop | Consultas SQLite rápidas y `sleep(0.5)` |

### 2.10 Evidencia esperada

- Cambios en backend, UI y pruebas.
- Resultados de `pytest`, cobertura, `ruff`, `node --check` y smoke real.
- OpenAPI y tabla de errores actualizados.

---

## 3. Cierre de fase

### 3.1 Resultado

El tiempo real y los feature flags quedaron integrados de extremo a extremo:

- `jobs` persiste `progress` y `stage`; una migración con `PRAGMA table_info` añade las
  columnas a bases creadas por versiones anteriores sin perder datos.
- El pipeline reporta avance real por etapas mediante `on_stage`, sin acoplarse a SQLite;
  el trabajo traduce cada etapa a `Storage.update_progress`.
- El endpoint SSE emite `retry: 3000`, `id` incremental, `event` (`progress`/`done`/
  `error`), `data` JSON compacto y heartbeats `: ping` cada 15 s.
- `Last-Event-ID` continúa la numeración tras una reconexión; el stream cierra en estado
  terminal o tras 10 minutos de seguridad.
- `export_srt=false` bloquea SRT/VTT con `403 VC-2003` en la exportación general y en el
  SRT por clip.
- La UI muestra los flags en Ajustes, los actualiza con `PATCH /api/flags`, usa SSE cuando
  `sse_progress` está activo y no hay API key, y cae a sondeo ante cualquier fallo.
- Las descargas SRT/VTT se ocultan cuando el flag está desactivado.

### 3.2 Evidencia

Código:

- `src/viralclip/errors.py` (`VC-2003`, `FeatureDisabledError`)
- `src/viralclip/storage.py` (`progress`/`stage`, `_migrate()`, `update_progress()`)
- `src/viralclip/pipeline.py` (`StageCallback`, `on_stage`)
- `src/viralclip/api/jobs.py` (reporte de etapas)
- `src/viralclip/api/routes.py` (SSE robusto, gating por flag)
- `src/viralclip/api/schemas.py` (`stage`)
- `src/viralclip/web/index.html` (panel de funciones)
- `src/viralclip/web/styles.css` (`[hidden]`, estilos de flags)
- `src/viralclip/web/app.js` (SSE/sondeo, progreso, gating de exportaciones)
- `docs/openapi.yaml` (SSE, `stage`, `403 VC-2003`)
- `docs/fases/fase-01-arquitectura.md` (tabla de errores)

Pruebas:

- `tests/test_api.py` (SSE, `Last-Event-ID`, progreso/etapa, gating `VC-2003`, formateador)
- `tests/test_storage.py` (`update_progress`, migración de base antigua, progreso terminal)
- `tests/test_jobs.py` (progreso y etapa en éxito/error)
- `tests/test_pipeline_llm.py` (etapas monótonas)
- `tests/test_web.py` (panel de flags, uso de SSE y fallback)

Comandos y resultados:

```text
$ python -m pytest -o addopts="" -q
227 passed, 1 warning

$ python -m ruff check src tests scripts
All checks passed!

$ node --check src/viralclip/web/app.js
(sin errores de sintaxis)

$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
TOTAL  1866 stmts  128 miss  530 branch  94 partial  90% cover
227 passed, 1 warning
```

La advertencia es de Starlette sobre `httpx`/`httpx2` en `TestClient`; no afecta la
aplicación.

Smoke con **uvicorn real** (no `TestClient`) en `127.0.0.1:8766` y SQLite temporal:

```text
root: 200 True True
js: 200 True True
post: 202
sse: 200 text/event-stream; charset=utf-8
sse retry: True
sse id: True
sse done: True
detail: done 100 done
flag off: 200
srt off: 403 VC-2003
clip srt off: 403 VC-2003
flag on: 200
srt on: 200 application/x-subrip
```

El smoke confirma el stream SSE con `retry` y numeración continuada desde
`Last-Event-ID`, el progreso/etapa final, y el bloqueo/restablecimiento de SRT mediante el
flag `export_srt`.

### 3.3 Criterios de aceptación

- [x] `GET /api/analyses/{id}` devuelve `progress` y `stage` reales.
- [x] SSE emite `retry`, `id`, `event` y `data` válidos.
- [x] `Last-Event-ID` continúa la numeración.
- [x] El stream termina en `done`/`error` y envía heartbeats.
- [x] `export_srt=false` bloquea SRT/VTT con `403 VC-2003`.
- [x] La UI muestra y actualiza flags desde Ajustes.
- [x] La UI usa SSE cuando está disponible y sondeo como fallback.
- [x] Las exportaciones se ocultan cuando el flag está apagado.
- [x] La migración de una base antigua añade las columnas sin perder datos.
- [x] `pytest` pasa (227 pruebas) y `ruff` no reporta errores.

### 3.4 Deuda consciente

- El progreso es por etapas gruesas; no refleja tokens individuales de Ollama ni el
  porcentaje exacto dentro de una etapa.
- El `id` de SSE es un contador por conexión, no un cursor persistente: tras reconectar se
  reenvía el snapshot actual, lo que evita perder el estado aunque puede repetir un evento.
- El timeout de 10 minutos cierra el stream y deja que el navegador reconecte; no hay
  reanudación de trabajos ni cola persistente.
- `sse_progress` solo controla la preferencia de la UI; el endpoint SSE sigue disponible
  para clientes que lo consuman directamente.
- Con API key configurada la UI usa sondeo porque `EventSource` no permite cabeceras
  personalizadas.
- Las pruebas E2E con navegador real, la auditoría automática de accesibilidad y la carga
  quedan para la Fase 9.

### 3.5 Handoff a la Fase 9

La Fase 9 se centrará en calidad:

- pruebas E2E con navegador real (Playwright) sobre el flujo completo;
- auditoría automática de accesibilidad (axe) y revisión de contraste;
- pruebas de carga con `k6` o `Locust` sobre la API y el SSE;
- set de casos de oro para evaluar ganchos del LLM (fidelidad, formato, utilidad);
- persistencia de evaluaciones en la tabla `evaluations`;
- umbrales de rendimiento y tasa de error documentados.

### 3.6 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 9 — Calidad: E2E, carga,
accesibilidad y evaluación IA**.
