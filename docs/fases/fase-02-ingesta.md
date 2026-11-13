# Fase 2 — Ingesta y validación de transcripciones

> **Proyecto:** Editor de Clips Virales
> **Fase:** 2 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Entradas:** `docs/fases/fase-01-arquitectura.md`, `docs/contratos/transcripcion.schema.json`

---

## 1. Resumen ejecutivo

Esta fase implementa la **puerta de entrada** del producto: convertir una transcripción
JSON heterogénea (array de segmentos, documento con `segments`, salida de Whisper o lista
de palabras) en un modelo interno **normalizado, validado y seguro**, listo para el motor
de análisis.

Sin esta fase, cualquier error de formato o de timestamps se propagaría al scoring y a los
subtítulos, produciendo clips inválidos. Por eso el parser es estricto en lo esencial y
tolerante en lo accesible.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Implementar y probar:

- modelos Pydantic de entrada y salida,
- utilidades de tiempo (`parse_timestamp`, `format_timecode`),
- normalizador de transcripciones con los tres formatos aceptados,
- síntesis de timestamps por palabra cuando no vienen,
- agrupación de palabras sueltas en segmentos,
- errores estables `VC-1001` / `VC-1002`,
- fixtures y pruebas unitarias y de contrato.

### 2.2 Alcance

#### Incluye

- `src/viralclip/timeutils.py`: parseo y formateo de tiempos.
- `src/viralclip/errors.py`: códigos y excepción base.
- `src/viralclip/models.py`: modelos de entrada y salida.
- `src/viralclip/transcript.py`: carga, normalización y validación.
- `tests/fixtures/`: transcripciones sintéticas.
- `tests/test_timeutils.py`, `tests/test_transcript.py`, `tests/test_contracts.py`.

#### No incluye

- Puntuación de momentos virales (Fase 3).
- Generación de ganchos (Fase 3).
- Subtítulos y metadatos (Fase 4).
- Persistencia y API (Fase 6).

### 2.3 Formatos de entrada aceptados

| Formato | Ejemplo | Detección |
|---|---|---|
| Array raíz | `[{"start":0,"end":2,"text":"..."}]` | `payload` es lista |
| Documento | `{"language":"es","segments":[...]}` | clave `segments` |
| Whisper verbose | `{"segments":[...],"language":"es","duration":120}` | clave `segments` |
| Palabras sueltas | `{"words":[{"word":"Hola","start":0,"end":0.4}]}` | clave `words` sin `segments` |

### 2.4 Reglas de normalización

1. Timestamps numéricos en segundos o cadenas `HH:MM:SS(.mmm)` / `MM:SS(.mmm)`.
2. `0 <= start < end <= 86 400`; se rechazan `NaN`, `inf` y negativos.
3. Texto obligatorio y recortado; los segmentos vacíos se omiten si hay otros válidos.
4. Si faltan `words`, se sintetizan distribuyendo la duración del segmento.
5. Si solo hay palabras sueltas, se agrupan por pausas (> 1,2 s) y puntuación final.
6. Se ordenan los segmentos por `start`.
7. Solapamientos mayores a 0,5 s se rechazan; los menores se toleran.
8. `duration` final = máximo entre la declarada y el último `end`.
9. Límites: 20 000 segmentos y 2 MB de payload por defecto.
10. Todo error de forma se convierte en `InvalidTranscriptError` (`VC-1001`) con detalle.

### 2.5 Modelo interno

```python
Transcript(
    language: str,
    duration: float,
    segments: list[Segment],
    source_format: str,
)
Segment(start: float, end: float, text: str, words: list[Word])
Word(word: str, start: float, end: float, confidence: float | None)
```

### 2.6 Modelos de salida (preparados para fases siguientes)

- `SubtitleWord`, `SubtitleLine`, `Clip`, `EngineInfo`, `SourceInfo`, `AnalysisResult`.
- `SpecClip` con la forma mínima de `SKILLS.md`.

Se definen ahora para fijar el contrato, aunque el pipeline los complete en las fases 3–4.

### 2.7 Errores

| Clase | Código | HTTP | Uso |
|---|---|---|---|
| `InvalidTranscriptError` | `VC-1001` | 400 | JSON inválido, campos faltantes, tiempos inconsistentes |
| `PayloadTooLargeError` | `VC-1002` | 413 | Payload o número de segmentos excedido |
| `InvalidParameterError` | `VC-1003` | 422 | Parámetros de análisis fuera de rango |

`ViralClipError.to_payload(request_id)` devuelve `{code, message, detail, request_id}`.

### 2.8 Actividades

1. Crear utilidades de tiempo y errores.
2. Definir modelos Pydantic de entrada y salida.
3. Implementar `normalize_transcript`, `load_transcript` y agrupación de palabras.
4. Crear fixtures representativos y casos inválidos.
5. Escribir pruebas unitarias y de contrato.
6. Ejecutar `pytest` y `ruff`.
7. Documentar evidencia y cerrar la fase.

### 2.9 Criterios de aceptación

- [ ] Los tres formatos de entrada producen un `Transcript` válido.
- [ ] Los timestamps inválidos fallan con `VC-1001` y mensaje claro.
- [ ] Un payload mayor al límite falla con `VC-1002`.
- [ ] Las palabras sintetizadas son monótonas y quedan dentro del segmento.
- [ ] Las palabras sueltas se agrupan en segmentos legibles.
- [ ] Los modelos de salida validan el contrato `v1.0`.
- [ ] `pytest` pasa al 100 %.
- [ ] `ruff` no reporta errores.
- [ ] Los fixtures son sintéticos (sin datos personales).

### 2.10 Riesgos

| Riesgo | Mitigación |
|---|---|
| Transcripciones reales con solapamientos leves | Tolerancia de 0,5 s documentada |
| Palabras sin timestamps | Síntesis proporcional determinista |
| JSON con claves alternativas (`text` vs `word`) | Aceptar ambas en palabras |
| Payload enorme que agota memoria | Límite de bytes antes de `json.loads` |
| Errores de Pydantic poco legibles | Envolver en `InvalidTranscriptError` con índice de segmento |

### 2.11 Evidencia esperada

- Código en `src/viralclip/`.
- Tests en `tests/`.
- Salida de `pytest` y `ruff`.
- Este documento con su cierre.

---

## 3. Cierre de fase

### 3.1 Resultado

La ingesta queda implementada y probada. El parser acepta los cuatro formatos definidos,
normaliza a un `Transcript` validado, sintetiza palabras cuando faltan, agrupa palabras
sueltas y falla con códigos estables. Los modelos de salida `v1.0` también quedaron
definidos y validados contra el JSON Schema.

### 3.2 Evidencia

Código:

- `src/viralclip/__init__.py`
- `src/viralclip/errors.py`
- `src/viralclip/timeutils.py`
- `src/viralclip/models.py`
- `src/viralclip/transcript.py`
- `src/viralclip/py.typed`

Pruebas y fixtures:

- `tests/test_timeutils.py`
- `tests/test_transcript.py`
- `tests/test_contracts.py`
- `tests/fixtures/transcripcion_basica.json`
- `tests/fixtures/transcripcion_array.json`
- `tests/fixtures/transcripcion_whisper.json`
- `tests/fixtures/transcripcion_palabras.json`
- `tests/fixtures/transcripcion_invalida.json`
- `tests/fixtures/transcripcion_solapada.json`

Comandos y resultados:

```text
$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
61 passed in 0.46s
TOTAL  443 stmts  59 miss  148 branch  33 partial  83% cover

$ python -m ruff check src tests
All checks passed!
```

### 3.3 Criterios de aceptación

- [x] Los tres formatos de entrada producen un `Transcript` válido.
- [x] Los timestamps inválidos fallan con `VC-1001` y mensaje claro.
- [x] Un payload mayor al límite falla con `VC-1002`.
- [x] Las palabras sintetizadas son monótonas y quedan dentro del segmento.
- [x] Las palabras sueltas se agrupan en segmentos legibles.
- [x] Los modelos de salida validan el contrato `v1.0`.
- [x] `pytest` pasa al 100 % (61 pruebas).
- [x] `ruff` no reporta errores.
- [x] Los fixtures son sintéticos (sin datos personales).

### 3.4 Deuda consciente

- La cobertura de `errors.py` es 76 %: las ramas de `to_payload` se ejercitarán en la
  Fase 6, cuando la API traduzca errores a respuestas HTTP.
- No se soportan formatos propietarios distintos de los documentados; se ampliarán si
  aparece un JSON real que lo requiera.
- La agrupación de palabras sueltas usa pausas y puntuación; no usa el LLM (decisión
  deliberada para mantener el parser determinista).

### 3.5 Handoff a la Fase 3

La Fase 3 consumirá `Transcript` para:

- segmentar ventanas candidatas de 15–60 s,
- puntuar picos de interés con heurísticas explicables,
- refinar con Ollama de forma opcional,
- seleccionar y deduplicar clips,
- generar ganchos con validación de ≤ 10 palabras.

### 3.6 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 3 — Motor de análisis y
ganchos**.
