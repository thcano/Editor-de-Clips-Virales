# ADR-007 — Local-first y privacidad por defecto

- **Estado:** aceptado
- **Fecha:** 2026-11-09

## Contexto

Las transcripciones pueden contener información personal, estrategias de negocio o material
no publicado. El producto no necesita la nube para funcionar.

## Decisión

Diseñar la app como **local-first**:

- Ollama y SQLite se ejecutan en el equipo del usuario.
- No hay telemetría ni llamadas a servicios externos por defecto.
- La API escucha en `127.0.0.1` por defecto.
- Los logs no incluyen la transcripción ni datos personales.
- El borrado de un análisis elimina sus clips y metadatos.

## Consecuencias

- Positivas: privacidad, funcionamiento sin internet, cumplimiento más sencillo.
- Negativas: sin sincronización entre dispositivos ni colaboración en el MVP.
- Cualquier integración futura con la nube requerirá consentimiento explícito y una ADR.

## Reglas

- No registrar tokens, API keys ni texto completo de la transcripción.
- Redactar `authorization`, `api_key` y campos equivalentes.
- Exportación y borrado disponibles para el usuario.
- Los datos de ejemplo en tests son sintéticos.

## Referencias

- GDPR
- NIST Privacy Framework
- OWASP Logging Cheat Sheet
