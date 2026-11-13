from __future__ import annotations

import json

import httpx
import pytest

from viralclip.errors import OllamaUnavailableError
from viralclip.llm.ollama import CircuitBreaker, OllamaClient, OllamaHealth

BASE_URL = "http://ollama.test"
MODEL = "llama3.2:latest"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_client(handler, *, clock=None, model: str = MODEL) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return OllamaClient(
        base_url=BASE_URL,
        model=model,
        client=http_client,
        clock=clock,
    )


def tags_response(models: list[str]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"models": [{"name": name} for name in models]},
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/tags"
        return tags_response([MODEL, "mistral:latest"])

    client = make_client(handler)
    health = client.health()

    expected_models = ("llama3.2:latest", "mistral:latest")
    assert health == OllamaHealth(True, MODEL, expected_models, "Ollama disponible")
    assert health.to_dict()["available"] is True


def test_health_matches_model_without_tag() -> None:
    client = make_client(
        lambda request: tags_response([MODEL]),
        model="llama3.2",
    )

    assert client.health().available is True


def test_health_without_models() -> None:
    client = make_client(lambda request: tags_response([]))
    health = client.health()

    assert health.available is False
    assert "no hay modelos instalados" in health.message
    assert "ollama pull" in health.message


def test_health_missing_model() -> None:
    client = make_client(lambda request: tags_response(["mistral:latest"]))
    health = client.health()

    assert health.available is False
    assert "no está instalado" in health.message
    assert MODEL in health.message


def test_health_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión", request=request)

    client = make_client(handler)
    health = client.health()

    assert health.available is False
    assert "no responde" in health.message


def test_health_http_error() -> None:
    client = make_client(lambda request: httpx.Response(500, json={"error": "boom"}))

    assert client.health().available is False


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


def test_generate_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/generate"
        payload = json.loads(request.content)
        assert payload["model"] == MODEL
        assert payload["stream"] is False
        assert payload["system"] == "sistema"
        return httpx.Response(200, json={"response": "  Gancho generado  "})

    client = make_client(handler)

    assert client.generate("prompt", system="sistema") == "Gancho generado"


def test_generate_http_error_raises_vc_4001() -> None:
    client = make_client(lambda request: httpx.Response(500, json={"error": "boom"}))

    with pytest.raises(OllamaUnavailableError) as error:
        client.generate("prompt")

    assert error.value.code.value == "VC-4001"
    assert error.value.http_status == 502


def test_generate_payload_error_raises() -> None:
    client = make_client(
        lambda request: httpx.Response(200, json={"error": "modelo no encontrado"})
    )

    with pytest.raises(OllamaUnavailableError):
        client.generate("prompt")


def test_generate_invalid_json_raises() -> None:
    client = make_client(lambda request: httpx.Response(200, content=b"no-json"))

    with pytest.raises(OllamaUnavailableError):
        client.generate("prompt")


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def test_stream_yields_chunks_until_done() -> None:
    body = (
        b'{"response":"Nadie "}\n'
        b'{"response":"te cuenta"}\n'
        b'{"response":"","done":true}\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        return httpx.Response(200, content=body)

    client = make_client(handler)

    assert "".join(client.stream("prompt")) == "Nadie te cuenta"


def test_stream_ignores_blank_and_malformed_lines() -> None:
    body = b'\n{"response":"Hola"}\nno-json\n{"response":" mundo","done":true}\n'
    client = make_client(lambda request: httpx.Response(200, content=body))

    assert "".join(client.stream("prompt")) == "Hola mundo"


def test_stream_can_be_cancelled() -> None:
    body = b'{"response":"uno"}\n{"response":"dos"}\n{"response":"tres","done":true}\n'
    client = make_client(lambda request: httpx.Response(200, content=body))

    generator = client.stream("prompt")
    assert next(generator) == "uno"
    generator.close()

    with pytest.raises(StopIteration):
        next(generator)


def test_stream_http_error_raises() -> None:
    client = make_client(lambda request: httpx.Response(500, json={"error": "boom"}))

    with pytest.raises(OllamaUnavailableError):
        list(client.stream("prompt"))


def test_stream_payload_error_raises() -> None:
    client = make_client(
        lambda request: httpx.Response(200, content=b'{"error":"sin modelo"}\n')
    )

    with pytest.raises(OllamaUnavailableError):
        list(client.stream("prompt"))


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_opens_after_three_failures() -> None:
    clock = FakeClock()
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(500, json={"error": "boom"})

    client = make_client(handler, clock=clock)

    for _ in range(3):
        with pytest.raises(OllamaUnavailableError):
            client.generate("prompt")

    assert calls["count"] == 3

    with pytest.raises(OllamaUnavailableError) as error:
        client.generate("prompt")

    assert calls["count"] == 3
    assert "Circuito abierto" in (error.value.detail or "")


def test_circuit_breaker_recovers_after_cooldown() -> None:
    clock = FakeClock()
    state = {"fail": True}
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if state["fail"]:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={"response": "Gancho válido"})

    client = make_client(handler, clock=clock)

    for _ in range(3):
        with pytest.raises(OllamaUnavailableError):
            client.generate("prompt")

    assert calls["count"] == 3

    clock.advance(61)
    state["fail"] = False

    assert client.generate("prompt") == "Gancho válido"
    assert calls["count"] == 4


def test_health_reports_open_circuit() -> None:
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = make_client(handler, clock=clock)

    for _ in range(3):
        client.health()

    health = client.health()

    assert health.available is False
    assert "pausa" in health.message


def test_success_resets_failures() -> None:
    state = {"fail": True}
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if state["fail"]:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={"response": "ok"})

    client = make_client(handler)

    with pytest.raises(OllamaUnavailableError):
        client.generate("prompt")
    state["fail"] = False
    assert client.generate("prompt") == "ok"

    state["fail"] = True
    with pytest.raises(OllamaUnavailableError):
        client.generate("prompt")
    with pytest.raises(OllamaUnavailableError):
        client.generate("prompt")

    assert calls["count"] == 4


def test_circuit_breaker_dataclass_directly() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(clock=clock)

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open() is False

    breaker.record_failure()
    assert breaker.is_open() is True
    assert breaker.retry_after == 60.0

    clock.advance(60)
    assert breaker.is_open() is False
    assert breaker.failures == 0


# ---------------------------------------------------------------------------
# Recursos
# ---------------------------------------------------------------------------


def test_injected_client_is_not_closed() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    client = OllamaClient(base_url=BASE_URL, client=http_client)

    client.close()

    assert http_client.is_closed is False
    http_client.close()


def test_owned_client_is_closed() -> None:
    client = OllamaClient(base_url=BASE_URL)
    internal = client._client

    client.close()

    assert internal.is_closed is True


def test_context_manager_closes_owned_client() -> None:
    with OllamaClient(base_url=BASE_URL) as client:
        internal = client._client

    assert internal.is_closed is True
