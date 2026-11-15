# Changelog

Todas las novedades relevantes del Editor de Clips Virales.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto
adopta [Semantic Versioning](https://semver.org/lang/es/).

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

[0.4.0]: https://github.com/thcano/Editor-de-Clips-Virales/releases/tag/v0.4.0
