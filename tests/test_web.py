from __future__ import annotations

from html.parser import HTMLParser

from fastapi.testclient import TestClient


class _MarkupAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.for_targets: list[str] = []
        self.described_by: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])  # type: ignore[arg-type]
        if values.get("for"):
            self.for_targets.append(values["for"])  # type: ignore[arg-type]
        if values.get("aria-describedby"):
            self.described_by.extend(values["aria-describedby"].split())  # type: ignore[union-attr]


def test_root_serves_html(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert '<html lang="es">' in body
    assert "Editor de Clips Virales" in body
    assert 'id="analysis-form"' in body
    assert 'id="history-list"' in body
    assert 'href="#contenido"' in body


def test_root_has_security_headers(client: TestClient) -> None:
    response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Request-ID"]


def test_static_css_is_served(client: TestClient) -> None:
    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "--primary" in response.text
    assert "prefers-reduced-motion" in response.text


def test_static_js_is_served(client: TestClient) -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "fetch(" in response.text
    assert "textContent" in response.text


def test_static_favicon_is_served(client: TestClient) -> None:
    response = client.get("/static/favicon.svg")

    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]


def test_static_missing_file_returns_404(client: TestClient) -> None:
    assert client.get("/static/no-existe.js").status_code == 404


def test_static_assets_force_revalidation(client: TestClient) -> None:
    """Los assets deben revalidarse siempre contra el servidor.

    Sin ``Cache-Control`` el navegador aplica caché heurística y puede
    devolver un ``styles.css`` antiguo sin preguntar al servidor.
    """

    for path in ("/static/styles.css", "/static/app.js", "/static/favicon.svg"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["etag"]


def test_static_etag_is_stable_and_allows_304(client: TestClient) -> None:
    first = client.get("/static/styles.css")
    second = client.get("/static/styles.css")
    assert first.headers["etag"] == second.headers["etag"]

    revalidated = client.get(
        "/static/styles.css",
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert revalidated.status_code == 304
    assert revalidated.content == b""


def test_static_ignores_if_modified_since(client: TestClient) -> None:
    """``If-Modified-Since`` no debe poder confirmar un asset obsoleto.

    Tras reinstalar o clonar el repo la fecha del fichero puede ser anterior
    a la de la copia cacheada; si el servidor aceptase esa fecha respondería
    304 y el navegador conservaría el diseño anterior.
    """

    response = client.get(
        "/static/styles.css",
        headers={"If-Modified-Since": "Wed, 21 Oct 2099 07:28:00 GMT"},
    )
    assert response.status_code == 200
    assert "kin-marquee" in response.text


def test_static_accepts_versioned_query(client: TestClient) -> None:
    response = client.get("/static/styles.css?v=abc123")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_root_versions_asset_urls(client: TestClient) -> None:
    """Las URLs de los assets incluyen la versión para evitar cachés viejas."""

    body = client.get("/").text
    assert "/static/styles.css?v=" in body
    assert "/static/app.js?v=" in body
    assert "/static/favicon.svg?v=" in body


def test_root_clears_stale_cache_once_per_version(client: TestClient) -> None:
    """La primera carga purga la caché; las siguientes ya no hace falta."""

    first = client.get("/")
    assert first.headers["Clear-Site-Data"] == '"cache"'
    assert "viralclip_assets=" in first.headers["set-cookie"]

    cookie = first.headers["set-cookie"].split(";")[0]
    second = client.get("/", headers={"Cookie": cookie})
    assert "Clear-Site-Data" not in second.headers


def test_html_has_accessible_labels(client: TestClient) -> None:
    body = client.get("/").text

    for field in (
        "transcript-file",
        "transcript-text",
        "platform",
        "max-clips",
        "min-duration",
        "max-duration",
        "use-llm",
    ):
        assert f'for="{field}"' in body
    assert 'role="status"' in body
    assert 'role="alert"' in body
    assert 'aria-live="polite"' in body
    assert 'aria-describedby="transcript-help"' in body
    assert 'name="viewport"' in body


def test_html_ids_are_unique_and_references_resolve(client: TestClient) -> None:
    audit = _MarkupAudit()
    audit.feed(client.get("/").text)

    assert len(audit.ids) == len(set(audit.ids))
    ids = set(audit.ids)
    assert set(audit.for_targets) <= ids
    assert set(audit.described_by) <= ids


def test_html_has_flags_panel(client: TestClient) -> None:
    body = client.get("/").text

    assert 'id="flags-list"' in body
    assert 'id="flags-status"' in body
    assert "Funciones" in body


def test_js_uses_sse_with_polling_fallback(client: TestClient) -> None:
    body = client.get("/static/app.js").text

    assert "EventSource" in body
    assert "sse_progress" in body
    assert "export_srt" in body
    assert "Last-Event-ID" not in body
