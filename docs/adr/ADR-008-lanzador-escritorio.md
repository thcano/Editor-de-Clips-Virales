# ADR-008 — Lanzador de escritorio con Python + navegador

- **Estado:** aceptado
- **Fecha:** 2026-11-09
- **Fase:** 10

## Contexto

El producto es una app web local (FastAPI + HTML/CSS/JS sin build) que hasta ahora se
arrancaba con `uvicorn viralclip.api.app:create_app --factory`. Para una persona que solo
quiere usar la herramienta, recordar ese comando y abrir la URL correcta es fricción
innecesaria.

La Fase 1 había anotado un shell Electron con `contextIsolation` y preload mínimo. Sin
embargo, el stack aprobado es Python + web, el proyecto evita tooling Node y el objetivo es
local-first con el mínimo de dependencias.

## Decisión

Implementar un **lanzador de escritorio en Python** (`viralclip`) que:

1. lee la configuración del entorno y de `.env`;
2. aplica argumentos (`--host`, `--port`, `--db`, `--no-browser`);
3. reserva un puerto libre si se pide `--port 0`;
4. arranca `uvicorn` en un hilo;
5. espera a que el servidor esté listo;
6. abre el navegador del sistema;
7. se cierra ordenadamente con `Ctrl+C`.

Se incluyen `run.bat` (Windows) y `run.sh` (macOS/Linux) para quien no instale el paquete.

## Alternativas consideradas

| Alternativa | Ventajas | Motivos para no elegirla ahora |
|---|---|---|
| **Electron** | Ventana nativa, ecosistema amplio | Añade Node, build y superficie de seguridad; contradice “sin build” |
| **Tauri** | Binario pequeño, seguro | Requiere Rust y toolchain nativo; más complejo para este alcance |
| **pywebview** | Ventana nativa con WebView2 | Añade dependencia y empaquetado por plataforma; no aporta al MVP |
| **Lanzador + navegador** | Sin dependencias nuevas, portable, simple | No es una ventana “de app”; depende del navegador del usuario |

## Consecuencias

### Positivas

- Cero dependencias nuevas y cero tooling Node.
- Funciona en Windows, macOS y Linux con Python 3.11+.
- El navegador ya ofrece accesibilidad, zoom, lector de pantalla y atajos.
- Fácil de probar: `serve()` acepta fábrica de servidor y apertura de navegador inyectables.

### Negativas

- No hay icono ni ventana propia; la app se ve como una pestaña del navegador.
- No hay auto-update ni instalador.
- El usuario necesita Python instalado.

## Deuda y evolución

Si más adelante se necesita una app instalable:

1. empaquetar con PyInstaller o Briefcase;
2. o envolver la app con pywebview/Tauri manteniendo el backend FastAPI;
3. o distribuir un contenedor con `uvicorn` y un navegador embebido.

Ninguna de esas opciones cambia el contrato de la API ni la lógica de dominio.

## Referencias

- `src/viralclip/cli.py`
- `run.bat`, `run.sh`
- ADR-001 (Python + FastAPI)
- ADR-002 (frontend sin build)
