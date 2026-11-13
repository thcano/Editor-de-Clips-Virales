# Fase 9 — Calidad: E2E, carga, accesibilidad y evaluación IA

> **Proyecto:** Editor de Clips Virales
> **Fase:** 9 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Entradas:** API/UI (Fases 6–8), pipeline y ganchos (Fases 3–5), tabla `evaluations`

---

## 1. Resumen ejecutivo

Esta fase mide la calidad del producto, no solo que compile: valida el flujo completo en un
navegador real, audita la accesibilidad con `axe-core`, somete la API a una carga
controlada y evalúa la calidad de los ganchos con un set de oro determinista y un juez LLM
opcional.

Las tres piezas son reproducibles y locales. Las pruebas E2E y la auditoría `axe` se
ejecutan con Playwright y se omiten limpiamente si el navegador no está instalado. La carga
usa un script `httpx` propio, sin dependencias nuevas. La evaluación IA guarda sus
resultados en la tabla `evaluations` ya existente.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Implementar y probar:

- E2E con Playwright sobre el flujo de carga, análisis, detalle, exportaciones y flags;
- auditoría de accesibilidad con `axe-core` en las vistas principales;
- script de carga asíncrono con percentiles y umbrales;
- set de oro de transcripciones y ganchos esperados;
- métricas deterministas de calidad (formato, fidelidad, utilidad);
- juez LLM opcional con Ollama y validación de su respuesta;
- persistencia y consulta de evaluaciones en SQLite;
- comandos y documentación de calidad.

### 2.2 Alcance

#### Incluye

- `tests/e2e/conftest.py`, `tests/e2e/test_flujo.py`, `tests/e2e/test_accesibilidad.py`
- `scripts/load_test.py`
- `src/viralclip/evaluation.py`
- `scripts/evaluate_hooks.py`
- `docs/evaluacion/casos-oro.json`
- `Storage.save_evaluation()` y `Storage.list_evaluations()`
- `tests/test_evaluation.py`
- dependencias de desarrollo: `playwright`, `axe-playwright-python`
- `docs/fases/fase-09-calidad.md` y actualización de índices

#### No incluye

- Renderizado o corte de video.
- Pruebas de carga distribuidas o en la nube.
- Evaluación humana a gran escala.
- Juez LLM obligatorio: el set de oro debe pasar sin Ollama.
- Multiusuario, roles o autenticación avanzada.
- Empaquetado de escritorio (Fase 10).

### 2.3 E2E con Playwright

Escenarios:

| Escenario | Validación |
|---|---|
| Carga inicial | `h1`, enlace “Saltar al contenido”, formulario e historial visibles |
| Ejemplo y análisis | Cargar ejemplo, enviar, esperar tarjetas de clips |
| Detalle de clip | Gancho, tiempos, texto, hashtags y score visibles |
| Copia | Botón “Copiar gancho” responde sin error |
| Ajustes y flags | Abrir diálogo, ver `export_srt` y `sse_progress`, alternar |
| Exportaciones | SRT/VTT se ocultan al apagar `export_srt` y reaparecen al encender |
| Historial | Abrir y borrar un análisis |

Infraestructura:

- `uvicorn` en un hilo con SQLite temporal y `llm_enabled=False`.
- Chromium headless; el fixture omite la prueba si Playwright o el navegador no están.
- La app se sirve en un puerto libre asignado por el sistema.
- Se espera por texto/estado, no por `sleep` fijos.

### 2.4 Accesibilidad

- `axe-core` sobre `/` con las reglas WCAG 2.2 A/AA.
- Cero violaciones `critical` o `serious`.
- Revisión de teclado: skip link, foco en el diálogo, cierre con `Escape`.
- Comprobaciones ya cubiertas: etiquetas, IDs únicos, `aria-live`, contraste y
  `prefers-reduced-motion`.

### 2.5 Carga

`scripts/load_test.py`:

- arranca la app en un hilo con SQLite temporal (o usa `--base-url`);
- ejecuta `N` análisis con concurrencia `C`;
- mide latencia de `POST /api/analyses` y del ciclo hasta `done`;
- calcula p50, p95, p99, media y tasa de error;
- imprime un resumen legible y devuelve código de salida distinto de cero si falla un
  umbral.

Umbrales por defecto:

| Métrica | Umbral |
|---|---|
| Tasa de error | < 1 % |
| p95 de `POST /api/analyses` | < 1 000 ms |
| p95 del ciclo completo | < 5 000 ms |
| peticiones por defecto | 30 |
| concurrencia por defecto | 5 |

### 2.6 Evaluación de ganchos

Set de oro (`docs/evaluacion/casos-oro.json`) con:

- `case_id`, `descripcion`, `transcript`, `platform`, parámetros y expectativas:
  - palabras clave que el gancho debería reflejar,
  - número máximo de palabras,
  - presencia de metadatos y subtítulos.

Métricas deterministas por clip:

| Métrica | Regla |
|---|---|
| `hook_format` | 1–10 palabras y ≤ 120 caracteres |
| `hook_fidelity` | comparte al menos una palabra clave con el candidato; no inventa cifras |
| `hook_not_corporate` | no usa lenguaje corporativo vetado |
| `hook_unique` | sin ganchos duplicados en el mismo análisis |
| `metadata_complete` | título, descripción, caption y 1–12 hashtags |
| `subtitles_ok` | líneas de 1–5 palabras y tiempos crecientes |
| `timestamps_ok` | `start < end` y dentro de la duración de la transcripción |

Puntuación: promedio ponderado de las métricas; `passed` si ≥ 0,8 y no hay fallo crítico
de formato o fidelidad.

Juez LLM opcional (`--judge`):

- pide a Ollama una puntuación 1–5 de claridad, curiosidad y fidelidad;
- valida el JSON y cae a “no evaluado” si el modelo falla;
- nunca cambia el resultado determinista ni los timestamps;
- guarda `model`, `prompt_version`, `case_id`, `score`, `passed` y `detail_json`.

### 2.7 Persistencia de evaluaciones

`Storage.save_evaluation(...)` inserta una fila en `evaluations`.
`Storage.list_evaluations(limit=...)` devuelve las más recientes con `detail_json`
deserializado de forma segura.

### 2.8 Actividades

1. Documentar esta planeación.
2. Añadir dependencias de desarrollo y verificar Playwright/Chromium.
3. Implementar `evaluation.py` con métricas y juez opcional.
4. Añadir métodos de evaluación a `Storage`.
5. Crear el set de oro y `scripts/evaluate_hooks.py`.
6. Crear `scripts/load_test.py`.
7. Crear pruebas E2E y de accesibilidad con Playwright + axe.
8. Escribir `tests/test_evaluation.py` y pruebas de almacenamiento.
9. Ejecutar suite, cobertura, `ruff`, E2E, carga y evaluación.
10. Documentar cierre, deuda y handoff a la Fase 10.

### 2.9 Criterios de aceptación

- [x] El flujo completo funciona en Chromium real.
- [x] `axe` no reporta violaciones `critical` ni `serious`.
- [x] El diálogo de ajustes y los flags funcionan con teclado.
- [x] La carga cumple los umbrales por defecto.
- [x] El set de oro pasa sin Ollama.
- [x] El juez LLM es opcional, valida su respuesta y no altera timestamps.
- [x] Las evaluaciones se persisten y se consultan.
- [x] Las pruebas E2E se omiten limpiamente sin navegador.
- [x] `pytest`, `ruff` y `node --check` pasan.

### 2.10 Riesgos

| Riesgo | Mitigación |
|---|---|
| Chromium no instalable | Omitir E2E con mensaje claro y mantener el resto de la suite |
| Pruebas E2E frágiles | Esperas por estado/texto, no `sleep` fijos |
| `axe` con falsos positivos | Revisar reglas y documentar exclusiones justificadas |
| Carga satura el proceso | Valores por defecto bajos y `BackgroundTasks` acotadas |
| Juez LLM no determinista | Métricas deterministas como fuente de verdad; juez opcional |
| Base sin tabla `evaluations` | Ya existe desde la Fase 6; migración no necesaria |
| Puertos ocupados | Puerto libre asignado por el sistema |

### 2.11 Evidencia esperada

- Archivos E2E, carga, evaluación y set de oro.
- Resultados de `pytest`, cobertura, `ruff`, `node --check`, E2E, carga y evaluación.
- Documento de cierre con umbrales y deuda consciente.

---

## 3. Cierre de fase

### 3.1 Resultado

La fase añadió una capa de calidad reproducible y local:

- **E2E reales** con Playwright + Chromium sobre el flujo completo: carga del ejemplo,
  análisis, tarjetas de clip, detalle, exportaciones, flags en Ajustes e historial.
- **Accesibilidad** con `axe-core`: cero violaciones `critical`/`serious`, enlace de salto,
  foco inicial en el diálogo y cierre con `Escape`.
- **Carga** con un script `httpx` asíncrono propio, sin dependencias nuevas, con percentiles
  p50/p95/p99 y umbrales configurables.
- **Evaluación de ganchos** con un set de oro de 3 casos y 9 métricas deterministas; el
  set pasa sin Ollama.
- **Juez LLM opcional** con Ollama, respuesta JSON validada y puntuación normalizada; no
  altera el resultado determinista ni los timestamps.
- **Persistencia** de evaluaciones en la tabla `evaluations` con `save_evaluation()` y
  `list_evaluations()`.
- **Bug real corregido:** si el análisis terminaba antes de abrir el detalle, el historial
  quedaba desactualizado; `app.js` ahora refresca el historial tras `openDetail`.

### 3.2 Evidencia

Código:

- `src/viralclip/evaluation.py` (métricas deterministas, `run_case`, `judge_hook`, `summarize`)
- `src/viralclip/llm/prompts.py` (`JUDGE_SYSTEM_PROMPT`, `build_judge_prompt`, `parse_judge_response`)
- `src/viralclip/storage.py` (`save_evaluation()`, `list_evaluations()`)
- `src/viralclip/web/app.js` (refresco de historial tras el detalle)
- `scripts/evaluate_hooks.py` (CLI del set de oro, juez y persistencia)
- `scripts/load_test.py` (carga asíncrona con umbrales)
- `docs/evaluacion/casos-oro.json` (3 casos de oro)
- `tests/e2e/conftest.py`, `tests/e2e/test_flujo.py`, `tests/e2e/test_accesibilidad.py`
- `tests/test_evaluation.py`
- `pyproject.toml` y `requirements-dev.txt` (`playwright`, `axe-playwright-python`)

Pruebas:

- `tests/test_evaluation.py`: 9 pruebas (formato, fidelidad, metadatos, subtítulos, tiempos,
  resultado vacío, parseo del juez, resumen, set de oro y persistencia).
- `tests/e2e/test_flujo.py`: 3 escenarios de flujo, flags e historial.
- `tests/e2e/test_accesibilidad.py`: auditoría `axe` y teclado del diálogo.

Comandos y resultados:

```text
$ python -m pytest -o addopts="" tests/e2e -q
5 passed, 1 warning

$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
TOTAL  2033 stmts  148 miss  576 branch  98 partial  90% cover
241 passed, 1 warning

$ python -m ruff check src tests scripts
All checks passed!

$ node --check src/viralclip/web/app.js
(sin errores de sintaxis)
```

Carga (`scripts/load_test.py`, 30 peticiones, concurrencia 5):

```text
Tiempo total:    0.83 s
Peticiones:      30
Errores:         0 (0.0%)
POST p50/p95:    23.0 / 61.8 ms
Ciclo  p50/p95:  111.9 / 166.0 ms
Ciclo  p99:      194.9 ms
Resultado:       OK
```

Evaluación determinista (`scripts/evaluate_hooks.py`):

```text
Caso                      Score Estado   Fallos
-----------------------------------------------
ventas-preguntar          1.000 OK       -
fitness-grasa             1.000 OK       -
productividad-miedo       1.000 OK       -

Resumen: 3/3 aprobados · media 1.000 · mínimo 1.000
```

Evaluación con juez Ollama (`--judge --persist`, `llama3.2:latest`):

```text
ventas-preguntar          1.000 OK       -
  juez: clarity=5.0 curiosity=3.0 fidelity=5.0 score=0.8667
fitness-grasa             1.000 OK       -
  juez: clarity=4.0 curiosity=5.0 fidelity=5.0 score=0.9333
productividad-miedo       1.000 OK       -
  juez: clarity=3.0 curiosity=5.0 fidelity=4.0 score=0.8

Resumen: 3/3 aprobados · media 1.000 · mínimo 1.000
Evaluaciones guardadas en SQLite
```

Las 3 filas se recuperan con `list_evaluations()` incluyendo `model=llama3.2:latest`,
`prompt_version=judge-v1` y el detalle del juez.

### 3.3 Criterios de aceptación

- [x] El flujo completo funciona en Chromium real.
- [x] `axe` no reporta violaciones `critical` ni `serious`.
- [x] El diálogo de ajustes y los flags funcionan con teclado.
- [x] La carga cumple los umbrales por defecto.
- [x] El set de oro pasa sin Ollama.
- [x] El juez LLM es opcional, valida su respuesta y no altera timestamps.
- [x] Las evaluaciones se persisten y se consultan.
- [x] Las pruebas E2E se omiten limpiamente sin navegador.
- [x] `pytest`, `ruff` y `node --check` pasan.

### 3.4 Deuda consciente

- Las E2E requieren Playwright y Chromium instalados; sin navegador se omiten (no fallan).
  No están en un pipeline de CI porque el proyecto es local-first.
- La auditoría `axe` cubre la vista inicial `/`; no audita cada estado dinámico del detalle.
- La carga usa datos de ejemplo y un solo proceso; no mide concurrencia distribuida ni
  saturación real de disco.
- El juez LLM es no determinista y puede variar entre modelos o ejecuciones; por eso el
  resultado determinista es la fuente de verdad y el juez solo informa.
- El set de oro tiene 3 casos; es una base sólida pero no una muestra representativa de
  todos los dominios.
- `expected_keywords` exige que al menos un gancho contenga una palabra esperada; es una
  comprobación gruesa, no una medida semántica.

### 3.5 Handoff a la Fase 10

La Fase 10 cerrará la documentación y el empaquetado de escritorio:

- manual de usuario y guía de operación;
- documentación de API y contratos finales;
- empaquetado o lanzador de escritorio para uso local;
- revisión final de `README`, `SKILLS.md` y estructura del repositorio;
- verificación integral y criterios de entrega.

### 3.6 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 10 — Documentación final,
manual y escritorio**.
