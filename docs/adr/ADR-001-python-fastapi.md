# ADR-001 — Python 3.11+ y FastAPI para el backend

- **Estado:** aceptado
- **Fecha:** 2026-11-09
- **Decisores:** equipo del proyecto

## Contexto

El producto requiere análisis de texto, integración con Ollama, validación de contratos
JSON y una API local para una interfaz web. El equipo ya dispone de Python 3.14 y Ollama
en el equipo de desarrollo.

## Decisión

Usar **Python 3.11+** como lenguaje del núcleo y **FastAPI** como framework HTTP, con
**Pydantic** para los modelos y **Uvicorn** como servidor ASGI.

## Consecuencias

- Positivas: ecosistema maduro para texto, tipado, validación declarativa, OpenAPI
  automático y pruebas sencillas con `TestClient`.
- Negativas: requiere runtime de Python; el empaquetado de escritorio necesitará un
  binario o un instalador (se aborda en la Fase 10).
- El núcleo se mantiene independiente de FastAPI para poder usarse desde la CLI.

## Alternativas consideradas

- **Node/TypeScript full stack:** un solo lenguaje, pero peor ecosistema local para
  procesamiento de texto y Ollama en este equipo.
- **Flask:** más simple, pero sin validación ni OpenAPI de primera clase.
- **Django:** excesivo para un monolito local de un solo usuario.

## Referencias

- FastAPI
- Pydantic v2
- Python 3.11+
