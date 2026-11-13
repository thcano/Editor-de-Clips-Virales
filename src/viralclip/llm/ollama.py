"""Cliente HTTP para Ollama con health check, streaming y circuit breaker.

El cliente nunca lanza errores fatales: ante un fallo de red, un timeout o una
respuesta inválida se lanza :class:`OllamaUnavailableError` para que el pipeline
degradación a las heurísticas.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import httpx

from ..errors import OllamaUnavailableError

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.2:latest"
DEFAULT_TIMEOUT = 60.0
DEFAULT_HEALTH_TIMEOUT = 2.0
FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 60.0

_UNAVAILABLE_MESSAGE = (
    "Ollama no está disponible; se usará el motor heurístico. "
    "Inicia Ollama y verifica OLLAMA_BASE_URL."
)


@dataclass(frozen=True)
class OllamaHealth:
    """Resultado del health check, apto para ``/api/health``."""

    available: bool
    model: str
    models: tuple[str, ...] = ()
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "model": self.model,
            "models": list(self.models),
            "message": self.message,
        }


@dataclass
class CircuitBreaker:
    """Corta las llamadas tras varios fallos consecutivos.

    El reloj es inyectable para que las pruebas no dependan del tiempo real.
    """

    failure_threshold: int = FAILURE_THRESHOLD
    cooldown_seconds: float = COOLDOWN_SECONDS
    clock: Callable[[], float] = field(default_factory=lambda: time.monotonic)
    failures: int = 0
    open_until: float = 0.0

    def is_open(self) -> bool:
        if self.open_until <= 0:
            return False
        if self.clock() < self.open_until:
            return True
        self.failures = 0
        self.open_until = 0.0
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.open_until = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.open_until = self.clock() + self.cooldown_seconds

    @property
    def retry_after(self) -> float:
        if self.open_until <= 0:
            return 0.0
        return max(0.0, round(self.open_until - self.clock(), 1))


class OllamaClient:
    """Cliente mínimo de la API de Ollama.

    Parámetros
    ----------
    base_url:
        URL del servicio, por defecto ``http://127.0.0.1:11434``.
    model:
        Modelo a usar, por defecto ``llama3.2:latest``.
    timeout:
        Timeout de generación en segundos.
    health_timeout:
        Timeout del health check en segundos.
    client:
        ``httpx.Client`` inyectable (útil con ``MockTransport``). Si se pasa,
        el llamador es responsable de cerrarlo.
    clock:
        Reloj monótono inyectable para el circuit breaker.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        health_timeout: float = DEFAULT_HEALTH_TIMEOUT,
        client: httpx.Client | None = None,
        clock: Callable[[], float] | None = None,
        failure_threshold: int = FAILURE_THRESHOLD,
        cooldown_seconds: float = COOLDOWN_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.health_timeout = health_timeout
        self._owns_client = client is None
        self._client = client or httpx.Client()
        self._breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
            clock=clock or time.monotonic,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def health(self) -> OllamaHealth:
        """Comprueba disponibilidad y que el modelo esté instalado."""

        if self._breaker.is_open():
            return OllamaHealth(
                False,
                self.model,
                (),
                (
                    "Ollama está en pausa tras varios fallos consecutivos "
                    f"({self._breaker.retry_after}s). Se usará el motor heurístico."
                ),
            )

        try:
            response = self._client.get(
                f"{self.base_url}/api/tags", timeout=self.health_timeout
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            self._breaker.record_failure()
            return OllamaHealth(
                False,
                self.model,
                (),
                (
                    f"Ollama no responde en {self.base_url}. "
                    "Inicia Ollama o revisa OLLAMA_BASE_URL."
                ),
            )

        models = self._parse_models(payload)
        if not models:
            self._breaker.record_failure()
            return OllamaHealth(
                False,
                self.model,
                (),
                (
                    "Ollama está activo pero no hay modelos instalados. "
                    f"Ejecuta: ollama pull {self.model}"
                ),
            )

        if not self._model_installed(models):
            self._breaker.record_failure()
            return OllamaHealth(
                False,
                self.model,
                models,
                (
                    f"El modelo {self.model} no está instalado. "
                    f"Ejecuta: ollama pull {self.model}"
                ),
            )

        self._breaker.record_success()
        return OllamaHealth(True, self.model, models, "Ollama disponible")

    # ------------------------------------------------------------------
    # Generación
    # ------------------------------------------------------------------
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Genera una respuesta completa (sin streaming)."""

        self._raise_if_open()
        payload = self._payload(prompt, system=system, stream=False)

        try:
            response = self._client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self._breaker.record_failure()
            raise OllamaUnavailableError(
                _UNAVAILABLE_MESSAGE, detail=str(exc)
            ) from exc

        if isinstance(data, dict) and data.get("error"):
            self._breaker.record_failure()
            raise OllamaUnavailableError(
                _UNAVAILABLE_MESSAGE, detail=str(data["error"])
            )

        self._breaker.record_success()
        text = data.get("response", "") if isinstance(data, dict) else ""
        return str(text).strip()

    def stream(self, prompt: str, *, system: str | None = None) -> Iterator[str]:
        """Genera tokens incrementales leyendo NDJSON.

        El consumidor puede detener la iteración en cualquier momento; el
        contexto ``with`` cierra la conexión y libera los recursos.
        """

        self._raise_if_open()
        payload = self._payload(prompt, system=system, stream=True)

        try:
            with self._client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    if data.get("error"):
                        self._breaker.record_failure()
                        raise OllamaUnavailableError(
                            _UNAVAILABLE_MESSAGE, detail=str(data["error"])
                        )
                    chunk = data.get("response") or ""
                    if chunk:
                        yield str(chunk)
                    if data.get("done"):
                        break
        except OllamaUnavailableError:
            raise
        except httpx.HTTPError as exc:
            self._breaker.record_failure()
            raise OllamaUnavailableError(
                _UNAVAILABLE_MESSAGE, detail=str(exc)
            ) from exc
        else:
            self._breaker.record_success()

    # ------------------------------------------------------------------
    # Recursos
    # ------------------------------------------------------------------
    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _payload(
        self, prompt: str, *, system: str | None, stream: bool
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        return payload

    def _raise_if_open(self) -> None:
        if self._breaker.is_open():
            raise OllamaUnavailableError(
                _UNAVAILABLE_MESSAGE,
                detail=(
                    "Circuito abierto tras fallos consecutivos; "
                    f"reintenta en {self._breaker.retry_after}s."
                ),
            )

    @staticmethod
    def _parse_models(payload: object) -> tuple[str, ...]:
        if not isinstance(payload, dict):
            return ()
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            return ()
        names: list[str] = []
        for item in raw_models:
            if isinstance(item, dict):
                name = item.get("name") or item.get("model")
                if isinstance(name, str) and name:
                    names.append(name)
        return tuple(sorted(set(names)))

    def _model_installed(self, models: tuple[str, ...]) -> bool:
        for installed in models:
            if installed == self.model:
                return True
            if ":" not in self.model and installed.split(":", 1)[0] == self.model:
                return True
        return False
