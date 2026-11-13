# ADR-005 — SSE para progreso en tiempo real

- **Estado:** aceptado
- **Fecha:** 2026-11-09

## Contexto

El análisis de una transcripción larga puede tardar varios segundos. La interfaz necesita
mostrar progreso y permitir cancelar, sin la complejidad de un canal bidireccional.

## Decisión

Usar **Server-Sent Events (SSE)** en `GET /api/analyses/{id}/events` para emitir eventos
unidireccionales `progress`, `done` y `error`. Incluir `id`, heartbeats cada 15 s y soporte
de `Last-Event-ID` para reanudar dentro de la misma sesión.

## Consecuencias

- Positivas: protocolo simple sobre HTTP, reconexión nativa del navegador, compatible con
  `EventSource`, fácil de probar.
- Negativas: unidireccional; la cancelación se hace con `DELETE`/`AbortController`, no por
  el stream.
- Los proxies deben desactivar el buffering (`X-Accel-Buffering: no`).

## Alternativas consideradas

- **WebSockets:** innecesario para progreso unidireccional.
- **Polling:** más simple, pero con latencia y carga extra.

## Referencias

- MDN Server-sent events
- Ollama streaming
