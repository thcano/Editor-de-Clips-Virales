# ADR-009 — Transcripción local con faster-whisper

> **Estado:** aceptada
> **Fecha:** 2026-11-09
> **Fase:** 12

## Contexto

El producto recibía transcripciones JSON ya preparadas. Para que una persona pueda llegar
a los clips con solo un video, la app necesita convertir el audio en texto con tiempos por
palabra sin enviar nada a la nube.

El equipo de destino es de consumo: Intel i5-11400H (6 núcleos/12 hilos), 7,7 GB de RAM e
Intel UHD, sin CUDA. FFmpeg 8.1 está instalado y dispone de `libass`.

## Decisión

1. **Motor:** `faster-whisper` 1.2.1 sobre CTranslate2. Se instala con pip, funciona en
   CPU y GPU y devuelve `word_timestamps`.
2. **Dispositivo:** detección automática. Si `ctranslate2.get_cuda_device_count() > 0` se
   usa `cuda` y `float16`; si no, `cpu` e `int8`.
3. **Modelo por defecto:** `small`. La interfaz permite `tiny`, `base`, `small`, `medium` y
   `large-v3`; `medium` queda disponible para quien acepte más tiempo y RAM.
4. **Audio:** FFmpeg extrae WAV PCM 16 bits, 16 kHz, mono. El WAV se lee con `wave` y se
   pasa a Whisper como `numpy.ndarray` float32.
5. **Caché:** un solo modelo en memoria (`_get_model`), protegido por lock. Los modelos se
   guardan en el directorio de datos del usuario
   (`%LOCALAPPDATA%\ViralClip\models` en Windows) para no sincronizar gigabytes en OneDrive.
6. **Persistencia:** tabla `transcriptions` en SQLite con estado, etapa, progreso, error y
   JSON normalizado. El progreso se expone por SSE y por sondeo.
7. **Reutilización:** `POST /api/transcriptions/{id}/analyze` crea un análisis con el
   pipeline existente, sin duplicar lógica.

## Por qué no pasar el video directamente a Whisper

`faster-whisper 1.2.1` llama a `av.open(..., metadata_errors=...)`, pero `av 19.0.2` ya no
acepta ese argumento. Pasar el video por PyAV falla con `TypeError`. Extraer el audio con
FFmpeg y entregar un array NumPy evita el decodificador de PyAV, controla el formato exacto
y hace que la transcripción sea reproducible.

## Alternativas descartadas

| Alternativa | Motivo |
|---|---|
| `whisper.cpp` | Requiere binario externo, compilación o descarga aparte y otra integración |
| `openai-whisper` | Más pesado y lento; más dependencias |
| GPU CUDA obligatoria | El equipo no tiene NVIDIA; se detecta y se usa CPU |
| Pasar el video a PyAV | Incompatibilidad real entre faster-whisper 1.2.1 y av 19 |
| Servicio en la nube | Rompe el principio local-first |

## Consecuencias

- La primera transcripción descarga el modelo (`small` ~500 MB; `medium` ~1,5 GB).
- En CPU, un video largo tarda; el progreso y el modelo configurable hacen el coste visible.
- La app depende de FFmpeg en `PATH` (o `VIRALCLIP_FFMPEG`).
- El ejecutable crece al incluir CTranslate2, PyAV, ONNX Runtime y tokenizers.
- El modelo se mantiene fuera del bundle; el `.exe` no lo descarga solo.
