# Empaquetado ejecutable (Windows)

> Versión documentada: **0.5.0**
> Esta guía explica cómo generar `ViralClip.exe` a partir del código fuente y cómo usarlo.

---

## 1. Qué genera el empaquetado

PyInstaller en modo **`onedir`** produce una carpeta con el ejecutable y sus dependencias:

```text
dist/
└─ ViralClip/
   ├─ ViralClip.exe
   └─ _internal/
      ├─ viralclip/web/...   (HTML, CSS, JS, favicon, fuentes woff2)
      ├─ python3*.dll
      ├─ ctranslate2/...      (DLLs de Whisper)
      ├─ onnxruntime/...
      └─ ...dependencias de FastAPI, uvicorn, pydantic
```

- El ejecutable **no requiere Python instalado**.
- Es **portable**: puedes mover la carpeta `ViralClip` completa a otra ruta o equipo.
- Debes distribuir **toda la carpeta**, no solo el `.exe`.

Tamaño de referencia del build verificado (0.5.0, Windows 11 x64, Python 3.14):

| Elemento | Tamaño |
|---|---|
| `ViralClip.exe` | 14,63 MB |
| Carpeta `dist/ViralClip` completa | **254,3 MB** (232 archivos) |

El tamaño crece frente a la 0.2.0 porque incluye CTranslate2, PyAV, ONNX Runtime, NumPy,
tokenizers y los ensamblados de interoperabilidad de **WebView2** (necesarios para la
ventana nativa). Los modelos de Whisper **no** están en el bundle.

### Los assets web incluidos

El bundle incluye el frontend completo con el estilo Kinetic Typography:

```text
_internal/viralclip/web/
├─ index.html
├─ styles.css          (~16 KB) con el sistema de diseño kinetic
├─ app.js              (~49 KB)
├─ favicon.svg
└─ fonts/
   ├─ syne-latin.woff2            (34,6 KB)
   └─ jetbrains-mono-latin.woff2  (31,4 KB)
```

Las fuentes están **autoalojadas** a propósito: la CSP del servidor (`default-src 'self'`)
no permite cargar fuentes desde un CDN, y así la app funciona sin conexión.

---

## 2. Requisitos de build

- Windows 10/11 de 64 bits.
- Python 3.11 o superior (verificado con 3.14.7).
- Entorno virtual `.venv` con las dependencias del proyecto.
- **FFmpeg** instalado en el equipo donde se usará el ejecutable (no se incluye en el
  bundle). Se detecta en `PATH` o con `VIRALCLIP_FFMPEG`.
- Las dependencias de empaquetado se instalan solas desde `requirements-build.txt`:
  - `pyinstaller>=6.0`
  - `pillow>=10` (solo para generar el icono)

Preparación:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

---

## 3. Construir el ejecutable

Desde la raíz del proyecto:

```bat
build.bat
```

El script:

1. valida que exista `.venv`;
2. instala `requirements-build.txt`;
3. genera `packaging/viralclip.ico` con `packaging/make_icon.py`;
4. limpia `build/` y `dist/`;
5. ejecuta PyInstaller con `packaging/viralclip.spec`;
6. imprime la ruta final del ejecutable.

Resultado:

```text
dist\ViralClip\ViralClip.exe
```

> `build.sh` existe para macOS/Linux, pero **PyInstaller no compila de forma cruzada**:
> solo genera el binario de la plataforma donde se ejecuta. Este ciclo se validó en
> Windows; el binario de macOS/Linux no está probado.

---

## 4. Usar el ejecutable

Doble clic en `ViralClip.exe` o desde una terminal:

```bat
dist\ViralClip\ViralClip.exe
```

El ejecutable conserva el comportamiento del lanzador `viralclip`:

1. arranca la API local;
2. elige un puerto libre si usas `--port 0`;
3. **abre su propia ventana de escritorio** (no el navegador);
4. se detiene al cerrar la ventana.

Opciones:

```bat
ViralClip.exe                     :: ventana de escritorio (por defecto)
ViralClip.exe --port 0            :: puerto libre automático
ViralClip.exe --browser           :: abre la interfaz en el navegador del sistema
ViralClip.exe --no-browser        :: solo el servidor, sin interfaz
ViralClip.exe --db C:\ruta\mi.db  :: base SQLite explícita
ViralClip.exe --host 127.0.0.1    :: host de escucha
ViralClip.exe --transcribe video.mp4 --model small --language es
ViralClip.exe --version
```

### El ejecutable no tiene consola

Desde la **0.5.0** el build es de tipo ventana (`console=False`): no aparece una
consola de Windows detrás de la app. A cambio:

- la salida (errores, URLs, logs de Uvicorn) se guarda en
  `%LOCALAPPDATA%\ViralClip\viralclip.log`;
- los errores graves se muestran en un diálogo nativo (`MessageBox`);
- al cerrar la ventana se detiene el servidor y no queda ningún proceso en segundo
  plano.

Para depurar, genera una build **con consola**:

```bat
set VIRALCLIP_CONSOLE=1
build.bat
```

Con esa variante los mensajes salen por la consola y `Ctrl+C` detiene el servidor.

### Requisito: Edge WebView2

La ventana se apoya en **WebView2** (el motor Chromium embebido de Edge). Viene
instalado de serie en Windows 11 y en las actualizaciones recientes de Windows 10. Si
no estuviera, Windows ofrece instalarlo automáticamente la primera vez. El bundle
incluye los ensamblados de interoperabilidad (`Microsoft.Web.WebView2.Core.dll` y
`Microsoft.Web.WebView2.WinForms.dll`), pero **no** el runtime del navegador: este se
instala en el sistema.

---

## 5. Dónde se guardan los datos

El ejecutable **no escribe dentro de su carpeta de instalación**. La base SQLite se resuelve así:

| Situación | Ruta de la base |
|---|---|
| `VIRALCLIP_DB_PATH` definida | La ruta indicada (tiene prioridad) |
| `--db RUTA` | La ruta indicada |
| Empaquetado, Windows, sin variable | `%LOCALAPPDATA%\ViralClip\viralclip.db` |
| Empaquetado, macOS, sin variable | `~/Library/Application Support/ViralClip/viralclip.db` |
| Empaquetado, Linux, sin variable | `$XDG_DATA_HOME/ViralClip/viralclip.db` o `~/.local/share/ViralClip/viralclip.db` |
| Código fuente (`python -m viralclip.cli`) | `data/viralclip.db` |

En Windows, por defecto:

```text
C:\Users\<usuario>\AppData\Local\ViralClip\viralclip.db
```

Junto a la base pueden aparecer `viralclip.db-wal` y `viralclip.db-shm`: son normales
(SQLite en modo WAL).

Los **modelos de Whisper** y los **videos subidos** también viven fuera del bundle:

| Dato | Ruta por defecto (Windows) |
|---|---|
| Modelos | `%LOCALAPPDATA%\ViralClip\models` |
| Subidas | `%LOCALAPPDATA%\ViralClip\uploads` |

Se pueden cambiar con `VIRALCLIP_WHISPER_MODEL_DIR` y `VIRALCLIP_UPLOAD_DIR`. La primera
transcripción descarga el modelo; el `.exe` no lo incluye.

La configuración `.env` se lee desde el **directorio de trabajo** desde el que arrancas el
ejecutable. Si quieres una configuración fija, crea un acceso directo con el directorio de
trabajo correcto o define las variables en el sistema.

---

## 6. Qué incluye y qué no

Incluye:

- código de `src/viralclip` y dependencias de `requirements.txt`;
- assets web (`viralclip/web`);
- módulos dinámicos de uvicorn necesarios para HTTP y WebSocket;
- faster-whisper, CTranslate2, PyAV, ONNX Runtime, tokenizers y huggingface_hub;
- icono del ejecutable.

No incluye:

- Ollama ni modelos de IA (siguen siendo un servicio externo opcional);
- modelos de Whisper (se descargan en el directorio de datos del usuario);
- FFmpeg (debe estar instalado en el equipo);
- Playwright, axe, pytest, ruff ni Pillow;
- `tests/`, `scripts/`, `docs/` ni `.venv/`;
- instalador MSI/NSIS, firma de código ni auto-update.

---

## 7. Antivirus y SmartScreen

Los ejecutables generados con PyInstaller a veces se marcan como sospechosos porque el
binario no está firmado y es poco común. Es un **falso positivo** habitual.

Mitigaciones:

- usar `onedir` en lugar de `onefile` (menos detecciones);
- compilar localmente en tu equipo;
- añadir una exclusión en el antivirus si confías en el origen;
- no distribuir el `.exe` por canales no verificados.

Si Windows SmartScreen muestra "Windows protegió tu PC", pulsa **Más información →
Ejecutar de todas formas** solo si generaste el binario tú mismo.

---

## 8. Verificar un build

Comprobaciones rápidas:

```bat
dist\ViralClip\ViralClip.exe --version
```

Debe responder con la versión (por ejemplo `viralclip 0.5.0`).

Arranque y comprobación HTTP:

```bat
dist\ViralClip\ViralClip.exe --no-browser --port 8766
```

> El build normal **no tiene consola**: la URL y los logs se escriben en
> `%LOCALAPPDATA%\ViralClip\viralclip.log`. Ábrelo para ver la salida.

Abre la URL y verifica:

| Comprobación | Resultado esperado |
|---|---|
| `/` | Interfaz con el estilo Kinetic Typography (fondo negro, hero, marquesina) |
| `/static/styles.css` | `200`; el texto contiene `--accent` y `kin-marquee` |
| `/static/fonts/syne-latin.woff2` | `200` (≈34,6 KB) |
| `/static/fonts/jetbrains-mono-latin.woff2` | `200` (≈31,4 KB) |
| `/static/app.js` | `200` |
| `/api/health` | `200` con `status: ok` (o `degraded` si Ollama no está) |
| `/api/config` | `200` e incluye `whisper_models` y `ffmpeg_available` |

Comprobación de la ventana nativa (doble clic en `ViralClip.exe`):

| Comprobación | Resultado esperado |
|---|---|
| Ventana | Aparece con el título **"Editor de Clips Virales"** y el icono de la app |
| Navegador | **No** se abre ninguna pestaña de Chrome, Edge, Firefox o Brave |
| Procesos | Solo `ViralClip.exe` y sus hijos `msedgewebview2.exe` (motor embebido) |
| Tamaño | 1280×880 px (redimensionable, mínimo 940×620) |
| Cierre | Al cerrar la ventana no queda ningún proceso `ViralClip.exe` |

Verificación de los assets web en disco:

```bat
dir dist\ViralClip\_internal\viralclip\web
dir dist\ViralClip\_internal\viralclip\web\fonts
```

Si `fonts/` no existe, el bundle se compiló antes de añadir las fuentes: rebuild.

Transcripción real desde el ejecutable:

```bat
dist\ViralClip\ViralClip.exe --transcribe C:\ruta\video.mp4 --model small --language es
```

Debe escribir `video.transcript.json` y mostrar las etapas de progreso.

Cierre: al cerrar la ventana de escritorio termina el servidor. No debe quedar ningún
proceso `ViralClip.exe`.

---

## 9. Limpiar y reconstruir

> **Clonar el repo:** el bundle usa **git-lfs** (`.dll`, `.exe`, `.pyd` y `.pkg`).
> Instala lfs antes de clonar: `git lfs install`. Sin los binarios reales, el
> ejecutable clonado no arranca.

```bat
rmdir /s /q build
rmdir /s /q dist
build.bat
```

El script ya limpia `build/` y `dist/` en cada ejecución. El icono se regenera también.

---

## 10. Problemas conocidos

| Síntoma | Causa probable | Solución |
|---|---|---|
| `script ... launcher.py not found` | `SPECPATH` mal resuelto en el spec | Actualizar a la versión actual de `packaging/viralclip.spec` |
| La interfaz carga sin estilos | Assets web no incluidos | Revisar `datas` del spec y reconstruir |
| `ModuleNotFoundError: uvicorn...` | Falta un `hiddenimport` | Añadirlo al spec y reconstruir |
| `AttributeError: 'NoneType' object has no attribute 'isatty'` | Build antiguo (pre-0.5.0) o `sys.stdout` a `None` | Actualizar a la 0.5.0; ver [`manual-tecnico.md`](manual-tecnico.md#9-bis-ventana-de-escritorio-nativa) |
| La ventana no aparece | Falta el runtime de WebView2 | Windows lo instala automáticamente; si no, instalarlo desde Microsoft |
| `pywebview` no encontrado | `pywebview` no instalado en el entorno de build | `pip install -r requirements.txt` y reconstruir |
| `Failed to create a .NET runtime (coreclr)` | Faltan los `.pyd` del bundle (bug de `.gitignore` corregido en 0.5.0) | Clonar con `git lfs install` y comprobar que existen `_internal/_cffi_backend*.pyd` e `_internal/_elementtree.pyd` |
| El antivirus borra el `.exe` | Falso positivo de PyInstaller | Exclusión local o build firmado (fuera de alcance) |
| No se puede escribir la base | Ruta sin permisos | Usar `--db` o `VIRALCLIP_DB_PATH` en una ruta escribible |
| Aviso `hidden import 'tzdata' not found` | Dependencia opcional de zonas horarias | No bloquea; se puede ignorar |

---

## 11. Deuda consciente

- Solo se validó el build de **Windows**; macOS/Linux no se probaron.
- No hay instalador, firma de código ni auto-update.
- No hay icono de bandeja; el modo sin consola es el único (se puede forzar una build
  con consola con `set VIRALCLIP_CONSOLE=1`).
- El tamaño del bundle no está optimizado con `upx` (desactivado a propósito para evitar
  más falsos positivos).
- La ruta `.env` depende del directorio de trabajo del acceso directo.
