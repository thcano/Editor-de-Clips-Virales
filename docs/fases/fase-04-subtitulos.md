# Fase 4 — Subtítulos dinámicos y metadatos por plataforma

> **Proyecto:** Editor de Clips Virales
> **Fase:** 4 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Entradas:** `ClipCandidate` (Fase 3), `Transcript` (Fase 2), contrato `v1.0`

---

## 1. Resumen ejecutivo

Esta fase convierte los candidatos en **clips listos para publicar**: subtítulos
dinámicos de 4–5 palabras por línea con palabras clave resaltadas, exportación SRT/VTT,
título, descripción y hashtags adaptados a TikTok/Reels o YouTube Shorts, y el
`AnalysisResult` final del contrato `v1.0`.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Implementar y probar:

- recolección de palabras del clip con tiempos ajustados al rango,
- división en líneas de 4–5 palabras y ≤ 42 caracteres,
- cortes por pausa (> 0,6 s) y puntuación,
- resaltado de palabras clave (máximo 2 por línea),
- exportación SRT y VTT,
- título, descripción y hashtags por plataforma,
- pipeline `Transcript + ClipCandidate → Clip → AnalysisResult`,
- pruebas de contrato y determinismo.

### 2.2 Alcance

#### Incluye

- `src/viralclip/subtitles.py`
- `src/viralclip/platforms.py`
- `src/viralclip/pipeline.py`
- `tests/test_subtitles.py`, `tests/test_platforms.py`, `tests/test_pipeline.py`

#### No incluye

- Integración con Ollama (Fase 5).
- Persistencia y API (Fase 6).
- Renderizado de video (fuera de alcance del producto).

### 2.3 Reglas de subtítulos

| Regla | Valor |
|---|---|
| Palabras por línea | 4–5 (máximo 5) |
| Caracteres por línea | ≤ 42 |
| Pausa que corta línea | > 0,6 s |
| Puntuación que corta línea | `.`, `!`, `?`, `;`, `:` si la línea tiene ≥ 2 palabras |
| Resaltados por línea | ≤ 2 |
| Rango | Solo palabras dentro de `[start, end]` del clip; se recortan los bordes |
| Índice | 1..n, consecutivo |

Las palabras se obtienen de los segmentos que se solapan con el clip. Si un segmento no
tiene palabras, se sintetizan con el mismo algoritmo determinista de la Fase 2.

### 2.4 Resaltado

- Se normalizan las palabras (minúsculas, sin acentos) para comparar.
- Se resalta si la palabra pertenece a las keywords del candidato o al léxico de
  curiosidad/emoción.
- Se limita a 2 resaltados por línea para evitar ruido visual.

### 2.5 Exportación

**SRT**

```text
1
00:00:00,000 --> 00:00:01,200
Esto es lo que

2
...
```

**VTT**

```text
WEBVTT

00:00:00.000 --> 00:00:01.200
Esto es lo que
```

Los formatos usan `HH:MM:SS,mmm` (SRT) y `HH:MM:SS.mmm` (VTT). Si no hay líneas, SRT
devuelve cadena vacía y VTT devuelve `WEBVTT`.

### 2.6 Metadatos por plataforma

| Plataforma | Hashtags base | Tono | CTA |
|---|---|---|---|
| `tiktok` | `#fyp #parati #viral #tiktok` | Informal y dinámico | “Guarda este clip y compártelo…” |
| `reels` | `#reels #instagram #viral #explore` | Informal y visual | “Guarda esto para tu próxima publicación.” |
| `shorts` | `#shorts #youtube #viral #youtubeshorts` | Informativo y ágil | “Suscríbete para más clips como este.” |

Reglas:

- Título = gancho limpio, ≤ 120 caracteres.
- Descripción = primera frase del clip (≤ 220 caracteres) + CTA, ≤ 500 caracteres.
- Hashtags = base + keywords + señales (`#consejos`, `#tips`, `#datos`, `#historia`,
  `#opinion`), sin duplicados, máximo 8.
- Hashtags normalizados a ASCII, `#` + `[a-z0-9]`, longitud ≥ 4.
- Sin lenguaje corporativo.

### 2.7 Pipeline

```text
Transcript + ClipCandidate
  → generate_hook()
  → build_subtitles()
  → build_metadata()
  → Clip (id, rank, tiempos, hook, título, descripción, hashtags, score, reason)
  → AnalysisResult v1.0
```

- `id` = `clip_001`, `clip_002`, …
- `rank` = posición por score.
- `engine.name = "heuristic"` y `degraded = true` hasta la Fase 5 (Ollama no integrado).
- `generated_at` configurable para pruebas deterministas.

### 2.8 Actividades

1. Implementar recolección y recorte de palabras.
2. Implementar división de líneas y resaltado.
3. Implementar SRT/VTT.
4. Implementar metadatos por plataforma.
5. Implementar pipeline y construcción de `Clip`.
6. Escribir pruebas unitarias, de contrato y de determinismo.
7. Ejecutar `pytest`, cobertura y `ruff`.
8. Documentar cierre y evidencia.

### 2.9 Criterios de aceptación

- [ ] Todas las líneas tienen ≤ 5 palabras y ≤ 42 caracteres.
- [ ] Los cortes respetan pausas y puntuación.
- [ ] Los tiempos de cada línea quedan dentro del clip.
- [ ] Hay resaltados y nunca más de 2 por línea.
- [ ] SRT y VTT tienen formato válido.
- [ ] Los metadatos respetan límites y hashtags únicos.
- [ ] El pipeline produce `AnalysisResult` válido contra el JSON Schema.
- [ ] El resultado es determinista con `generated_at` fijo.
- [ ] `pytest` pasa y `ruff` no reporta errores.

### 2.10 Riesgos

| Riesgo | Mitigación |
|---|---|
| Líneas ilegibles por palabras largas | Límite de caracteres y máximo 5 palabras |
| Subtítulos desincronizados | Tiempos tomados de las palabras, nunca inventados |
| Demasiados resaltados | Máximo 2 por línea |
| Hashtags inválidos o duplicados | Normalización ASCII + deduplicación |
| Descripciones genéricas | Primera frase real del clip + CTA por plataforma |
| Pipeline acoplado a la API | `pipeline.py` solo depende de modelos y núcleo |

### 2.11 Evidencia esperada

- `src/viralclip/subtitles.py`, `platforms.py`, `pipeline.py`.
- `tests/test_subtitles.py`, `test_platforms.py`, `test_pipeline.py`.
- Resultados de `pytest`, cobertura y `ruff`.

---

## 3. Cierre de fase

### 3.1 Resultado

Los subtítulos dinámicos, las exportaciones y los metadatos por plataforma están
implementados. El pipeline produce un `AnalysisResult` completo y válido contra el
contrato `v1.0`, con clips que incluyen gancho, título, descripción, hashtags y
subtítulos de 4–5 palabras por línea.

### 3.2 Evidencia

Código:

- `src/viralclip/subtitles.py`
- `src/viralclip/platforms.py`
- `src/viralclip/pipeline.py`

Pruebas:

- `tests/test_subtitles.py` (9 pruebas)
- `tests/test_platforms.py` (6 pruebas + 3 parametrizadas)
- `tests/test_pipeline.py` (7 pruebas)

Comandos y resultados:

```text
$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
103 passed in 1.03s
TOTAL  1002 stmts  102 miss  364 branch  72 partial  86% cover

$ python -m ruff check src tests
All checks passed!
```

### 3.3 Criterios de aceptación

- [x] Todas las líneas tienen ≤ 5 palabras y ≤ 42 caracteres.
- [x] Los cortes respetan pausas y puntuación.
- [x] Los tiempos de cada línea quedan dentro del clip.
- [x] Hay resaltados y nunca más de 2 por línea.
- [x] SRT y VTT tienen formato válido.
- [x] Los metadatos respetan límites y hashtags únicos.
- [x] El pipeline produce `AnalysisResult` válido contra el JSON Schema.
- [x] El resultado es determinista con `generated_at` fijo.
- [x] `pytest` pasa (103 pruebas) y `ruff` no reporta errores.

### 3.4 Deuda consciente

- `pipeline.py` deja la rama `use_llm=True` sin efecto real hasta la Fase 5 (cobertura
  90 %, línea 78 pendiente).
- Las plantillas de título y descripción son deterministas; el LLM podrá enriquecerlas
  en la Fase 5 sin cambiar el contrato.
- La exportación SRT/VTT por clip se expondrá por API en la Fase 6.
- No se incluyen estilos ASS ni animaciones: el producto entrega texto y tiempos.

### 3.5 Handoff a la Fase 5

La Fase 5 integrará Ollama:

- health check con timeout corto,
- generación de ganchos con streaming y cancelación,
- timeout, reintentos seguros y circuit breaker,
- degradación a heurísticas con `engine.degraded = true`,
- pruebas con transporte HTTP simulado (sin depender del servicio real).

### 3.6 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 5 — Integración con
Ollama (streaming, cancelación y degradación)**.
