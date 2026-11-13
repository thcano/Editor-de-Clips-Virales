# Fase 5 — Integración con Ollama (streaming, cancelación y degradación)

> **Proyecto:** Editor de Clips Virales
> **Fase:** 5 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Entradas:** `ClipCandidate` y pipeline (Fases 3–4), Ollama local

---

## 1. Resumen ejecutivo

Esta fase integra **Ollama** como motor opcional para redactar ganchos con un LLM local.
La app sigue funcionando sin Ollama: el pipeline detecta el servicio, usa el modelo
configurado cuando está disponible y, ante cualquier fallo, cae al generador heurístico
con `engine.degraded = true` y un mensaje accionable.

El LLM **nunca inventa timestamps**: solo recibe texto ya validado y devuelve un gancho.
Los tiempos, subtítulos y metadatos siguen saliendo del núcleo determinista.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Implementar y probar:

- cliente HTTP de Ollama con `httpx`,
- health check con timeout corto y verificación de modelo,
- generación no streaming y streaming NDJSON,
- cancelación segura del stream,
- timeout, reintentos controlados y circuit breaker,
- prompts de ganchos con reglas de retención,
- parseo y validación de respuestas del LLM,
- integración en el pipeline con degradación clara,
- configuración por entorno.

### 2.2 Alcance

#### Incluye

- `src/viralclip/config.py`
- `src/viralclip/llm/__init__.py`
- `src/viralclip/llm/ollama.py`
- `src/viralclip/llm/prompts.py`
- integración en `src/viralclip/pipeline.py`
- `scripts/smoke_ollama.py`
- `tests/test_config.py`, `tests/test_ollama.py`, `tests/test_prompts.py`,
  `tests/test_pipeline_llm.py`

#### No incluye

- Chat conversacional en la UI (Fase 7).
- SSE de progreso (Fase 8).
- Persistencia de resultados (Fase 6).
- Fine-tuning o evaluación de calidad (Fase 9).

### 2.3 Cliente Ollama

| Operación | Endpoint | Uso |
|---|---|---|
| `health()` | `GET /api/tags` | Disponibilidad y modelos instalados |
| `generate()` | `POST /api/generate` (`stream=false`) | Gancho completo con timeout |
| `stream()` | `POST /api/generate` (`stream=true`) | Tokens incrementales NDJSON |
| `close()` | — | Liberar el cliente HTTP |

Configuración:

- `OLLAMA_BASE_URL` (por defecto `http://127.0.0.1:11434`).
- `OLLAMA_MODEL` (por defecto `llama3.2:latest`).
- `VIRALCLIP_OLLAMA_TIMEOUT` (60 s) y `VIRALCLIP_OLLAMA_HEALTH_TIMEOUT` (2 s).
- `VIRALCLIP_LLM_ENABLED` (true).

### 2.4 Health check

- `GET /api/tags` con timeout de 2 s.
- Si no responde: `available=false` con mensaje “Ollama no responde”.
- Si no hay modelos: mensaje “no hay modelos instalados”.
- Si el modelo configurado no está: mensaje con `ollama pull <modelo>`.
- La app **no se bloquea**: el pipeline usa heurísticas.

### 2.5 Streaming y cancelación

- `stream()` usa `httpx.Client.stream()` y lee líneas NDJSON.
- Cada línea aporta `response`; `done=true` cierra el stream.
- El consumidor puede detener la iteración o llamar `close()` al generador; el contexto
  `with` cierra la conexión y libera recursos.
- El timeout aplica al stream completo.
- Los errores de red se convierten en `OllamaUnavailableError` (`VC-4001`).

### 2.6 Circuit breaker

- Estado en memoria por cliente: `failures`, `open_until`.
- Tras **3 fallos consecutivos**, el circuito se abre durante **60 s**.
- Con el circuito abierto, `generate()`/`stream()` fallan rápido sin llamar a Ollama.
- Un éxito reinicia el contador y cierra el circuito.
- El reloj es inyectable para pruebas.

### 2.7 Prompts y guardrails

Prompt de sistema:

> Eres un guionista experto en clips virales para TikTok, Reels y YouTube Shorts.
> Escribes ganchos conversacionales, directos y sin lenguaje corporativo.

Prompt de usuario:

- Plataforma y tono.
- Texto del clip (máximo 1 500 caracteres).
- Palabras clave.
- Reglas: ≤ 10 palabras, sin inventar datos, sin comillas, una sola línea.
- Respuesta esperada: solo el gancho.

Parseo:

- Tomar la primera línea no vacía.
- Quitar viñetas, etiquetas (`Gancho:`) y comillas.
- Validar con `is_valid_hook` (≤ 10 palabras, ≤ 120 caracteres, sin lenguaje corporativo).
- Si no valida, se usa el gancho heurístico.

### 2.8 Integración en el pipeline

```text
analyze(use_llm=True)
  → settings.llm_enabled?
      no → heurístico (degraded=false)
      sí → client.health()
          no disponible → heurístico (degraded=true, notes con instrucciones)
          disponible → por candidato:
              generate(prompt) → parse → validar
              válido → gancho LLM
              inválido/error → gancho heurístico
          ¿algún gancho LLM? → engine=heuristic+ollama, degraded=false
          ninguno → engine=heuristic, degraded=true
```

- `build_clip()` acepta un `hook` opcional para inyectar el gancho elegido.
- El LLM no toca tiempos, subtítulos, hashtags ni score.
- `use_llm=False` no llama a Ollama y marca `degraded=false` (decisión explícita).

### 2.9 Actividades

1. Añadir `OllamaUnavailableError` con código `VC-4001`.
2. Implementar configuración por entorno.
3. Implementar cliente Ollama, health, generate, stream, cancelación y circuito.
4. Implementar prompts y parseo.
5. Integrar en el pipeline con degradación.
6. Escribir pruebas con `httpx.MockTransport` y clientes falsos.
7. Ejecutar smoke test real contra `llama3.2:latest`.
8. Ejecutar `pytest`, cobertura y `ruff`; documentar cierre.

### 2.10 Criterios de aceptación

- [ ] La app funciona sin Ollama y explica cómo instalarlo.
- [ ] El streaming se puede detener sin dejar procesos huérfanos.
- [ ] El modelo y el endpoint son configurables.
- [ ] El circuito se abre tras 3 fallos y se recupera tras el cooldown.
- [ ] Los ganchos del LLM se validan y, si fallan, se usa el heurístico.
- [ ] `engine` refleja el motor real y el estado de degradación.
- [ ] Los timestamps no cambian por usar LLM.
- [ ] Las pruebas no dependen del servicio real.
- [ ] `pytest` pasa y `ruff` no reporta errores.

### 2.11 Riesgos

| Riesgo | Mitigación |
|---|---|
| Ollama lento o colgado | Timeout + circuit breaker |
| Modelo no instalado | Health check con mensaje `ollama pull` |
| Respuesta del LLM inválida | Parseo + `is_valid_hook` + fallback |
| Alucinaciones de datos | El prompt prohíbe inventar; el texto base manda |
| Stream sin cierre | Context manager + cancelación del generador |
| Tests frágiles por servicio real | `MockTransport` y clientes falsos |
| Datos enviados fuera del equipo | Ollama local; sin nube |

### 2.12 Evidencia esperada

- Código en `src/viralclip/llm/`, `config.py`, `pipeline.py`.
- Pruebas y smoke test.
- Resultados de `pytest`, cobertura, `ruff` y smoke real.

---

## 3. Cierre de fase

### 3.1 Resultado

Ollama queda integrado como motor opcional de ganchos:

- configuración por entorno (`config.py`) con validación de booleanos, enteros y flotantes;
- cliente HTTP con `health()`, `generate()`, `stream()` NDJSON, cancelación y `close()`;
- circuit breaker con 3 fallos consecutivos y 60 s de cooldown, con reloj inyectable;
- prompts con guardrails y parseo que descarta respuestas inválidas o corporativas;
- pipeline que decide entre heurístico, `heuristic+ollama` y degradación explícita;
- `build_clip()` acepta un gancho ya validado sin tocar tiempos, subtítulos ni metadatos;
- smoke test real y pruebas con `httpx.MockTransport`, sin depender del servicio.

La app sigue funcionando sin Ollama: el health check devuelve un mensaje accionable con
`ollama pull <modelo>` y el pipeline usa el motor heurístico.

### 3.2 Evidencia

Código:

- `src/viralclip/config.py`
- `src/viralclip/errors.py` (`OllamaUnavailableError`, `VC-4001`)
- `src/viralclip/llm/__init__.py`
- `src/viralclip/llm/ollama.py`
- `src/viralclip/llm/prompts.py`
- `src/viralclip/pipeline.py`
- `scripts/smoke_ollama.py`
- `.env.example` (circuito y timeouts)

Pruebas:

- `tests/test_config.py`
- `tests/test_ollama.py`
- `tests/test_prompts.py`
- `tests/test_pipeline_llm.py`
- `tests/test_pipeline.py` (degradación explícita corregida)

Comandos y resultados:

```text
$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
170 passed in 0.98s
TOTAL  1305 stmts  111 miss  448 branch  81 partial  88% cover

$ python -m ruff check src tests scripts
All checks passed!
```

Smoke real con `llama3.2:latest`:

```text
Ollama: http://127.0.0.1:11434 / llama3.2:latest
health.available = True
health.message   = Ollama disponible
modelos          = ['llama3.2:latest', 'minimax-m3:cloud', 'tinyllama:1.1b']

[generate]
respuesta = '¿Sabes qué es lo que frena tus ventas?'
gancho    = '¿Sabes qué es lo que frena tus ventas?'

[stream]
primeros  = '¿Qué error frena tus ventas?'
```

Pipeline real sobre `tests/fixtures/transcripcion_viral.json`:

```text
engine: heuristic+ollama | model: llama3.2:latest | degraded: False
notes: 2 de 2 ganchos refinados con Ollama.
1. ¿Estás perdiendo dinero porque no preguntas?  [00:05 - 00:20]
2. Deja de hablar y escucha lo que realmente importa  [00:15 - 00:30]
```

### 3.3 Criterios de aceptación

- [x] La app funciona sin Ollama y explica cómo instalarlo.
- [x] El streaming se puede detener sin dejar procesos huérfanos (`generator.close()` +
  context manager).
- [x] El modelo y el endpoint son configurables.
- [x] El circuito se abre tras 3 fallos y se recupera tras el cooldown.
- [x] Los ganchos del LLM se validan y, si fallan, se usa el heurístico.
- [x] `engine` refleja el motor real y el estado de degradación.
- [x] Los timestamps no cambian por usar LLM.
- [x] Las pruebas no dependen del servicio real.
- [x] `pytest` pasa (170 pruebas) y `ruff` no reporta errores.

### 3.4 Deuda consciente

- El LLM es no determinista: puede devolver un gancho inválido y el pipeline cae al
  heurístico. La tasa de aceptación se medirá con casos de oro en la Fase 9.
- `stream()` está implementado y probado, pero el pipeline usa `generate()`; el consumo
  incremental se aprovechará en la Fase 8 (SSE).
- No hay reintentos con backoff: el circuit breaker evita insistir y el fallback cubre la
  disponibilidad.
- La carga de `.env` se resolverá al montar la API (Fase 6); por ahora `Settings` lee el
  entorno del proceso.
- La evaluación de calidad de prompts y modelos queda para la Fase 9.

### 3.5 Handoff a la Fase 6

La Fase 6 construirá sobre este cliente:

- persistencia SQLite (jobs, clips, settings, flags, auditoría),
- API FastAPI con los endpoints del borrador OpenAPI,
- traducción de errores `VC-xxxx` a respuestas HTTP,
- `/api/health` con el estado de Ollama,
- inyección de `Settings` y del cliente en la capa API.

### 3.6 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 6 — Persistencia SQLite
y API FastAPI**.
