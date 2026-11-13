# Empaquetado ejecutable (Windows)

> Versión documentada: **0.3.0**
> Esta guía explica cómo generar `ViralClip.exe` a partir del código fuente y cómo usarlo.

---

## 1. Qué genera el empaquetado

PyInstaller en modo **`onedir`** produce una carpeta con el ejecutable y sus dependencias:

```text
dist/
└─ ViralClip/
   ├─ ViralClip.exe
   └─ _internal/
      ├─ viralclip/web/...   (HTML, CSS, JS, favicon)
      ├─ python3*.dll
      ├─ ctranslate2/...      (DLLs de Whisper)
      ├─ onnxruntime/...
      └─ ...dependencias de FastAPI, uvicorn, pydantic
```

- El ejecutable **no requiere Python instalado**.
- Es **portable**: puedes mover la carpeta `ViralClip` completa a otra ruta o equipo.
- Debes distribuir **toda la carpeta**, no solo el `.exe`.

Tamaño de referencia del build verificado:

| Elemento | Tamaño |
|---|---|
| `ViralClip.exe` | ~13,9 MB |
| Carpeta `dist/ViralClip` completa | ~251 MB (206 archivos) |

El tamaño crece frente a la 0.2.0 porque incluye CTranslate2, PyAV, ONNX Runtime, NumPy y
tokenizers. Los modelos de Whisper **no** están en el bundle.

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
3. abre el navegador;
4. se detiene con `Ctrl+C` en la ventana de consola.

Opciones:

```bat
ViralClip.exe --port 0            :: puerto libre automático
ViralClip.exe --no-browser        :: no abre el navegador
ViralClip.exe --db C:\ruta\mi.db  :: base SQLite explícita
ViralClip.exe --host 127.0.0.1    :: host de escucha
ViralClip.exe --transcribe video.mp4 --model small --language es
ViralClip.exe --version
```

La consola muestra la URL, la documentación de la API y los logs. Es intencional: permite
ver errores y cerrar el servidor con `Ctrl+C`.

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

Debe responder con la versión (por ejemplo `viralclip 0.3.0`).

Arranque y comprobación HTTP:

```bat
dist\ViralClip\ViralClip.exe --no-browser --port 0
```

Abre la URL impresa y verifica:

- `/` muestra la interfaz con el panel **Transcribir video**;
- `/static/app.js` responde `200`;
- `/api/health` responde `200` con `status: ok`;
- `/api/config` responde `200` e incluye `whisper_models` y `ffmpeg_available`.

Transcripción real desde el ejecutable:

```bat
dist\ViralClip\ViralClip.exe --transcribe C:\ruta\video.mp4 --model small --language es
```

Debe escribir `video.transcript.json` y mostrar las etapas de progreso.

Cierre: `Ctrl+C` en la consola. No debe quedar ningún proceso `ViralClip.exe`.

---

## 9. Limpiar y reconstruir

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
| El antivirus borra el `.exe` | Falso positivo de PyInstaller | Exclusión local o build firmado (fuera de alcance) |
| No se puede escribir la base | Ruta sin permisos | Usar `--db` o `VIRALCLIP_DB_PATH` en una ruta escribible |
| Aviso `hidden import 'tzdata' not found` | Dependencia opcional de zonas horarias | No bloquea; se puede ignorar |

---

## 11. Deuda consciente

- Solo se validó el build de **Windows**; macOS/Linux no se probaron.
- No hay instalador, firma de código ni auto-update.
- No hay icono de bandeja ni modo sin consola.
- El tamaño del bundle no está optimizado con `upx` (desactivado a propósito para evitar
  más falsos positivos).
- La ruta `.env` depende del directorio de trabajo del acceso directo.
