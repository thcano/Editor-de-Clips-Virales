"""Carga, normalización y validación de transcripciones."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import InvalidTranscriptError, PayloadTooLargeError
from .models import Segment, Transcript, Word
from .timeutils import parse_timestamp

DEFAULT_MAX_SEGMENTS = 20_000
DEFAULT_MAX_BYTES = 2_000_000
MAX_OVERLAP_TOLERANCE = 0.5
PAUSE_THRESHOLD = 1.2
MAX_SEGMENT_CHARS = 220

_WHITESPACE_RE = re.compile(r"\S+")
_SENTENCE_END = (".", "!", "?", "…")


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = error.get("msg", "valor inválido")
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_word(raw: Any, *, segment_index: int, word_index: int) -> Word | None:
    if not isinstance(raw, dict):
        raise InvalidTranscriptError(
            f"La palabra {word_index} del segmento {segment_index} no es un objeto"
        )

    text = _coerce_text(raw.get("word") or raw.get("text") or raw.get("punctuation"))
    if not text:
        return None

    start_raw = raw.get("start", raw.get("start_time"))
    end_raw = raw.get("end", raw.get("end_time"))
    try:
        start = parse_timestamp(start_raw)
        end = parse_timestamp(end_raw)
    except (TypeError, ValueError) as exc:
        raise InvalidTranscriptError(
            f"Tiempo inválido en la palabra {word_index} del segmento {segment_index}",
            detail=str(exc),
        ) from exc

    if end <= start:
        raise InvalidTranscriptError(
            f"La palabra {word_index} del segmento {segment_index} tiene end <= start"
        )

    confidence = raw.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None

    try:
        return Word(word=text, start=start, end=end, confidence=confidence)
    except ValidationError as exc:
        raise InvalidTranscriptError(
            f"Palabra inválida en el segmento {segment_index}",
            detail=_format_validation_error(exc),
        ) from exc


def synthesize_words(text: str, start: float, end: float) -> list[Word]:
    """Distribuye la duración del segmento entre sus palabras.

    La distribución pondera por longitud de la palabra y garantiza tiempos
    monótonos y no nulos. Es determinista.
    """

    tokens = _WHITESPACE_RE.findall(text)
    if not tokens:
        return []

    duration = end - start
    if duration <= 0:
        return []

    weights = [max(len(token), 1) for token in tokens]
    total_weight = sum(weights)
    words: list[Word] = []
    cursor = start
    accumulated = 0

    for index, (token, weight) in enumerate(zip(tokens, weights, strict=True)):
        accumulated += weight
        if index == len(tokens) - 1:
            word_end = end
        else:
            word_end = start + duration * (accumulated / total_weight)

        word_start = cursor
        if word_end <= word_start:
            word_end = min(end, word_start + 0.001)
        if word_end <= word_start:
            word_end = word_start + 0.001

        words.append(
            Word(
                word=token,
                start=round(word_start, 3),
                end=round(word_end, 3),
            )
        )
        cursor = word_end

    return words


def _group_words_into_segments(words: list[Word]) -> list[Segment]:
    """Agrupa palabras sueltas en segmentos legibles."""

    ordered = sorted(words, key=lambda word: (word.start, word.end))
    if not ordered:
        return []

    segments: list[Segment] = []
    group: list[Word] = []

    def flush() -> None:
        if not group:
            return
        text = " ".join(word.word for word in group).strip()
        start = group[0].start
        end = group[-1].end
        if end <= start:
            end = start + 0.01
        segments.append(Segment(start=start, end=end, text=text, words=list(group)))
        group.clear()

    for word in ordered:
        if group:
            previous = group[-1]
            gap = word.start - previous.end
            current_text = " ".join(item.word for item in group)
            duration = previous.end - group[0].start
            sentence_end = previous.word.endswith(_SENTENCE_END) and duration >= 3.0
            too_long = len(current_text) >= MAX_SEGMENT_CHARS
            if gap > PAUSE_THRESHOLD or sentence_end or too_long:
                flush()
        group.append(word)

    flush()
    return segments


def _extract_payload(payload: Any, max_bytes: int) -> tuple[Any, str]:
    """Devuelve el documento y el formato detectado."""

    if isinstance(payload, bytes):
        if len(payload) > max_bytes:
            raise PayloadTooLargeError(
                f"La transcripción supera el límite de {max_bytes} bytes"
            )
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidTranscriptError("La transcripción no está codificada en UTF-8") from exc
        return _extract_payload(text, max_bytes)

    if isinstance(payload, str):
        encoded = payload.encode("utf-8")
        if len(encoded) > max_bytes:
            raise PayloadTooLargeError(
                f"La transcripción supera el límite de {max_bytes} bytes"
            )
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise InvalidTranscriptError(
                "El JSON de la transcripción no es válido",
                detail=f"línea {exc.lineno}, columna {exc.colno}: {exc.msg}",
            ) from exc
        return _extract_payload(parsed, max_bytes)

    if isinstance(payload, list):
        return {"segments": payload}, "array"

    if isinstance(payload, dict):
        if "segments" in payload:
            return payload, "document"
        if "words" in payload:
            return payload, "words"
        raise InvalidTranscriptError(
            "La transcripción debe incluir 'segments' o 'words'"
        )

    raise InvalidTranscriptError(
        "La transcripción debe ser un objeto JSON, un array o una cadena JSON"
    )


def normalize_transcript(
    payload: Any,
    *,
    max_segments: int = DEFAULT_MAX_SEGMENTS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Transcript:
    """Normaliza una transcripción heterogénea a :class:`Transcript`.

    Acepta array raíz, documento con ``segments``, salida de Whisper y listas de
    palabras sueltas. Lanza :class:`InvalidTranscriptError` o
    :class:`PayloadTooLargeError` con códigos estables.
    """

    document, source_format = _extract_payload(payload, max_bytes)

    if not isinstance(document, dict):
        raise InvalidTranscriptError("La transcripción normalizada debe ser un objeto")

    if source_format == "words":
        raw_words = document.get("words")
        if not isinstance(raw_words, list) or not raw_words:
            raise InvalidTranscriptError("La lista 'words' está vacía o no es un array")
        if len(raw_words) > max_segments * 50:
            raise PayloadTooLargeError("La transcripción contiene demasiadas palabras")
        words = [
            word
            for index, raw in enumerate(raw_words)
            if (word := _parse_word(raw, segment_index=0, word_index=index)) is not None
        ]
        if not words:
            raise InvalidTranscriptError("No se encontraron palabras válidas")
        segments = _group_words_into_segments(words)
        source_format = "words"
    else:
        raw_segments = document.get("segments")
        if not isinstance(raw_segments, list):
            raise InvalidTranscriptError("'segments' debe ser un array")
        if not raw_segments:
            raise InvalidTranscriptError("La transcripción no contiene segmentos")
        if len(raw_segments) > max_segments:
            raise PayloadTooLargeError(
                f"La transcripción supera el límite de {max_segments} segmentos"
            )

        segments = []
        for index, raw in enumerate(raw_segments):
            if not isinstance(raw, dict):
                raise InvalidTranscriptError(f"El segmento {index} no es un objeto")

            text = _coerce_text(raw.get("text") or raw.get("sentence"))
            if not text:
                continue

            try:
                start = parse_timestamp(raw.get("start", raw.get("start_time")))
                end = parse_timestamp(raw.get("end", raw.get("end_time")))
            except (TypeError, ValueError) as exc:
                raise InvalidTranscriptError(
                    f"Tiempo inválido en el segmento {index}",
                    detail=str(exc),
                ) from exc

            if end <= start:
                raise InvalidTranscriptError(
                    f"El segmento {index} tiene end <= start ({start} >= {end})"
                )

            raw_words = raw.get("words")
            if isinstance(raw_words, list) and raw_words:
                words = [
                    word
                    for word_index, raw_word in enumerate(raw_words)
                    if (
                        word := _parse_word(
                            raw_word,
                            segment_index=index,
                            word_index=word_index,
                        )
                    )
                    is not None
                ]
            else:
                words = synthesize_words(text, start, end)

            try:
                segments.append(
                    Segment(start=start, end=end, text=text, words=words)
                )
            except ValidationError as exc:
                raise InvalidTranscriptError(
                    f"El segmento {index} no es válido",
                    detail=_format_validation_error(exc),
                ) from exc

        if not segments:
            raise InvalidTranscriptError("La transcripción no contiene segmentos con texto")

    segments.sort(key=lambda segment: (segment.start, segment.end))

    for index in range(1, len(segments)):
        overlap = segments[index - 1].end - segments[index].start
        if overlap > MAX_OVERLAP_TOLERANCE:
            raise InvalidTranscriptError(
                f"Los segmentos {index - 1} y {index} se solapan {overlap:.2f}s "
                f"(máximo tolerado {MAX_OVERLAP_TOLERANCE}s)"
            )

    declared_duration: float | None = None
    raw_duration = document.get("duration")
    if raw_duration is not None:
        try:
            declared_duration = parse_timestamp(raw_duration)
        except (TypeError, ValueError) as exc:
            raise InvalidTranscriptError(
                "La duración declarada no es válida", detail=str(exc)
            ) from exc

    computed_duration = segments[-1].end
    duration = max(declared_duration or 0.0, computed_duration)
    if duration <= 0:
        raise InvalidTranscriptError("La duración de la transcripción debe ser mayor que 0")

    language = _coerce_text(document.get("language")) or "es"
    language = language[:10]

    try:
        return Transcript(
            language=language,
            duration=round(duration, 3),
            segments=segments,
            source_format=source_format,
        )
    except ValidationError as exc:
        raise InvalidTranscriptError(
            "La transcripción no cumple el contrato de entrada",
            detail=_format_validation_error(exc),
        ) from exc


def load_transcript(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_segments: int = DEFAULT_MAX_SEGMENTS,
) -> Transcript:
    """Carga una transcripción desde un archivo JSON local."""

    file_path = Path(path).expanduser()
    try:
        resolved = file_path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise InvalidTranscriptError(f"No existe el archivo: {file_path}") from exc

    if not resolved.is_file():
        raise InvalidTranscriptError(f"La ruta no es un archivo: {file_path}")

    size = resolved.stat().st_size
    if size > max_bytes:
        raise PayloadTooLargeError(
            f"El archivo supera el límite de {max_bytes} bytes ({size} bytes)"
        )

    raw = resolved.read_bytes()
    return normalize_transcript(
        raw,
        max_bytes=max_bytes,
        max_segments=max_segments,
    )


def transcript_to_dict(transcript: Transcript) -> dict[str, Any]:
    """Serializa una transcripción normalizada para persistencia o depuración."""

    return transcript.model_dump(mode="json", exclude_none=True)
