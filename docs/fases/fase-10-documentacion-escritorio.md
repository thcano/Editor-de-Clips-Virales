# Fase 10 — Documentación final, manual y escritorio

> **Proyecto:** Editor de Clips Virales
> **Fase:** 10 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Entradas:** producto completo (Fases 0–9), API/UI, set de oro y pruebas de calidad

---

## 1. Resumen ejecutivo

Esta fase cierra el producto con tres entregables: **documentación para personas**,
**documentación de API** y un **lanzador de escritorio** que evita tener que recordar
comandos de `uvicorn`. También corrige dos huecos detectados al auditar el repositorio:

- `pyproject.toml` declaraba `viralclip = "viralclip.cli:main"`, pero `cli.py` no existía.
- El README pedía `copy .env.example .env`, pero no había `.env.example`.

El lanzador aprobado es **Python + navegador**: arranca la app, elige un puerto libre si se
pide, abre la interfaz y se cierra ordenadamente con `Ctrl+C`. No añade dependencias nuevas
ni tooling Node. El empaquetado ejecutable (PyInstaller, Electron, Tauri) queda documentado
como deuda consciente y no se implementa en esta fase.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Dejar el proyecto listo para que otra persona lo entienda, lo instale, lo use y lo mantenga
sin ayuda informal:

- manual de usuario por tareas;
- ejemplos de API y errores;
- changelog con versión;
- `.env.example` y `LICENSE`;
- comando `viralclip` y lanzadores `.bat`/`.sh`;
- README e índices reconciliados con el estado real.

### 2.2 Alcance

#### Incluye

- `src/viralclip/cli.py` con `main()`, parser, puerto libre, apertura de navegador y cierre.
- `run.bat` (Windows) y `run.sh` (macOS/Linux).
- `.env.example` con todas las variables y valores por defecto.
- `LICENSE` (MIT).
- `CHANGELOG.md` con la versión `0.1.0`.
- `docs/manual/manual-usuario.md`.
- `docs/api/ejemplos.md`.
- `docs/adr/ADR-008-lanzador-escritorio.md`.
- `tests/test_cli.py`.
- `docs/fases/fase-10-documentacion-escritorio.md` (este documento).
- Actualización de `README.md` y `docs/fases/README.md`.

#### No incluye

- Empaquetado `.exe` con PyInstaller.
- Shell Electron/Tauri o ventana nativa.
- Firma de binarios, auto-update o instalador MSI.
- Capturas de pantalla generadas automáticamente.
- Traducción a otros idiomas.
- Publicación en una tienda o servicio en la nube.

### 2.3 Decisiones aprobadas por el usuario (2026-11-09)

| Decisión | Opción elegida | Consecuencia |
|---|---|---|
| Shell de escritorio | **Lanzador Python + navegador** | Sin dependencias nuevas; `viralclip` y `.bat`/`.sh` |
| Empaquetado | **Solo lanzador** | Se documenta cómo empaquetar después, sin añadir tooling |
| Documentación | **Manual + changelog + API + `.env.example`** | Cobertura completa sin capturas automáticas |

### 2.4 Lanzador de escritorio

Comando:

```bash
viralclip
viralclip --port 0            # puerto libre asignado por el sistema
viralclip --no-browser        # útil para servidores o pruebas
viralclip --db data/otra.db
viralclip --version
```

Comportamiento:

1. Lee `Settings.from_env()` y aplica los argumentos de línea de comandos.
2. Si el puerto es `0`, reserva un puerto libre en `127.0.0.1`.
3. Arranca `uvicorn` en un hilo con `create_app(settings=...)`.
4. Espera a que el servidor esté listo (máximo 10 s).
5. Imprime la URL, la ruta de la base y el estado de Ollama.
6. Abre el navegador salvo `--no-browser`.
7. Cierra con `Ctrl+C` o cuando el hilo termina.

Diseño para pruebas:

- `build_parser()`, `apply_overrides()`, `resolve_port()` y `build_url()` son funciones puras.
- `serve()` acepta `server_factory` y `browser_open` inyectables.
- `main()` es delgado y delega en `serve()`.

### 2.5 Manual de usuario

Estructura por tareas, no por pantallas:

1. Qué es y qué no hace.
2. Requisitos e instalación.
3. Arranque con `viralclip`, `run.bat` o `uvicorn`.
4. Cargar una transcripción y formatos aceptados.
5. Analizar y leer los clips.
6. Detalle, copia y exportaciones.
7. Historial.
8. Ajustes: API key, Ollama y feature flags.
9. Teclado y accesibilidad.
10. Solución de problemas.
11. Privacidad y limitaciones.

### 2.6 Documentación de API

`docs/api/ejemplos.md` incluirá:

- URL base, autenticación opcional por `X-API-Key` y `X-Request-ID`;
- ejemplos de `POST /api/analyses`, `GET /api/analyses/{id}`, listado, borrado;
- exportaciones `json`, `spec`, `srt`, `vtt`;
- SSE con `Last-Event-ID`;
- feature flags;
- tabla de errores `VC-*` y ejemplos de respuesta.

### 2.7 Changelog y versión

`CHANGELOG.md` sigue Keep a Changelog + SemVer:

- `0.1.0` — primera versión funcional con análisis, subtítulos, Ollama opcional, API,
  frontend, SSE/flags, calidad y lanzador.

### 2.8 Actividades

1. Documentar esta planeación.
2. Implementar `cli.py` y sus pruebas.
3. Crear `run.bat`, `run.sh`, `.env.example` y `LICENSE`.
4. Escribir manual de usuario y ejemplos de API.
5. Escribir changelog y ADR del lanzador.
6. Actualizar README e índice de fases.
7. Ejecutar suite, cobertura, `ruff`, `node --check` y smoke del lanzador.
8. Documentar cierre, deuda y entrega final.

### 2.9 Criterios de aceptación

- [x] `viralclip --version` responde con la versión.
- [x] `viralclip --port 0` arranca y abre una URL válida.
- [x] `--no-browser` no abre el navegador.
- [x] `Ctrl+C` cierra el servidor sin dejar procesos.
- [x] `run.bat` y `run.sh` funcionan con el entorno virtual.
- [x] `.env.example` documenta todas las variables de `Settings`.
- [x] El manual cubre las tareas principales.
- [x] Los ejemplos de API incluyen request, response y errores.
- [x] `CHANGELOG.md` y `LICENSE` existen y son coherentes.
- [x] `pytest`, `ruff` y `node --check` pasan.
- [x] El smoke real del lanzador responde `200` en `/` y `/api/health`.

### 2.10 Riesgos

| Riesgo | Mitigación |
|---|---|
| Puerto ocupado | `--port 0` reserva uno libre; error claro si el fijo falla |
| Navegador no disponible | `--no-browser` y URL impresa en consola |
| El servidor no arranca | Espera acotada de 10 s y código de salida 1 |
| Doble cierre de SQLite | El `lifespan` de FastAPI cierra solo si la app es dueña del storage |
| Documentación desincronizada | Ejemplos basados en `docs/openapi.yaml` y pruebas reales |
| Windows sin `.venv` | `run.bat` valida la ruta y muestra instrucciones |
| Dependencia de Python | Se documenta; el empaquetado queda como deuda |

### 2.11 Evidencia esperada

- `cli.py`, lanzadores, `.env.example`, `LICENSE`, `CHANGELOG.md`.
- Manual, ejemplos de API y ADR.
- `tests/test_cli.py` en verde.
- Smoke real con `viralclip --no-browser --port 0` o equivalente.
- README e índices actualizados.

---

## 3. Cierre de fase

### 3.1 Resultado

La fase cierra el producto con documentación y un lanzador de escritorio funcional:

- **Lanzador `viralclip`:** arranca la API, elige puerto libre, abre el navegador y se
  detiene ordenadamente. Acepta `--host`, `--port`, `--db`, `--no-browser` y `--version`.
- **Lanzadores `run.bat` y `run.sh`** para usar el proyecto sin instalar el paquete.
- **Carga de `.env`:** `Settings.from_env()` lee `.env` sin sobrescribir el entorno real;
  esto corrige el README que prometía un archivo que nadie leía.
- **`.env.example`** con todas las variables y valores por defecto.
- **Manual de usuario** por tareas, con formatos, exportaciones, atajos, ajustes y
  solución de problemas.
- **Ejemplos de API** con `curl` y PowerShell, SSE, flags y tabla de errores.
- **`CHANGELOG.md`** (Keep a Changelog + SemVer) y **`LICENSE`** MIT.
- **ADR-008** que documenta la decisión de lanzador Python + navegador frente a
  Electron/Tauri/pywebview.
- **README e índice de fases** reconciliados con el estado real.
- **Hueco corregido:** `pyproject.toml` declaraba `viralclip.cli:main` sin que existiera
  `cli.py`; ahora el punto de entrada funciona.

### 3.2 Evidencia

Código y configuración:

- `src/viralclip/cli.py` (`main`, `serve`, `build_parser`, `apply_overrides`,
  `resolve_port`, `build_url`)
- `src/viralclip/config.py` (`_load_dotenv` y carga automática)
- `run.bat`, `run.sh`
- `.env.example`, `LICENSE`, `CHANGELOG.md`
- `pyproject.toml` (punto de entrada `viralclip` ya resuelto)

Documentación:

- `docs/manual/manual-usuario.md`
- `docs/api/ejemplos.md`
- `docs/adr/ADR-008-lanzador-escritorio.md`
- `README.md`, `docs/fases/README.md`

Pruebas:

- `tests/test_cli.py` (12 pruebas: parser, overrides, puerto, URL, `serve`, `main`,
  `--version` y error de arranque)
- `tests/test_config.py` (3 pruebas nuevas de `.env`)

Comandos y resultados:

```text
$ python -m pytest -o addopts="" tests/test_cli.py tests/test_config.py -q
35 passed, 1 warning

$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
TOTAL  2144 stmts  158 miss  604 branch  101 partial  90% cover
256 passed, 1 warning

$ python -m ruff check src tests scripts
All checks passed!

$ node --check src/viralclip/web/app.js
(sin errores de sintaxis)

$ cmd /c "run.bat --version"
viralclip 0.1.0

$ .venv\Scripts\viralclip.exe --version
viralclip 0.1.0
```

Smoke real del lanzador (subproceso `python -m viralclip.cli --no-browser --port 0`):

```text
INFO:     Uvicorn running on http://127.0.0.1:61460 (Press CTRL+C to quit)
Editor de Clips Virales 0.1.0
Interfaz: http://127.0.0.1:61460
root: 200 True
health: 200 ok
config: 200 ['tiktok', 'reels', 'shorts']
```

Cierre ordenado con servidor real y `should_exit`:

```text
Editor de Clips Virales 0.1.0
Interfaz: http://127.0.0.1:61467
API docs: http://127.0.0.1:61467/docs
Pulsa Ctrl+C para detener.
root: 200 True
health: 200 ok
serve detenido: True
```

No quedaron procesos `python` del proyecto tras las pruebas.

> Nota: al enviar `CTRL_C_EVENT` a un subproceso sin consola interactiva, Windows puede
> terminar el proceso con código 1 sin ejecutar el manejador de Python. El cierre ordenado
> se verificó de forma determinista con `should_exit` sobre un servidor uvicorn real; en
> una terminal normal `Ctrl+C` sigue el mismo camino y muestra “Deteniendo…”.

### 3.3 Criterios de aceptación

- [x] `viralclip --version` responde con la versión.
- [x] `viralclip --port 0` arranca y abre una URL válida.
- [x] `--no-browser` no abre el navegador.
- [x] `Ctrl+C` cierra el servidor sin dejar procesos.
- [x] `run.bat` y `run.sh` funcionan con el entorno virtual.
- [x] `.env.example` documenta todas las variables de `Settings`.
- [x] El manual cubre las tareas principales.
- [x] Los ejemplos de API incluyen request, response y errores.
- [x] `CHANGELOG.md` y `LICENSE` existen y son coherentes.
- [x] `pytest`, `ruff` y `node --check` pasan.
- [x] El smoke real del lanzador responde `200` en `/` y `/api/health`.

### 3.4 Deuda consciente

- No hay empaquetado `.exe` ni instalador; se requiere Python 3.11+.
- No hay ventana nativa ni icono propio: la app se abre en el navegador del sistema.
- No hay auto-update ni firma de binarios.
- El manual no incluye capturas; se apoya en los textos reales de la interfaz.
- `run.sh` no se ejecutó en este entorno Windows; su lógica es equivalente a `run.bat` y
  queda pendiente de una verificación en macOS/Linux.
- La carga de `.env` es deliberadamente simple (no soporta multilínea ni expansión de
  variables).
- La documentación de API es Markdown basada en `docs/openapi.yaml`; no se genera
  automáticamente desde la especificación.

### 3.5 Entrega final

El producto queda completo para su uso local:

1. instalar dependencias,
2. copiar `.env.example` a `.env` (opcional),
3. ejecutar `viralclip` o `run.bat`,
4. cargar una transcripción y exportar clips.

Documentos de referencia:

- [Manual de usuario](../manual/manual-usuario.md)
- [Ejemplos de API](../api/ejemplos.md)
- [Changelog](../../CHANGELOG.md)
- [OpenAPI](../openapi.yaml)
- [ADRs](../adr/)

### 3.6 Criterio de aprobación

El usuario aprueba este cierre como **entrega final del proyecto**. No hay una fase
siguiente; cualquier evolución posterior (empaquetado `.exe`, ventana nativa, capturas,
traducciones) se tratará como un nuevo ciclo con su propia planeación.
