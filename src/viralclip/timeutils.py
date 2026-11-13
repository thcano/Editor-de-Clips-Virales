"""Parseo y formateo de marcas de tiempo."""

from __future__ import annotations

import math
import re

MAX_SECONDS = 86_400.0

_NUMERIC_RE = re.compile(r"^\d+(?:\.\d+)?$")
_CLOCK_RE = re.compile(
    r"^(?:(?P<hours>\d{1,2}):)?(?P<minutes>\d{1,2}):(?P<seconds>\d{1,2}(?:\.\d{1,3})?)$"
)


def parse_timestamp(value: float | int | str) -> float:
    """Convierte segundos o cadenas de reloj a segundos (float, 3 decimales).

    Formatos aceptados:
    - número de segundos: ``12``, ``12.5``
    - ``MM:SS``: ``01:02``, ``01:02.500``
    - ``HH:MM:SS``: ``01:02:03``, ``01:02:03.500``

    Lanza ``ValueError`` con un mensaje claro si el valor no es válido.
    """

    if isinstance(value, bool):
        raise ValueError("El tiempo no puede ser un booleano")

    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("El tiempo está vacío")
        if _NUMERIC_RE.match(text):
            seconds = float(text)
        else:
            match = _CLOCK_RE.match(text)
            if match is None:
                raise ValueError(f"Formato de tiempo no reconocido: {value!r}")
            hours = int(match.group("hours") or 0)
            minutes = int(match.group("minutes"))
            secs = float(match.group("seconds"))
            if minutes >= 60:
                raise ValueError(f"Los minutos deben ser menores que 60: {value!r}")
            if secs >= 60:
                raise ValueError(f"Los segundos deben ser menores que 60: {value!r}")
            seconds = hours * 3600 + minutes * 60 + secs
    else:
        raise ValueError(f"Tipo de tiempo no soportado: {type(value).__name__}")

    if not math.isfinite(seconds):
        raise ValueError("El tiempo debe ser un número finito")
    if seconds < 0:
        raise ValueError("El tiempo no puede ser negativo")
    if seconds > MAX_SECONDS:
        raise ValueError(f"El tiempo excede el máximo de {MAX_SECONDS:.0f} segundos")
    return round(seconds, 3)


def format_timecode(seconds: float, *, force_hours: bool = False) -> str:
    """Formatea segundos como ``MM:SS`` o ``HH:MM:SS``.

    Se redondea al segundo más cercano. Los valores negativos se tratan como 0.
    """

    total = int(round(max(0.0, float(seconds))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours or force_hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
