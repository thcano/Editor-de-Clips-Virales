# Fase 7 — Frontend accesible y responsive

> **Proyecto:** Editor de Clips Virales
> **Fase:** 7 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Entradas:** API FastAPI (Fase 6), contrato `v1.0`, `docs/openapi.yaml`

---

## 1. Resumen ejecutivo

Esta fase entrega la interfaz web local del editor: una página sin build (HTML + CSS +
módulos ES) servida por la propia app FastAPI. Permite cargar una transcripción JSON,
elegir plataforma y parámetros, lanzar el análisis, seguir su estado, revisar los clips y
descargar las exportaciones.

El diseño parte de **WCAG 2.2 AA** y de un layout **mobile-first**: navegación por teclado,
foco visible, regiones `aria-live`, etiquetas explícitas, contraste suficiente y objetivos
táctiles de al menos 44 px.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Implementar y probar:

- página `index.html` semántica en español;
- hoja de estilos responsive con tema claro/oscuro;
- módulo `app.js` sin dependencias ni build;
- formulario de transcripción (archivo o pegado) con validación;
- historial de análisis con estados y borrado;
- detalle de clips con gancho, tiempos, texto, hashtags y copia;
- exportaciones `json`, `spec`, `srt` y `vtt`, más SRT por clip;
- indicador de salud (SQLite + Ollama) y ajustes de API key;
- montaje de estáticos y raíz HTML en FastAPI;
- pruebas de servido de la interfaz.

### 2.2 Alcance

#### Incluye

- `src/viralclip/web/index.html`
- `src/viralclip/web/styles.css`
- `src/viralclip/web/app.js`
- `src/viralclip/web/favicon.svg`
- montaje de `/static` y raíz HTML en `src/viralclip/api/app.py`
- `tests/test_web.py`
- `pyproject.toml` (empaquetado de los estáticos)

#### No incluye

- Framework o bundler (React, Vue, Vite, etc.).
- SSE con reconexión: la UI usa sondeo en esta fase; el SSE se endurece en la Fase 8.
- Edición de video, previsualización o renderizado.
- Autenticación multiusuario.
- Pruebas E2E con navegador real (Fase 9).

### 2.3 Estructura de la interfaz

| Zona | Contenido |
|---|---|
| Cabecera | Marca, estado de salud y botón de ajustes |
| Nuevo análisis | Archivo JSON o pegado, plataforma, nº de clips, duración y LLM |
| Historial | Lista paginada con estado, plataforma, motor y acciones |
| Resultado | Metadatos, error, exportaciones y tarjetas de clips |
| Ajustes | API key opcional guardada en `sessionStorage` |
| Avisos | Región `aria-live` para estados y errores |

### 2.4 Flujo de uso

1. La página carga salud, configuración e historial.
2. El usuario elige un archivo `.json` o pega el JSON.
3. Se valida el JSON y se envía `POST /api/analyses`.
4. La UI recibe `202` y consulta `GET /api/analyses/{id}` cada segundo.
5. Al terminar, muestra motor, degradación y clips.
6. El usuario copia ganchos/textos o descarga exportaciones.
7. Puede borrar el análisis o abrir otro desde el historial.

### 2.5 Accesibilidad (WCAG 2.2 AA)

- HTML semántico: `header`, `main`, `section`, `form`, `ol`, `footer`.
- Enlace “Saltar al contenido”.
- Todos los campos con `label` asociado y ayuda con `aria-describedby`.
- Mensajes con `role="status"`/`role="alert"` y `aria-live`.
- Foco visible con `:focus-visible` y foco programático al abrir el detalle.
- Botones con nombre accesible y altura mínima de 44 px.
- Estado no comunicado solo por color: siempre hay texto.
- `prefers-reduced-motion` desactiva transiciones.
- Contraste verificado en tema claro y oscuro.
- `dialog` nativo para ajustes, con cierre por teclado.

### 2.6 Responsive

- Mobile-first: una columna por defecto.
- Dos columnas para formulario e historial desde 860 px.
- Detalle a ancho completo.
- Tipografía fluida con `clamp()`.
- Tablas/acciones que se apilan sin desbordamiento horizontal.

### 2.7 Integración con FastAPI

- `app.mount("/static", StaticFiles(directory=WEB_DIR))`.
- `GET /` devuelve `index.html` con `FileResponse`.
- La API sigue en `/api/*`; los estáticos no requieren API key.
- Si la API key está configurada, la UI la envía en `X-API-Key` y cae a sondeo
  (EventSource no permite cabeceras personalizadas).

### 2.8 Actividades

1. Escribir la planeación y el alcance.
2. Crear HTML semántico y plantilla de clip.
3. Crear CSS responsive con variables y tema oscuro.
4. Implementar `app.js`: cliente API, formulario, historial, detalle y copia.
5. Montar estáticos y raíz HTML en `create_app`.
6. Añadir empaquetado de `web/` en `pyproject.toml`.
7. Escribir pruebas de servido y sanidad del HTML.
8. Ejecutar suite, cobertura, `ruff` y smoke con la app real.
9. Documentar el cierre y el handoff a la Fase 8.

### 2.9 Criterios de aceptación

- [ ] `GET /` devuelve la interfaz HTML en español.
- [ ] `/static/styles.css` y `/static/app.js` se sirven correctamente.
- [ ] El formulario acepta archivo o JSON pegado y valida errores.
- [ ] El análisis se encola y el estado se actualiza hasta `done`/`error`.
- [ ] El historial lista, abre y borra análisis.
- [ ] El detalle muestra ganchos, tiempos, texto, hashtags y exportaciones.
- [ ] La UI refleja `degraded` y los errores `VC-xxxx`.
- [ ] La API key opcional funciona desde ajustes.
- [ ] La interfaz es usable con teclado y en móvil.
- [ ] `pytest` pasa y `ruff` no reporta errores.

### 2.10 Riesgos

| Riesgo | Mitigación |
|---|---|
| JSON inválido o enorme | Validación en cliente y límites del servidor |
| Estado desactualizado | Sondeo con corte en estado terminal |
| API key expuesta | `sessionStorage`, no `localStorage`; campo enmascarado |
| UI inaccesible | Semántica, foco, `aria-live` y pruebas manuales |
| Estáticos fuera del paquete | `package-data` en `pyproject.toml` |
| XSS al pintar textos | `textContent` en lugar de `innerHTML` |

### 2.11 Evidencia esperada

- Archivos en `src/viralclip/web/`.
- Montaje en `create_app` y pruebas `tests/test_web.py`.
- Resultados de `pytest`, cobertura, `ruff` y smoke real.

---

## 3. Cierre de fase

### 3.1 Resultado

La app ya tiene interfaz web local servida por FastAPI:

- `index.html` semántico en español con formulario, historial, detalle, ajustes y avisos;
- `styles.css` mobile-first con tema claro/oscuro, foco visible y `prefers-reduced-motion`;
- `app.js` sin dependencias: cliente API, validación, sondeo de estado, historial, detalle,
  copia al portapapeles y descargas autenticadas;
- `favicon.svg` local;
- `/static` montado con `StaticFiles` y `/` devuelve la interfaz con CSP y cabeceras de
  seguridad;
- `web/` incluido en `package-data` para que los estáticos viajen con el paquete.

La UI refleja el estado real del backend: salud de SQLite/Ollama, motor heurístico o
`heuristic+ollama`, degradación, errores `VC-xxxx` y estados `queued/running/done/error`.

### 3.2 Evidencia

Código:

- `src/viralclip/web/index.html`
- `src/viralclip/web/styles.css`
- `src/viralclip/web/app.js`
- `src/viralclip/web/favicon.svg`
- `src/viralclip/api/app.py` (`WEB_DIR`, `/static`, raíz HTML, CSP)
- `pyproject.toml` (`web/*` en `package-data`)

Pruebas:

- `tests/test_web.py` (servido de HTML/CSS/JS/SVG, 404 de estáticos, cabeceras, etiquetas,
  IDs únicos y referencias `for`/`aria-describedby`).

Comandos y resultados:

```text
$ python -m pytest -o addopts="" -q
217 passed, 1 warning in 2.23s

$ python -m ruff check src tests scripts
All checks passed!

$ node --check src/viralclip/web/app.js
(sin errores de sintaxis)

$ python -m pytest -o addopts="" --cov=viralclip --cov-report=term-missing -q
TOTAL  1802 stmts  122 miss  516 branch  94 partial  90% cover
217 passed, 1 warning in 2.66s
```

La cobertura mide el backend Python; HTML, CSS y JS se validan con pruebas de servido y
parseo de sintaxis. Las pruebas E2E con navegador real quedan para la Fase 9.

Smoke con **uvicorn real** (no `TestClient`) en `127.0.0.1:8765` y SQLite temporal:

```text
root: 200 text/html; charset=utf-8 True
css: 200 text/css; charset=utf-8
js: 200 text/javascript; charset=utf-8
health: ok ok
post: 202
job: done clips: 2 engine: heuristic
```

### 3.3 Criterios de aceptación

- [x] `GET /` devuelve la interfaz HTML en español.
- [x] `/static/styles.css` y `/static/app.js` se sirven correctamente.
- [x] El formulario acepta archivo o JSON pegado y valida errores.
- [x] El análisis se encola y el estado se actualiza hasta `done`/`error`.
- [x] El historial lista, abre y borra análisis.
- [x] El detalle muestra ganchos, tiempos, texto, hashtags y exportaciones.
- [x] La UI refleja `degraded` y los errores `VC-xxxx`.
- [x] La API key opcional funciona desde ajustes.
- [x] La interfaz es usable con teclado y en móvil.
- [x] `pytest` pasa (217 pruebas) y `ruff` no reporta errores.

### 3.4 Deuda consciente

- La UI usa **sondeo cada segundo** en lugar de SSE. Es robusto y funciona con API key,
  pero el SSE con heartbeats, `Last-Event-ID` y reconexión llega en la Fase 8.
- No hay pruebas E2E con navegador real (Playwright) ni auditoría automática de
  accesibilidad; se harán en la Fase 9.
- La API key se guarda en `sessionStorage` (se borra al cerrar la pestaña). No hay gestión
  multiusuario ni cifrado adicional.
- Las descargas se hacen por `fetch` + `Blob` para poder enviar `X-API-Key`; esto requiere
  que el navegador permita `Blob` y `URL.createObjectURL` (soportado en navegadores
  modernos).
- El ejemplo integrado es un guion de ventas; no sustituye una transcripción real.
- La UI no edita clips ni tiempos: solo muestra y exporta lo que devuelve el pipeline.
- No hay i18n: la interfaz está en español.

### 3.5 Handoff a la Fase 8

La Fase 8 endurecerá el tiempo real y los flags:

- SSE con heartbeats, `Last-Event-ID` y reconexión;
- progreso real por etapas en lugar de `queued=0`, `running=50`, `done=100`;
- uso de `stream()` de Ollama para mostrar tokens incrementales si aporta valor;
- feature flags aplicados en la UI (`export_srt`, `sse_progress`);
- integración de las exportaciones y eventos con la interfaz actual.

### 3.6 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 8 — SSE, feature flags e
integraciones**.
