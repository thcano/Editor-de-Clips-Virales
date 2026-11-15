# Manual de despliegue — Editor de Clips Virales

> Versión documentada: **0.4.0**
> Audiencia: personas encargadas de instalar, distribuir y dar soporte al producto.
> Cubre los tres escenarios de despliegue: **portable**, **instalación en el equipo** y
> **servidor local compartido**.

---

## 1. Resumen de las opciones de despliegue

| Escenario | Cuándo usarlo | Qué se distribuye | Python requerido |
|---|---|---|---|
| **[A] Portable (bundle)** | Equipos sin permisos de instalación, demos, pruebas | Carpeta `ViralClip/` completa | No |
| **[B] Instalación local** | Uso diario en el equipo de trabajo | Paquete `viralclip` vía `pip` | Sí (3.11+) |
| **[C] Servidor local compartido** | Varios usuarios en la misma red de área local | Código + `uvicorn` | Sí (3.11+) |

> La opción **[A] es la recomendada para distribución**: no requiere Python, no toca el
> sistema y funciona sin conexión.

---

## 2. Requisitos comunes

### Sistema operativo

- Windows 10/11 de 64 bits (validado).
- macOS y Linux: el código funciona, pero el bundle no se ha validado en esas plataformas
  (PyInstaller no compila de forma cruzada; hay que generarlo en cada sistema).

### Dependencias externas

| Dependencia | Obligatoria | Notas |
|---|---|---|
| **FFmpeg** | Sí | Con `libx264` y `libass`. Necesaria para extraer audio y renderizar |
| **Ollama** | No | Solo refina ganchos. Si no está, la app funciona igual |

**Verificar FFmpeg:**

```powershell
ffmpeg -version
```

Debe listar `libx264` y `libass`. Si no aparecen, la transcripción fallará al extraer
audio y el render no podrá escribir subtítulos.

**Instalación de FFmpeg en Windows:** descarga desde [ffmpeg.org](https://ffmpeg.org/),
descomprime y añade la carpeta `bin` al `PATH` del sistema.

---

## 3. Escenario A — Despliegue portable (bundle ejecutable)

### 3.1 Generar el bundle

Desde la raíz del proyecto, con Python 3.11+ y el entorno virtual preparado:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
build.bat
```

Detalle completo del proceso en [`empaquetado.md`](empaquetado.md).

### 3.2 Resultado

```text
dist/
└─ ViralClip/
   ├─ ViralClip.exe          ~14,6 MB
   └─ _internal/             ~236 MB (DLLs, módulos, assets web)
```

**208 archivos · 251,1 MB en total.**

### 3.3 Distribuir

1. Comprime la **carpeta completa** `ViralClip/`:
   ```powershell
   Compress-Archive -Path dist\ViralClip -DestinationPath ViralClip-0.4.0-win64.zip
   ```
2. Publica el `.zip` (GitHub Releases, intranet, drive compartido…).
3. Distribuye **el ZIP**, nunca el `.exe` suelto: sin `_internal/` la app no arranca.

> **Límite de GitHub:** el repositorio no admite ficheros de más de 100 MB en un push, así
> que el ZIP se publica como **GitHub Release** y no se versiona en el árbol. La release
> 0.4.0 está en
> <https://github.com/thcano/Editor-de-Clips-Virales/releases/tag/v0.4.0> y el artefacto
> en
> <https://github.com/thcano/Editor-de-Clips-Virales/releases/download/v0.4.0/ViralClip-0.4.0-win64.zip>.

Con la CLI de GitHub:

```powershell
gh release create v0.4.0 dist\ViralClip-0.4.0-win64.zip `
  --repo thcano/Editor-de-Clips-Virales `
  --title "Editor de Clips Virales 0.4.0 - portable Windows" `
  --notes-file notas.md
```

### 3.4 Instalar en el equipo destino

1. Descomprime el ZIP en una carpeta con espacio para ~300 MB:
   ```
   C:\Apps\ViralClip\
   ```
2. **No** la pongas dentro de `C:\Program Files\` salvo que el usuario tenga permisos de
   escritura (la app escribe en su carpeta de datos, pero conviene evitar rutas
   protegidas por permisos).
3. Doble clic en `ViralClip.exe`.

### 3.5 Qué ocurre en el primer arranque

```text
1. Se resuelve la ruta de datos:
   %LOCALAPPDATA%\ViralClip\
2. Se crea la base SQLite: %LOCALAPPDATA%\ViralClip\viralclip.db
3. Arranca la API en http://127.0.0.1:8000 (o el primer puerto libre)
4. Abre el navegador en la interfaz
5. En la consola se ven la URL y los logs
```

La primera **transcripción** descarga el modelo de Whisper (`small`, ~500 MB) al
directorio de modelos. Requiere conexión en ese momento; después funciona offline.

### 3.6 Atajos y acceso directo

Para crear un acceso directo con puerto fijo:

```bat
"C:\Apps\ViralClip\ViralClip.exe" --port 8000 --no-browser
```

El directorio de trabajo del acceso directo determina dónde se busca el `.env`.

### 3.7 Desinstalar

1. Cerrar la app (la consola, `Ctrl+C`).
2. Borrar la carpeta de la aplicación.
3. Opcional: borrar los datos del usuario:
   ```text
   %LOCALAPPDATA%\ViralClip\
   ```

### 3.8 Verificar la instalación

```powershell
cd C:\Apps\ViralClip
.\ViralClip.exe --version        # → viralclip 0.4.0
.\ViralClip.exe --no-browser --port 8766
```

Comprueba en el navegador:

| URL | Respuesta esperada |
|---|---|
| `/` | Interfaz con estilo Kinetic Typography (fondo negro, hero, marquesina) |
| `/static/styles.css` | `200` con `--accent` y `kin-marquee` |
| `/static/fonts/syne-latin.woff2` | `200` (≈34 KB) |
| `/api/health` | `200` con `"status": "ok"` o `"degraded"` |
| `/api/config` | `200` con `whisper_models` y `ffmpeg_available` |

---

## 4. Escenario B — Instalación desde código (pip)

Adecuado para equipos de desarrollo o cuando se quiere integrar en otro proceso.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install -r requirements-dev.txt   # solo para desarrollo
copy .env.example .env
```

Ejecución:

```powershell
viralclip                    # arranca la API y abre el navegador
viralclip --port 8765
viralclip --no-browser
viralclip --version
```

Para **desplegar en el escritorio** sin terminal, crea un `.bat` y un acceso directo:

```bat
@echo off
cd /d "C:\ruta\al\proyecto"
call .venv\Scripts\activate
viralclip --no-browser
```

### Variables de entorno permanentes

Para fijar configuración sin `.env` (recomendado en instalaciones managed):

```powershell
[Environment]::SetEnvironmentVariable("VIRALCLIP_PORT", "8765", "User")
[Environment]::SetEnvironmentVariable("VIRALCLIP_FFMPEG_PATH", "C:\ffmpeg\bin\ffmpeg.exe", "User")
```

> Un `.env` **no** sobrescribe variables ya definidas en el sistema: lo definido en el
> entorno tiene prioridad.

---

## 5. Escenario C — Servidor local compartido

Para que varias personas en una red de área local usen la misma instancia.

### 5.1 Requisitos

- Debe ejecutarse en un equipo con **FFmpeg** y capacidad de CPU para Whisper.
- Es una app **de un solo usuario por diseño** (SQLite, sin autenticación por usuario).
  Compartirla entre varias personas simultáneas no es un escenario soportado.

### 5.2 Configuración

```powershell
$env:VIRALCLIP_HOST = "0.0.0.0"
$env:VIRALCLIP_PORT = "8000"
$env:VIRALCLIP_API_KEY = "clave-secreta-compartida"
$env:VIRALCLIP_CORS_ORIGINS = "http://192.168.1.50:8000"
$env:VIRALCLIP_DB_PATH = "D:\viralclip-data\viralclip.db"
.venv\Scripts\python.exe -m uvicorn viralclip.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

### 5.3 Acceso desde otros equipos

```
http://<IP-del-servidor>:8000
```

### 5.4 Firewall de Windows

```powershell
New-NetFirewallRule -DisplayName "ViralClip" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
```

> Usa **solo** en redes privadas de confianza. El puerto abierto expone el análisis y los
> archivos del usuario a quien esté en la red.

### 5.5 Sistema como servicio (opcional)

Con [NSSM](https://nssm.cc/):

```powershell
nssm install ViralClip "C:\Apps\ViralClip\ViralClip.exe" "--no-browser --port 8000"
nssm set ViralClip AppDirectory "C:\Apps\ViralClip"
nssm start ViralClip
```

---

## 6. Configuración por entorno

Todos los parámetros se controlan con variables `VIRALCLIP_*`. La lista completa está en
[`manual-tecnico.md` § 6](manual-tecnico.md#6-configuración). Los essentials:

| Variable | Ejemplo | Efecto |
|---|---|---|
| `VIRALCLIP_HOST` | `127.0.0.1` | Interfaz de escucha |
| `VIRALCLIP_PORT` | `8000` | Puerto |
| `VIRALCLIP_DB_PATH` | `D:\datos\viralclip.db` | Ubicación de la base |
| `VIRALCLIP_API_KEY` | *(secreto)* | Exige API key en escritura |
| `VIRALCLIP_WHISPER_MODEL` | `medium` | Modelo de transcripción |
| `VIRALCLIP_FFMPEG_PATH` | `C:\ffmpeg\bin\ffmpeg.exe` | Ruta explícita de FFmpeg |
| `VIRALCLIP_RENDER_WIDTH` / `_HEIGHT` | `1080` / `1920` | Resolución del clip |
| `VIRALCLIP_LLM_ENABLED` | `false` | Desactiva Ollama por completo |
| `VIRALCLIP_LOG_LEVEL` | `WARNING` | Reduce el ruido en consola |

---

## 7. Ubicación de los datos

El ejecutable **nunca escribe dentro de su carpeta de instalación**.

| Dato | Windows | macOS | Linux |
|---|---|---|---|
| Base de datos | `%LOCALAPPDATA%\ViralClip\viralclip.db` | `~/Library/Application Support/ViralClip/` | `$XDG_DATA_HOME/ViralClip/` |
| Modelos Whisper | `%LOCALAPPDATA%\ViralClip\models\` | `…/ViralClip/models/` | `…/ViralClip/models/` |
| Videos subidos | `%LOCALAPPDATA%\ViralClip\uploads\` | `…/ViralClip/uploads/` | `…/ViralClip/uploads/` |
| Renders | `%LOCALAPPDATA%\ViralClip\renders\` | `…/ViralClip/renders/` | `…/ViralClip/renders/` |

Estos valores se pueden redirigir con `VIRALCLIP_DB_PATH`,
`VIRALCLIP_WHISPER_MODEL_DIR`, `VIRALCLIP_UPLOAD_DIR` y `VIRALCLIP_RENDER_DIR`.

### Copias de seguridad

Como la app es local-first, la copia de seguridad es copiar el directorio de datos:

```powershell
robocopy "$env:LOCALAPPDATA\ViralClip" "D:\backups\ViralClip" /E /R:1 /W:1
```

Incluye la base (`viralclip.db`) y, si interesa, los renders. Los modelos de Whisper
(~500 MB) se pueden re-descargar; conviene excluirlos de la copia.

Para restaurar, basta con volver a copiar el directorio.

---

## 8. Verificación posterior al despliegue

Checklist:

- [ ] `ViralClip.exe --version` responde `viralclip 0.4.0`
- [ ] El navegador muestra la interfaz con el estilo Kinetic Typography
- [ ] El título de la pestaña es "Editor de Clips Virales"
- [ ] `/api/health` responde `200`
- [ ] `/api/config` incluye `ffmpeg_available: true`
- [ ] El campo de archivo de "Transcribir video" acepta un `.mp4`
- [ ] Una transcripción de prueba genera `video.transcript.json`
- [ ] "Cargar ejemplo" + "Analizar transcripción" produce clips con gancho y score
- [ ] El botón "Ajustes" abre el diálogo y el foco va al campo API key
- [ ] "Descargar SRT" entrega un `.srt` válido

---

## 9. Problemas frecuentes en despliegue

| Síntoma | Causa | Solución |
|---|---|---|
| Windows SmartScreen bloquea el `.exe` | Binario sin firmar | "Más información → Ejecutar de todas formas" si generaste el binario tú mismo |
| El antivirus lo borra | Falso positivo de PyInstaller | Excluir la carpeta o firmar el binario |
| "No se encontró el módulo viralclip" | Se distribuyó solo el `.exe` | Distribuir la carpeta completa |
| La interfaz aparece sin estilos | Faltan los assets en `_internal/` | Verificar que existe `_internal\viralclip\web\` |
| Las fuentes se ven como fallback | Las woff2 no están en el bundle | Verificar `_internal\viralclip\web\fonts\` |
| `ffmpeg not found` | FFmpeg no está en el `PATH` | Instalar o definir `VIRALCLIP_FFMPEG_PATH` |
| "No se pudo escribir en la base" | Ruta sin permisos | Definir `VIRALCLIP_DB_PATH` en una ruta escribible |
| La transcripción tarda mucho | Modelo `medium` en CPU | Usar `tiny` o `base` |
| El render no escribe subtítulos | FFmpeg sin `libass` | Instalar una build con `libass` |
| "Ollama no responde" | Servicio no iniciado | Opcional: iniciar Ollama o dejar el refinado desactivado |

---

## 10. Actualizar una instalación

1. Descargar la nueva versión del bundle.
2. Detener la app en ejecución (`Ctrl+C` en la consola).
3. Sustituir la carpeta completa por la nueva.
4. **Conservar** `%LOCALAPPDATA%\ViralClip\` (no se toca: es donde están los datos).
5. Ejecutar `ViralClip.exe --version` y arrancar.

El esquema de la base se migra automáticamente al arrancar.

---

## 11. Lista de comprobación de publicación

Antes de publicar una release:

```powershell
# 1. Tests completos
.venv\Scripts\python.exe -m pytest

# 2. Lint
.venv\Scripts\python.exe -m ruff check src tests

# 3. Build limpio
build.bat

# 4. Verificación del ejecutable
.\dist\ViralClip\ViralClip.exe --version
.\dist\ViralClip\ViralClip.exe --no-browser --port 8766
```

Después:

- [ ] La interfaz carga con el estilo Kinetic Typography
- [ ] Las fuentes se sirven (200) desde `/static/fonts/`
- [ ] `/api/health` y `/api/config` responden 200
- [ ] Una transcripción y un render de prueba funcionan
- [ ] El ZIP se genera y se publica en la release de GitHub
- [ ] Los manuales (usuario, técnico, despliegue, empaquetado) están actualizados

---

## 12. Referencias

- Manual de usuario → [manual-usuario.md](manual-usuario.md)
- Manual técnico → [manual-tecnico.md](manual-tecnico.md)
- Manual de empaquetado → [empaquetado.md](empaquetado.md)
- OpenAPI → [`../openapi.yaml`](../openapi.yaml)
