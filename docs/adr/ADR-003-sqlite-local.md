# ADR-003 — SQLite local en modo WAL

- **Estado:** aceptado
- **Fecha:** 2026-11-09

## Contexto

La app es de un solo usuario y debe recordar análisis, clips, ajustes, feature flags y
auditoría sin requerir un servidor de base de datos.

## Decisión

Usar **SQLite** con `journal_mode=WAL`, `foreign_keys=ON` y consultas parametrizadas a
través del módulo estándar `sqlite3`. La base de datos vive en `data/viralclip.db` por
defecto y es configurable.

## Consecuencias

- Positivas: cero infraestructura, transacciones ACID, backup por copia de archivo,
  portabilidad y buen rendimiento de lectura.
- Negativas: un solo escritor; no apta para multiusuario concurrente (fuera de alcance).
- Los binarios no se guardan en la base de datos: solo metadatos y JSON.

## Esquema inicial

`jobs`, `clips`, `settings`, `feature_flags`, `audit_log`, `evaluations`.

## Alternativas consideradas

- **PostgreSQL:** potente, pero requiere servicio y credenciales para un MVP local.
- **Archivos JSON:** simples, pero sin transacciones ni consultas.

## Referencias

- SQLite WAL
- OWASP SQL Injection Prevention
