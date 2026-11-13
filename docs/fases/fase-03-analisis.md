# Fase 3 — Motor de análisis y ganchos

> **Proyecto:** Editor de Clips Virales
> **Fase:** 3 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Entradas:** `Transcript` normalizado (Fase 2), contrato de salida `v1.0`

---

## 1. Resumen ejecutivo

Esta fase convierte una transcripción normalizada en **candidatos de clip** ordenados por
potencial de retención, con una puntuación **explicable** y un **gancho** de menos de 10
palabras. El motor combina señales lingüísticas deterministas (preguntas, datos, emoción,
historia, consejo, polémica, ritmo) y deja preparada la interfaz para el refinamiento con
Ollama en la Fase 5.

La salida de esta fase es interna (`ClipCandidate`); la Fase 4 la convertirá en `Clip`
con subtítulos, título, descripción y hashtags.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Implementar y probar:

- segmentación de ventanas candidatas de 15–60 s,
- extracción de señales lingüísticas en español,
- puntuación 0–1 con motivo legible,
- selección y deduplicación de clips diversos,
- generación determinista de ganchos con validación de ≤ 10 palabras,
- extracción de palabras clave,
- pruebas unitarias de calidad y determinismo.

### 2.2 Alcance

#### Incluye

- `src/viralclip/lexicon.py`: léxicos y stopwords en español.
- `src/viralclip/analyzer.py`: ventanas, señales, scoring, selección y palabras clave.
- `src/viralclip/hooks.py`: generación y validación de ganchos.
- `tests/test_analyzer.py`, `tests/test_hooks.py`.
- Fixture `tests/fixtures/transcripcion_viral.json`.

#### No incluye

- Llamadas a Ollama (Fase 5).
- Subtítulos dinámicos (Fase 4).
- Títulos, descripciones y hashtags por plataforma (Fase 4).
- Persistencia y API (Fase 6).

### 2.3 Segmentación de candidatos

1. **Dividir segmentos largos** que excedan `max_duration` usando sus palabras.
2. **Construir bloques base** acumulando segmentos hasta `min_duration`, cerrando en
   límites naturales: fin de frase (`.!?`), pausa > 0,8 s o `max_duration`.
3. **Generar ventanas**:
   - cada bloque base dentro de `[min_duration, max_duration]`,
   - unión de 2–3 bloques consecutivos si no excede `max_duration`,
   - ventanas ancla que empiezan en cada límite natural y avanzan hasta `max_duration`.
4. **Deduplicar** por rango redondeado y por texto normalizado.
5. Si la transcripción es más corta que `min_duration`, devolver una ventana con todo el
   contenido.
6. Límite de seguridad: 3 000 ventanas y 2 000 anclas.

### 2.4 Señales lingüísticas

| Señal | Qué mide | Ejemplos |
|---|---|---|
| `question` | Pregunta directa o inicio interrogativo | `?`, `qué`, `cómo`, `por qué` |
| `curiosity` | Curiosidad o promesa de revelación | `nadie`, `secreto`, `error`, `verdad` |
| `numbers` | Datos y cifras | `80%`, `miles`, `millones`, `por ciento` |
| `emotion` | Carga emocional | `brutal`, `increíble`, `miedo`, `odio` |
| `story` | Marcadores narrativos | `cuando`, `de repente`, `resulta`, `un día` |
| `advice` | Consejo práctico | `tienes que`, `debes`, `el truco`, `deja de` |
| `controversy` | Opinión polémica | `polémico`, `mentira`, `te equivocas` |
| `density` | Ritmo conversacional (palabras/s) | objetivo ≈ 2,5 |
| `completeness` | Idea cerrada | termina en `.`, `!`, `?` |
| `keyword_density` | Densidad de contenido | proporción de palabras plenas |
| `filler` | Relleno (penaliza) | `eh`, `mmm`, `o sea`, `tipo` |
| `repetition` | Repetición (penaliza) | palabras únicas / totales |

### 2.5 Fórmula de puntuación

Cada señal se normaliza a `[0, 1]` y se combina con pesos:

```text
raw = 1.6*question + 1.2*curiosity + 1.0*numbers + 1.1*emotion
    + 0.9*story + 1.0*advice + 1.0*controversy + 0.6*density
    + 0.4*completeness + 0.5*keyword_density
    - 0.9*filler - 0.6*repetition

score = 1 / (1 + e^-(raw - 2.2))    # logística, 0–1
```

El `reason` enumera las 3–4 señales dominantes en lenguaje natural. Si no hay señales
fuertes, usa “Ritmo conversacional y cierre de idea”.

### 2.6 Selección y deduplicación

- Ordenar por `score` descendente y luego por `start`.
- Rechazar un candidato si su solapamiento con un clip ya elegido es **≥ 50 %** del clip
  más corto.
- Rechazar si la similitud Jaccard de palabras es **> 0,85**.
- Detenerse al alcanzar `max_clips`.
- Devolver al menos un clip si la transcripción tiene contenido.

### 2.7 Reglas de ganchos

- Máximo **10 palabras** y 120 caracteres.
- Tono conversacional; se prohíben términos corporativos (`sinergia`, `optimizar`, `KPI`,
  `ROI`, `stakeholder`, `engagement`, etc.).
- Si la primera frase del candidato es una pregunta o una afirmación fuerte de ≤ 10
  palabras, se usa tal cual (sin el punto final).
- Si no, se usa una plantilla según señales y plataforma:
  - TikTok/Reels: `Nadie te cuenta esto sobre {kw}`, `El error que frena tu {kw}`,
    `La verdad sobre {kw} que nadie dice`, `¿Por qué nadie habla de {kw}?`.
  - YouTube Shorts: `La clave para entender {kw}`, `Esto explica {kw} en 30 segundos`,
    `El dato clave sobre {kw}`.
- Si nada valida, fallback: `Esto es lo que nadie te cuenta` (7 palabras).
- La generación es determinista: mismo texto y plataforma → mismo gancho.

### 2.8 Palabras clave

- Tokenizar preservando acentos.
- Excluir stopwords, números y palabras de menos de 4 letras.
- Ordenar por frecuencia y longitud; devolver hasta 5.
- Si no hay, devolver `["esto"]`.

### 2.9 Actividades

1. Crear léxicos y utilidades de normalización.
2. Implementar división de segmentos largos y generación de ventanas.
3. Implementar extracción de señales, scoring, motivo y palabras clave.
4. Implementar selección y deduplicación.
5. Implementar generación y validación de ganchos.
6. Crear fixture y pruebas.
7. Ejecutar `pytest`, cobertura y `ruff`.
8. Documentar cierre y evidencia.

### 2.10 Criterios de aceptación

- [ ] Las ventanas respetan `[min_duration, max_duration]` salvo transcripciones cortas.
- [ ] Un fragmento con pregunta/dato/emoción/consejo supera a uno de relleno.
- [ ] `max_clips` se respeta.
- [ ] No se seleccionan clips con solapamiento ≥ 50 %.
- [ ] Todos los ganchos tienen ≤ 10 palabras y pasan la validación.
- [ ] Los ganchos no contienen términos corporativos.
- [ ] TikTok/Reels y Shorts producen ganchos diferentes cuando aplica.
- [ ] El análisis es determinista.
- [ ] `pytest` pasa y `ruff` no reporta errores.

### 2.11 Riesgos

| Riesgo | Mitigación |
|---|---|
| Heurísticas sesgadas a un estilo | Pesos explícitos + evaluación con casos de oro (Fase 9) |
| Ventanas demasiado solapadas | Deduplicación por solapamiento y similitud |
| Ganchos genéricos | Plantillas por señal + uso de la primera frase fuerte |
| Transcripciones cortas | Fallback de ventana completa |
| Coste en transcripciones largas | Límite de anclas y ventanas |
| Español con acentos | Normalización NFKD para matching, acentos preservados en keywords |

### 2.12 Evidencia esperada

- `src/viralclip/lexicon.py`, `analyzer.py`, `hooks.py`.
- `tests/test_analyzer.py`, `tests/test_hooks.py`.
- Fixture `transcripcion_viral.json`.
- Resultados de `pytest`, cobertura y `ruff`.

---

## 3. Cierre de fase

### 3.1 Resultado

El motor de análisis y los ganchos están implementados y probados:

- segmentación en ventanas de 15–60 s con división de segmentos largos,
- 12 señales lingüísticas normalizadas y puntuación logística 0–1,
- motivo legible por clip (`reason`) y palabras clave,
- selección diversa por score, solapamiento y similitud,
- ganchos deterministas de ≤ 10 palabras con tono conversacional y variantes por
  plataforma,
- fallback seguro para textos vacíos o sin señales.

### 3.2 Evidencia

Código:

- `src/viralclip/lexicon.py`
- `src/viralclip/analyzer.py`
- `src/viralclip/hooks.py`
- `src/viralclip/transcript.py` (síntesis de palabras expuesta como `synthesize_words`)

Pruebas:

- `tests/test_analyzer.py` (10 pruebas)
- `tests/test_hooks.py` (8 pruebas)
- `tests/fixtures/transcripcion_viral.json`

Comandos y resultados:

```text
$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
79 passed in 0.80s
TOTAL  817 stmts  93 miss  290 branch  59 partial  85% cover

$ python -m ruff check src tests
All checks passed!
```

### 3.3 Criterios de aceptación

- [x] Las ventanas respetan `[min_duration, max_duration]` salvo transcripciones cortas.
- [x] Un fragmento con pregunta/dato/emoción/consejo supera a uno de relleno.
- [x] `max_clips` se respeta.
- [x] No se seleccionan clips con solapamiento ≥ 50 %.
- [x] Todos los ganchos tienen ≤ 10 palabras y pasan la validación.
- [x] Los ganchos no contienen términos corporativos.
- [x] TikTok/Reels y Shorts producen ganchos diferentes cuando aplica.
- [x] El análisis es determinista.
- [x] `pytest` pasa (79 pruebas) y `ruff` no reporta errores.

### 3.4 Deuda consciente

- La cobertura de `hooks.py` es 74 %: las ramas de plantillas alternativas se
  ejercitarán con el set de evaluación de la Fase 9.
- El refinamiento con Ollama y la generación de ganchos por LLM se implementan en la
  Fase 5; esta fase deja la interfaz `generate_hook(text, keywords, platform)` lista.
- La calidad del scoring se calibrará con casos de oro y revisión humana en la Fase 9.
- Los pesos son una primera versión explicable, no un modelo entrenado.

### 3.5 Handoff a la Fase 4

La Fase 4 tomará `ClipCandidate` y:

- generará subtítulos dinámicos de 4–5 palabras por línea con resaltado,
- exportará SRT y VTT,
- producirá título, descripción y hashtags por plataforma,
- construirá el `Clip` final y el `AnalysisResult` `v1.0`.

### 3.6 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 4 — Subtítulos
dinámicos y metadatos por plataforma**.
