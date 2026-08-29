"""SPA shell is served only for known client routes; probes get a 404."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.spa import ROUTE_META, SPA_ROUTES, is_spa_route, mount_spa, render_shell


class TestIsSpaRoute:
    @pytest.mark.parametrize("path", ["", "paste", "url", "fundsxml", "fundsxml/", "paste//", "api-docs"])
    def test_known_routes(self, path: str) -> None:
        assert is_spa_route(path)

    @pytest.mark.parametrize(
        "path",
        ["wp-login.php", "wp-admin/js/", "xleet.php", ".well-known/", "randkeyword.PhP7",
         "index.html", "api/", "fundsxml/extra", "PASTE"],
    )
    def test_unknown_paths(self, path: str) -> None:
        assert not is_spa_route(path)

    def test_routes_mirror_frontend(self) -> None:
        assert frozenset({"", "paste", "url", "fundsxml", "api-docs"}) == SPA_ROUTES


SHELL = """<html><head>
<title>Online XSD Viewer</title>
<meta
  name="description"
  content="home description"
/>
<link rel="canonical" href="https://www.xsd-viewer.online/" />
<meta property="og:title" content="Online XSD Viewer" />
<meta property="og:description" content="home description" />
<meta property="og:url" content="https://www.xsd-viewer.online/" />
</head><body>shell</body></html>"""


class TestRenderShell:
    def test_home_keeps_defaults(self) -> None:
        out = render_shell(SHELL, "")
        assert "<title>Online XSD Viewer</title>" in out
        assert 'href="https://www.xsd-viewer.online/"' in out

    def test_api_docs_gets_own_title_description_canonical(self) -> None:
        out = render_shell(SHELL, "api-docs")
        meta = ROUTE_META["api-docs"]
        assert f"<title>{meta.title.replace('&', '&amp;')}</title>" in out
        assert 'content="home description"' not in out
        assert 'href="https://www.xsd-viewer.online/api-docs"' in out
        assert 'property="og:url" content="https://www.xsd-viewer.online/api-docs"' in out
        assert 'property="og:title" content="XML validation via API' in out
        assert "shell" in out

    @pytest.mark.parametrize("route", ["paste", "url"])
    def test_uploader_tabs_canonicalise_to_home(self, route: str) -> None:
        out = render_shell(SHELL, route)
        assert 'rel="canonical" href="https://www.xsd-viewer.online/"' in out
        assert "<title>Online XSD Viewer</title>" not in out

    def test_trailing_slash_tolerated(self) -> None:
        assert render_shell(SHELL, "fundsxml/") == render_shell(SHELL, "fundsxml")


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text(SHELL)
    (tmp_path / "robots.txt").write_text("User-agent: *")
    app = FastAPI()
    mount_spa(app, tmp_path)
    return TestClient(app)


class TestSpaFallback:
    @pytest.mark.parametrize("path", ["/", "/paste", "/url", "/fundsxml", "/fundsxml/", "/api-docs"])
    def test_client_routes_serve_shell(self, client: TestClient, path: str) -> None:
        r = client.get(path)
        assert r.status_code == 200
        assert "shell" in r.text
        assert r.headers["content-type"].startswith("text/html")
        assert "Content-Security-Policy" in r.headers

    def test_served_shell_has_route_meta(self, client: TestClient) -> None:
        r = client.get("/fundsxml")
        assert "<title>FundsXML schema viewer" in r.text
        assert 'href="https://www.xsd-viewer.online/fundsxml"' in r.text

    @pytest.mark.parametrize(
        "path", ["/wp-login.php", "/wp-admin/js/", "/xleet.php", "/.well-known/", "/index.html"]
    )
    def test_probes_get_plain_404(self, client: TestClient, path: str) -> None:
        r = client.get(path)
        assert r.status_code == 404
        assert "shell" not in r.text
        assert r.headers["content-type"].startswith("text/plain")

    def test_api_404_is_json(self, client: TestClient) -> None:
        r = client.get("/api/nope")
        assert r.status_code == 404
        assert r.json() == {"error": "not_found"}

    def test_root_static_file_and_assets(self, client: TestClient) -> None:
        assert client.get("/robots.txt").text == "User-agent: *"
        assert client.get("/assets/app.js").status_code == 200

    def test_path_traversal_blocked(self, client: TestClient, tmp_path: Path) -> None:
        (tmp_path.parent / "secret.txt").write_text("x")
        assert client.get("/../secret.txt").status_code == 404
