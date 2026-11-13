# ADR-010 — Renderizado local con FFmpeg

- **Estado:** aceptado
- **Fecha:** 2026-11-09
- **Fase:** 13

## Contexto

La app ya transcribe y analiza, pero el clip final se montaba a mano. Se necesita un MP4
vertical listo para TikTok/Reels/Shorts sin depender de servicios en la nube, sin editor
externo y con el menor número de dependencias nuevas posible.

## Decisión

1. **Usar el FFmpeg del sistema**, no una librería de edición ni un servicio externo.
   FFmpeg ya era requisito para extraer audio de Whisper y aporta `libx264`, AAC y
   `libass`.
2. **Un solo grafo de filtros** por clip:
   - fondo: `scale` + `crop` + `boxblur` + `eq`;
   - frente: `scale` ajustado al marco y zoom animado con `eval=frame`;
   - composición: `overlay` centrado + `ass` + `yuv420p`.
3. **Subtítulos ASS** generados en un directorio temporal y referenciados por nombre,
   con `cwd` en ese directorio. Así se evitan problemas de escapado de rutas de Windows.
4. **Salida fija 1080×1920, 30 fps, H.264 CRF 20, AAC 192 kbps** con valores
   configurables por entorno.
5. **Miniatura JPG** extraída del primer segundo del MP4 (o del centro si el clip es
   más corto).
6. **Runner serializado** con `threading.Lock`: un render a la vez para no saturar la
   CPU del equipo objetivo (i5-11400H, 7,7 GB RAM, sin CUDA).
7. **Persistencia en SQLite** (`renders`) y progreso por SSE con sondeo de respaldo.
8. **Origen automático**: los análisis creados desde una transcripción heredan su
   `source_path`; los análisis manuales aceptan una ruta en la solicitud.

## Alternativas descartadas

| Alternativa | Motivo |
|---|---|
| MoviePy / imageio-ffmpeg | Añade Python y una copia de FFmpeg; menos control del grafo |
| Servicio en la nube | Rompe el principio local-first y añade coste/latencia |
| `zoompan` | Más difícil de combinar con el fondo y el overlay; el zoom por `scale` animado es suficiente |
| Varios renders en paralelo | Saturaría CPU/RAM y haría impredecible el progreso |
| Guardar rutas dentro del filtro `ass` | Escapado frágil en Windows con espacios, acentos y dos puntos |

## Consecuencias

- El equipo necesita FFmpeg con `libx264` y `libass`; si falta, la API responde
  `VC-1202`.
- El render es más lento que un editor nativo, pero predecible y sin nube.
- El bundle no incluye FFmpeg; se documenta como requisito externo.
- El zoom animado y el fondo desenfocado se validaron con un frame real del video de
  prueba.
- Los renders viven en `%LOCALAPPDATA%\ViralClip\renders` y se pueden borrar desde la
  interfaz.
