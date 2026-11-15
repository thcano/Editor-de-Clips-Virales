# Manual de usuario — Editor de Clips Virales

> Versión documentada: **0.4.1**
> Producto local-first: el análisis y los datos se quedan en tu equipo.
> Interfaz con estilo **Kinetic Typography**: la tipografía se mueve y es la protagonista.

---

## 1. Qué es y qué no hace

El Editor de Clips Virales puede **transcribir un video local con Whisper** y analizar la
transcripción para proponer clips candidatos con:

- un **gancho** de menos de 10 palabras para los primeros 3 segundos;
- **subtítulos dinámicos** de 4–5 palabras por línea con palabras clave resaltadas;
- **título, descripción, caption y hashtags** adaptados a TikTok, Instagram Reels o
  YouTube Shorts;
- marcas de tiempo verificables y una puntuación explicable (`score` y `reason`).

**No hace todavía:**

- no renderiza, corta ni reencuadra el video (llega en la Fase 13);
- no quema subtítulos en el video;
- no genera voz en off (TTS) ni avatares;
- no analiza imágenes;
- no publica en redes sociales.

La salida es un conjunto de metadatos, textos y **clips renderizados en MP4** que tú o tu
editor usáis para publicar.

---

## 1 bis. La interfaz

La app usa el estilo **Kinetic Typography**: fondo negro, tipografía display en mayúsculas
y elementos que se mueven. No es un adorno: la estructura de la pantalla refleja esa idea.

| Zona | Qué verás |
|---|---|
| **Fondo** | Negro con una grilla sutil y un resplandor amarillo/naranja que se desplaza lentamente |
| **Cabecera** | Fija al hacer scroll. Logo en degradado, nombre en mayúsculas y el estado del servicio |
| **Hero** | "CLIPS QUE **SE MUEVEN**" en tipografía gigante; la palabra en amarillo rota ligeramente; a la derecha, el contorno `// CLIPS // CLIPS` |
| **Franja amarilla** | "TIPOGRAFÍA CINÉTICA" con un parpadeo lento |
| **Marquesina** | Banda con el ciclo *Transcribe · Analiza · Ganchos · Subtítulos · Hashtags · Renderiza* desplazándose en bucle infinito |
| **Paneles** | Numerados: `01` Transcribir · `02` Nuevo análisis · `03` Historial · `04` Resultado |
| **Botones** | Amarillo sólido. Al pasar el cursor se elevan ligeramente |

**Si prefieres una interfaz sin movimiento**, tu sistema operativo puede desactivar las
animaciones (Windows: *Configuración → Accesibilidad → Efectos visuales → Animaciones*).
La app respeta esa preferencia y también la de los navegadores.

### Ejecución portable (sin Python)

Si te han entregado la carpeta `ViralClip/`, no necesitas instalar nada:

1. Descomprime el ZIP completo.
2. Doble clic en `ViralClip.exe`.
3. Se abre el navegador con la interfaz.

Detalle en la [guía de despliegue](despliegue.md).

---

## 2. Requisitos

- Python 3.11 o superior.
- Windows, macOS o Linux.
- [FFmpeg](https://ffmpeg.org/) instalado y disponible en `PATH` (`ffmpeg -version`).
- (Opcional) [Ollama](https://ollama.com/) para refinar ganchos con IA local.
  ```bash
  ollama pull llama3.2
  ```

La primera transcripción descarga el modelo de Whisper en
`%LOCALAPPDATA%\ViralClip\models` (Windows) o en el directorio de datos del usuario. El
modelo `small` ocupa unos 500 MB; `medium`, alrededor de 1,5 GB.

---

## 3. Instalación

```bash
python -m venv .venv
```

Activa el entorno:

```bat
:: Windows
.venv\Scripts\activate
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Instala dependencias:

```bash
pip install -r requirements-dev.txt
```

Copia la configuración de ejemplo:

```bat
copy .env.example .env
```

```bash
# macOS / Linux
cp .env.example .env
```

El archivo `.env` es opcional: la app funciona con los valores por defecto.

---

## 4. Arrancar la aplicación

### Opción A — Lanzador de escritorio (recomendado)

```bash
viralclip
```

Si instalaste el paquete con `pip install -e .`, el comando anterior funciona directamente.
Si no, usa el lanzador del proyecto:

```bat
:: Windows
run.bat
```

```bash
# macOS / Linux
./run.sh
```

El lanzador:

1. arranca la API local,
2. elige un puerto libre si usas `--port 0`,
3. abre el navegador,
4. se detiene con `Ctrl+C`.

Opciones útiles:

```bash
viralclip --port 0          # puerto libre automático
viralclip --no-browser      # no abre el navegador
viralclip --db data/otra.db # otra base SQLite
viralclip --host 0.0.0.0    # escuchar en la red local (úsalo con cuidado)
viralclip --version
```

### Opción B — Servidor manual

```bash
uvicorn viralclip.api.app:create_app --factory --reload
```

Abre `http://127.0.0.1:8000` para la interfaz y `http://127.0.0.1:8000/docs` para Swagger.

---

## 5. Transcribir un video

El panel **Transcribir video** convierte un archivo local en una transcripción con tiempos
por palabra. Whisper y FFmpeg se ejecutan en tu equipo: el audio no se sube a ningún
servicio.

1. **Selecciona un archivo** con el selector o arrástralo a la zona de carga. También puedes
   escribir una **ruta local** (`C:\videos\entrevista.mp4`). Si indicas ambos, se usa el
   archivo seleccionado.
2. Elige el **modelo**:
   - `small` (por defecto): buen equilibrio para español en CPU;
   - `medium`: más preciso, más lento y con más RAM;
   - `base` / `tiny`: rápidos, con más errores.
3. Elige el **idioma** o deja **Detectar automáticamente**.
4. Pulsa **Transcribir**.

La barra de progreso muestra las etapas `extrayendo`, `cargando modelo`,
`transcribiendo` y `guardando`. Al terminar verás el archivo, idioma, duración, número de
segmentos y palabras.

Desde ahí puedes:

- **Analizar esta transcripción**: crea un análisis con la plataforma, número de clips y
  duraciones configuradas en el panel **Nuevo análisis**;
- **Cargar JSON en el editor**: copia la transcripción al área de texto para revisarla o
  editarla;
- **Copiar JSON**: copia el documento completo.

Los videos subidos se guardan en `%LOCALAPPDATA%\ViralClip\uploads` (Windows) o en el
directorio de datos del usuario. Se borran al eliminar la transcripción.

### Transcripción por línea de comandos

```bash
viralclip --transcribe video.mp4 --model small --language es
viralclip --transcribe video.mp4 --output salida.json --model medium
```

El comando no arranca el servidor y guarda el JSON normalizado.

---

## 6. Cargar una transcripción

En el panel **Nuevo análisis** tienes dos formas:

1. **Archivo de transcripción (JSON):** selecciona un archivo `.json`.
2. **…o pega el JSON aquí:** pega el contenido en el área de texto.

### Formato aceptado

La app acepta un **array de segmentos**:

```json
[
  { "start": 0, "end": 5, "text": "Nadie te cuenta esto: el 80% de las ventas se pierde." },
  { "start": 5, "end": 11, "text": "El error es hablar demasiado." }
]
```

O un **objeto con `segments`**:

```json
{
  "language": "es",
  "duration": 60,
  "segments": [
    { "start": 0, "end": 5, "text": "Nadie te cuenta esto." }
  ]
}
```

También se toleran formatos tipo Whisper con `words` o `start`/`end` por palabra. Los
tiempos deben ser crecientes y coherentes con la duración.

> Si el JSON no es válido, la app muestra un error `VC-1001` con el detalle del problema.

---

## 7. Analizar y leer los clips

1. Elige la **Plataforma** (TikTok, Instagram Reels o YouTube Shorts).
2. Ajusta el **Número de clips** (1–8; el máximo real lo define `VIRALCLIP_MAX_CLIPS`).
3. En **Opciones avanzadas** puedes cambiar:
   - **Duración mínima** y **máxima** de cada clip;
   - **Refinar ganchos con Ollama si está disponible**.
4. Pulsa **Analizar transcripción**.

El panel **Resultado** muestra una tarjeta por clip con:

- **gancho** y **tiempo** (`00:05–00:20`);
- **puntuación** de potencial viral;
- **caption** y **motivo** (`reason`);
- **hashtags**;
- botones **Copiar gancho**, **Copiar texto** y **Descargar SRT**.

Si Ollama está activo, el motor aparece como `heuristic+ollama`; si no, como `heuristic`
con una nota de degradación. La app **nunca inventa timestamps**: el LLM solo reescribe el
gancho.

---

## 8. Exportar

En la parte superior del resultado, **Descargar:**

| Formato | Contenido |
|---|---|
| **JSON** | Resultado completo con timestamps, score, subtítulos y metadatos |
| **Especificación** | Formato mínimo de `SKILLS.md`: `start_time`, `end_time`, `hook`, `caption_text`, `hashtags` |
| **SRT** | Subtítulos combinados de todos los clips |
| **VTT** | Subtítulos combinados en formato WebVTT |

También puedes descargar el **SRT de un clip concreto** desde su tarjeta.

> Si el flag **Exportar subtítulos SRT/VTT** está apagado, los botones SRT/VTT se ocultan y
> la API responde `403 VC-2003`.

---

## 8 bis. Renderizar el clip en MP4

Cada tarjeta de clip incluye una sección **Renderizar clip** que convierte el resultado en
un vídeo vertical listo para publicar.

1. Escribe la **ruta del video de origen** en el campo de texto:
   ```text
   C:\videos\entrevista.mp4
   ```
2. Pulsa **Renderizar clip**.

Durante el proceso verás una barra de progreso y la etapa actual. Al terminar aparecen:

- un **visor de vídeo** con el clip renderizado;
- la **miniatura**;
- botones **Descargar MP4** y **Descargar miniatura**;
- **Borrar render**, que elimina el archivo del disco.

### Características del render

| Aspecto | Valor por defecto |
|---|---|
| Resolución | 1080 × 1920 (vertical 9:16) |
| Fotogramas por segundo | 30 |
| Códec de vídeo | H.264 (`libx264`), CRF 20 |
| Perfil | `veryfast` |
| Códec de audio | AAC |
| Subtítulos | Quemados en el vídeo con `libass` |
| Efecto | Zoom lento (Ken Burns) del 6 % |

El render **requiere FFmpeg** con `libx264` y `libass`. Si falta, la transcripción y el
análisis siguen funcionando; solo el render falla.

Los archivos se guardan en `%LOCALAPPDATA%\ViralClip\renders` (Windows) o en el directorio
de datos del usuario.

> El render es la parte más pesada: puede tardar varios minutos según la duración del
> vídeo y la potencia del equipo. No cierres la app mientras corre.

---

## 9. Historial

El panel **Historial** lista los análisis guardados en SQLite.

- **Abrir:** carga el resultado en el panel **Resultado**.
- **Borrar:** pide confirmación y elimina el análisis y sus clips.
- **Actualizar:** vuelve a consultar la lista.

El historial se guarda en `data/viralclip.db` salvo que definas `VIRALCLIP_DB_PATH`.

---

## 10. Ajustes

Pulsa **Ajustes** en la cabecera.

### API key

Solo es necesaria si definiste `VIRALCLIP_API_KEY` en el entorno. Se guarda en la pestaña
actual y se borra al cerrarla. Si está activa, la UI usa sondeo en lugar de SSE, porque
`EventSource` no permite enviar cabeceras personalizadas.

### Funciones (feature flags)

- **Exportar subtítulos SRT/VTT** (`export_srt`): controla la disponibilidad de SRT/VTT.
- **Progreso en tiempo real por SSE** (`sse_progress`): prefiere SSE sobre sondeo.

Los cambios se aplican al instante en la pestaña.

---

## 11. Teclado y accesibilidad

- `Tab` recorre enlaces, campos y botones en orden lógico.
- El primer `Tab` lleva a **Saltar al contenido**.
- `Escape` cierra el diálogo de **Ajustes**.
- Al abrir Ajustes, el foco entra en el campo **API key**.
- Los estados y errores se anuncian en regiones `aria-live`.
- La interfaz respeta `prefers-reduced-motion` y el contraste AA.

---

## 12. Solución de problemas

### La interfaz se ve con el diseño anterior

Si tras actualizar la app sigues viendo el diseño previo (fondo claro, tipografía
del sistema) en lugar del estilo **Kinetic Typography**, el navegador tiene una
copia antigua de `styles.css` guardada.

**Solución:** abre la interfaz desde el enlace que imprime la consola al
arrancar. La app abre el navegador en una URL versionada
(`http://127.0.0.1:8000/?v=...`) y además pide al navegador que vacíe su caché
la primera vez, de modo que el diseño antiguo desaparece por completo.

Si aun así persistiera:

1. Pulsa `Ctrl+F5` (recarga forzada) o `Ctrl+Shift+R`.
2. Cierra **todas** las pestañas de la app y vuelve a abrirla.
3. Como último recurso, borra los datos del sitio en
   *Configuración → Privacidad → Cookies y datos de sitios → Borrar datos* para
   `127.0.0.1:8000`.

> Desde la **versión 0.4.1** esto ya no debería ocurrir: los assets se sirven con
> `Cache-Control: no-cache`, con `ETag` calculado sobre el hash del contenido y
> con URLs versionadas. El detalle técnico está en el
> [manual técnico](manual-tecnico.md#caché-de-los-assets-por-qué-el-diseño-se-quedaba-obsoleto).

### Ollama no disponible

La app sigue funcionando con el motor heurístico. Para activarlo:

```bash
ollama serve
ollama pull llama3.2
```

Comprueba el estado en la cabecera o en `GET /api/health`.

### El puerto está ocupado

```bash
viralclip --port 0
```

### `401 VC-3001` (API key)

Define la clave en **Ajustes** o elimina `VIRALCLIP_API_KEY` del entorno.

### `VC-1001` (transcripción inválida)

Revisa que los segmentos tengan `start`, `end` y `text`, que los tiempos sean crecientes y
que la duración no sea menor que el último `end`.

### `VC-1002` (payload demasiado grande)

Reduce el tamaño del JSON o aumenta `VIRALCLIP_MAX_INPUT_BYTES`.

### `VC-1101` / `VC-1102` (video no válido o demasiado grande)

Comprueba que la ruta existe y que la extensión está soportada (MP4, MKV, MOV, WebM, MP3,
WAV…). Para archivos enormes, usa una ruta local en vez de subirlos o aumenta
`VIRALCLIP_UPLOAD_MAX_BYTES`.

### `VC-1103` (FFmpeg no disponible)

Instala FFmpeg y comprueba que responde:

```bash
ffmpeg -version
```

Si está instalado pero fuera de `PATH`, define `VIRALCLIP_FFMPEG` con la ruta completa.

### La transcripción tarda mucho o se queda sin memoria

En CPU, Whisper es lento. Usa `small` o `base`, cierra otras aplicaciones y evita
`medium`/`large-v3` en equipos con poca RAM. El modelo se carga una sola vez y se reutiliza.

### La primera transcripción tarda en empezar

Está descargando el modelo en `%LOCALAPPDATA%\ViralClip\models`. Necesita conexión la
primera vez; después funciona sin red.

### La base no se puede abrir

Cierra otras instancias de la app y verifica permisos sobre `data/`. SQLite usa modo WAL,
así que pueden existir archivos `viralclip.db-wal` y `viralclip.db-shm` junto a la base.

### El navegador no se abre

Usa `viralclip --no-browser` y abre la URL que imprime la consola.

---

## 13. Privacidad y limitaciones

- **Local-first:** no hay telemetría ni llamadas a la nube por defecto.
- Ollama y Whisper se ejecutan en tu equipo; el audio y los textos no salen de tu máquina.
- La primera transcripción descarga el modelo de Whisper desde Hugging Face; después el
  uso es totalmente local.
- Las fuentes tipográficas (Syne y JetBrains Mono) están **alojadas en la propia app**: no
  se hace ninguna petición a Google Fonts ni a ningún CDN. La interfaz se ve igual sin
  conexión.
- La base SQLite es local y de un solo usuario.
- Existe una **versión portable para Windows** (`dist\ViralClip\ViralClip.exe`, ~251 MB)
  que no requiere Python instalado; consulta la [guía de empaquetado](empaquetado.md) y la
  [guía de despliegue](despliegue.md). En macOS/Linux se ejecuta con Python instalado.
- FFmpeg debe estar instalado en el equipo; no se incluye en el ejecutable.
- El progreso es por etapas gruesas, no token a token.
- El juez LLM de calidad es opcional y no determinista.

---

## 14. Documentos relacionados

| Documento | Para quién |
|---|---|
| [Manual de usuario](manual-usuario.md) *(este)* | Quien usa la app |
| [Manual técnico](manual-tecnico.md) | Desarrollo y mantenimiento |
| [Manual de despliegue](despliegue.md) | Instalación y distribución |
| [Manual de empaquetado](empaquetado.md) | Generación del ejecutable |
| [Documentación de la API](../openapi.yaml) | Integraciones |
- El renderizado y el quemado de subtítulos llegan en la Fase 13.
