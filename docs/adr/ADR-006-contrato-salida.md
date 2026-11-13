# ADR-006 — Contrato de salida versionado + export compatible

- **Estado:** aceptado
- **Fecha:** 2026-11-09

## Contexto

`SKILLS.md` define una salida mínima:

```json
[{"start_time": "00:00", "end_time": "00:45", "hook": "...", "caption_text": "...", "hashtags": []}]
```

La app necesita además metadatos para la UI (score, razón, subtítulos, plataforma).

## Decisión

Mantener un **contrato enriquecido versionado** (`version: "1.0"`) como salida principal y
ofrecer un **export `spec`** que devuelve exactamente la lista mínima de `SKILLS.md`.

## Consecuencias

- Positivas: compatibilidad con la especificación y riqueza para la interfaz.
- Negativas: dos formatos que mantener; se cubren con pruebas de esquema.
- Cualquier cambio incompatible sube la versión mayor del contrato y se documenta en el
  changelog.

## Reglas

- `start_time` y `end_time` en formato `MM:SS` o `HH:MM:SS`.
- `hook` ≤ 10 palabras.
- `caption_text` es el texto completo del clip, no la línea de subtítulo.
- `hashtags` sin duplicados, con `#`, máximo 8 por plataforma.
- Los timestamps siempre provienen del parser, nunca del LLM.

## Referencias

- `docs/contratos/salida.schema.json`
- `SKILLS.md` (formato de salida esperado)
