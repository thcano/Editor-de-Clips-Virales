# Changelog

Todas las novedades relevantes del Editor de Clips Virales.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto
adopta [Semantic Versioning](https://semver.org/lang/es/).

---

## [0.5.0] — 2026-11-18

### Añadido

- **Aplicación de escritorio nativa**: el ejecutable abre su **propia ventana** de
  Windows, como cualquier otra aplicación, en lugar de lanzar el navegador del
  sistema. La ventana usa `pywebview`, que en Windows se apoya en **Edge WebView2**
  (el motor de Chromium embebido), con fondo negro para evitar el destello blanco
  al abrir y tamaño inicial de 1280×880 (redimensionable, mínimo 940×620).
- **Cierre limpio**: al cerrar la ventana se detiene el servidor local y termina
  la app. Si ya hay otra instancia en ejecución, se muestra un diálogo nativo
  indicando el puerto ocupado y cómo usar otro.
- **Log de la aplicación**: como el ejecutable ya no tiene consola, la salida se
  redirige a `%LOCALAPPDATA%\ViralClip\viralclip.log`.
- **Diálogos nativos de error** (`MessageBox`) en lugar de mensajes de consola.
- Nuevo módulo `src/viralclip/desktop_window.py` y tests en
  `tests/test_desktop_window.py`.
- Dependencia `pywebview>=6.0`.

### Corregido

- **Crash de arranque del ejecutable sin consola**:
  `AttributeError: 'NoneType' object has no attribute 'isatty'` →
  `ValueError: Unable to configure formatter 'default'`.
  En los builds con `console=False` PyInstaller deja `sys.stdout = None`, y el
  formateador de logs de Uvicorn (`uvicorn/logging.py`) llama a
  `sys.stdout.isatty()` sin protección. Se corrige en tres capas:
  1. `packaging/launcher.py` pasa `os.environ` a `default_data_dir()` (la llamada
     sin ese argumento lanzaba un `TypeError` oculto por un
     `except Exception: pass`, que dejaba la redirección al log sin aplicar) y ya
     no oculta los errores de arranque;
  2. `desktop_window.ensure_streams()` garantiza que `sys.stdout`/`sys.stderr`
     nunca sean `None` (se llama al inicio de `cli.main()` y en
     `_default_server_factory`);
  3. `cli._uvicorn_log_config()` clona la configuración de logging de Uvicorn con
     `use_colors=False`, de modo que el formateador nunca consulta `isatty()`.
- Tests de regresión en `tests/test_no_console_startup.py` que reproducen el
  entorno `sys.stdout = None` del build empaquetado.

### Cambiado

- La CLI abre la **ventana de escritorio por defecto**. Se añade `--browser` para
  abrir la interfaz en el navegador del sistema y se mantiene `--no-browser` para
  arrancar solo el servidor (sin interfaz).
- El spec de PyInstaller genera un ejecutable **sin consola** (`console=False`).
  Se puede forzar una build de consola con `set VIRALCLIP_CONSOLE=1` antes de
  lanzar `build.bat`.
- `packaging/launcher.py` redirige la salida al log del usuario antes de importar
  el resto de la aplicación, para que ningún mensaje se pierda.
- Manuales (usuario, técnico, despliegue, empaquetado) y `README` actualizados a la
  versión **0.5.0**, con la nueva sección de ventana nativa y el diagnóstico del
  arranque sin consola.

---

## [0.4.1] — 2026-11-15

### Corregido

- **El navegador se quedaba con el diseño anterior** (el estilo previo a Kinetic
  Typography) aunque el servidor ya enviase el CSS nuevo. La causa estaba en la
  política de caché HTTP, no en los estilos:
  - `StaticFiles` de Starlette no envía `Cache-Control`, de modo que el navegador
    aplicaba *caché heurística* (10 % de la antigüedad del fichero) y podía
    devolver el `styles.css` antiguo **sin contactar con el servidor**. Como la
    app se sirve siempre desde `127.0.0.1`, el ejecutable y el clon del
    repositorio compartían origen y URL: la copia obsoleta se quedaba pegada en
    ambos.
  - Starlette aceptaba `If-Modified-Since` y respondía `304 Not Modified` cuando
    la fecha de la copia cacheada era igual o posterior al `Last-Modified` del
    fichero. Tras reinstalar o clonar el repo la fecha del fichero puede ser
    *anterior*, de modo que el servidor confirmaba como "no modificado" un CSS
    obsoleto y el cliente conservaba el diseño viejo.

### Añadido

- **Versionado de assets por hash del contenido** (`src/viralclip/assets.py`): las
  URLs de `styles.css`, `app.js` y `favicon.svg` incluyen `?v=<hash>`, así que
  cualquier cambio produce una URL nueva que el navegador no puede reutilizar.
- **El lanzador abre el navegador en una URL versionada**, de modo que la propia
  página de entrada nunca se resuelve desde una caché obsoleta.
- **Purga de la caché obsoleta**: la respuesta de `/` envía `Clear-Site-Data:
  "cache"` cuando la versión de los assets ha cambiado (controlado con la cookie
  `viralclip_assets`), eliminando cualquier copia del diseño anterior.
- **`ETag` por hash del contenido** en los assets: la revalidación solo se acepta
  por `If-None-Match`; `If-Modified-Since` se ignora. Un `304` significa siempre
  "los bytes son idénticos".
- **`Cache-Control: no-cache`** en todos los assets estáticos.
- 6 tests de regresión que cubren la caché, el versionado y el `ETag`.

---

## [0.4.0] — 2026-11-15

### Añadido

- **Renderizado de clips en MP4**: la tarjeta de cada clip incluye una sección para
  renderizarlo en vertical 1080×1920 a 30 fps con `libx264`, subtítulos quemados con
  `libass` y efecto Ken Burns. Genera también miniatura, y permite descargar o borrar el
  archivo.
- **Nuevo ejecutable portable para Windows** generado con PyInstaller en modo `onedir`:
  `dist\ViralClip\ViralClip.exe` (251,1 MB, 208 archivos). No requiere Python instalado.
- **Documentación completa**: manual de usuario, manual técnico, manual de despliegue y
  manual de empaquetado en [`docs/manual/`](docs/manual/).
- **ZIP distribuible** `ViralClip-0.4.0-win64.zip` (102 MB), publicado como
  [GitHub Release v0.4.0](https://github.com/thcano/Editor-de-Clips-Virales/releases/tag/v0.4.0)
  (GitHub no admite ficheros de más de 100 MB en el árbol del repo).

### Cambiado

- **Interfaz rediseñada con el estilo Kinetic Typography**: fondo negro (`#0A0A0A`) con
  grilla y aurora animadas, tipografía display Syne mayúscula con tracking `-0.05em`,
  texto y datos en JetBrains Mono, acento amarillo (`#FFE600`) y naranja (`#FF3D00`).
- **Hero cinético** con palabra rotatoria, contorno `-webkit-text-stroke` en el título y
  marquesina horizontal en bucle infinito.
- **Paneles numerados** (`01` a `04`) con el estilo del catálogo visual del proyecto.
- Manuales actualizados a la versión **0.4.0** y con los datos reales del build
  verificado.

### Corregido

- Restaurado el código fuente del paquete (`src/viralclip/*.py`), los tests y la
  documentación, que habían quedado fuera del árbol de trabajo tras un revert.

---

## [0.3.0]

### Añadido

- **Transcripción local con faster-whisper**: extracción de audio con FFmpeg y
  transcripción en CPU/GPU con caché de modelos en el directorio de datos del usuario.
- Panel **Transcribir video** con selección o arrastre de archivo, ruta local alternativa,
  selección de modelo e idioma, y progreso por etapas con SSE.
- Uso de la API key almacenada en `sessionStorage`, con sondeo en lugar de SSE cuando está
  activa (porque `EventSource` no permite cabeceras personalizadas).

### Cambiado

- Feature flags de **progreso SSE** y **exportación SRT/VTT** exposed en el diálogo de
  Ajustes y aplicados en caliente.

---

## [0.2.0]

### Añadido

- **Renderizado y análisis**: motor heurístico de ganchos con `score` y `reason`
  explicables, adaptación por plataforma (TikTok, Reels, Shorts) y segmentación de
  subtítulos en 4–5 palabras con palabras clave resaltadas.
- Persistencia en **SQLite** con modo WAL e historial de análisis.
- API REST con especificación OpenAPI y cabeceras de seguridad.

### Añadido

- **Integración opcional con Ollama** con circuit breaker: si el servicio falla, el
  análisis continúa con el motor heurístico sin bloquearse.
- **Interfaz web accesible** sin build step: HTML, CSS y módulos ES nativos servidos como
  estáticos.

---

## [0.1.0]

### Añadido

- Estructura inicial del proyecto: arquitectura, contratos JSON y esqueleto de la CLI.
- Decisiones de arquitectura documentadas en [`docs/adr/`](docs/adr/).

[0.5.0]: https://github.com/thcano/Editor-de-Clips-Virales/releases/tag/v0.5.0
[0.4.1]: https://github.com/thcano/Editor-de-Clips-Virales/releases/tag/v0.4.1
[0.4.0]: https://github.com/thcano/Editor-de-Clips-Virales/releases/tag/v0.4.0
