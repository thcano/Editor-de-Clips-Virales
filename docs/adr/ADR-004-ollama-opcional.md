# ADR-004 — Ollama opcional con fallback heurístico

- **Estado:** aceptado
- **Fecha:** 2026-11-09

## Contexto

El análisis semántico y la redacción de ganchos mejoran con un LLM, pero no se puede
bloquear la app si Ollama no está instalado, tarda o falla. El equipo tiene
`llama3.2:latest` disponible localmente.

## Decisión

Integrar **Ollama** como motor opcional de refinamiento y redacción. El pipeline siempre
calcula una puntuación heurística determinista y, si Ollama está disponible, la enriquece.
Si no lo está, se devuelve el resultado heurístico con `engine.degraded = true` y un aviso
en la interfaz.

## Consecuencias

- Positivas: la app funciona sin IA generativa; resultados reproducibles; privacidad local.
- Negativas: dos caminos de calidad; hay que probar ambos y evitar divergencias de formato.
- El LLM **no inventa timestamps**: solo puntúa y redacta sobre texto y tiempos ya validados.

## Reglas

- Endpoint y modelo configurables por entorno (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`).
- Timeout por defecto: 60 s para generación, 2 s para health check.
- Streaming con cancelación; el cliente puede detener la generación.
- Circuit breaker: tras 3 fallos consecutivos, se usa el fallback durante 60 s.
- Nunca se envían datos a la nube sin consentimiento explícito.

## Alternativas consideradas

- **Solo heurísticas:** más simple, pero menor calidad de ganchos.
- **Solo LLM:** frágil ante falta de servicio y difícil de testear.
- **API en la nube:** rompe el requisito local-first.

## Referencias

- Ollama API
- Patrón circuit breaker
