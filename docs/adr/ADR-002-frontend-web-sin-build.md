# ADR-002 — Frontend web sin paso de build

- **Estado:** aceptado
- **Fecha:** 2026-11-09

## Contexto

La interfaz debe ser accesible, responsive y fácil de ejecutar en local. El equipo quiere
evitar toolchains de frontend (bundlers, transpiladores, gestores de paquetes) en el MVP.

## Decisión

Construir el frontend con **HTML semántico, CSS moderno y módulos ES nativos**, servidos
como archivos estáticos por FastAPI. Sin React, sin bundler y sin `node_modules` en el MVP.

## Consecuencias

- Positivas: arranque inmediato, menos dependencias, accesibilidad controlable, fácil de
  auditar y de empaquetar.
- Negativas: sin componentes reutilizables de un framework; el estado se gestiona a mano.
- Si el producto crece, se podrá migrar a un framework sin cambiar la API.

## Alternativas consideradas

- **React/Vite:** buena DX, pero añade build y dependencias innecesarias para un MVP local.
- **Electron renderer con React:** se pospone; el shell de escritorio se hará en la Fase 10.

## Referencias

- MDN Web Components
- WCAG 2.2
