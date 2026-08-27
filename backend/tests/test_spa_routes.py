"""SPA shell is served only for known client routes; probes get a 404."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.spa import SPA_ROUTES, is_spa_route, mount_spa


class TestIsSpaRoute:
    @pytest.mark.parametrize("path", ["", "paste", "url", "fundsxml", "fundsxml/", "paste//"])
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
        assert frozenset({"", "paste", "url", "fundsxml"}) == SPA_ROUTES


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<html>shell</html>")
    (tmp_path / "robots.txt").write_text("User-agent: *")
    app = FastAPI()
    mount_spa(app, tmp_path)
    return TestClient(app)


class TestSpaFallback:
    @pytest.mark.parametrize("path", ["/", "/paste", "/url", "/fundsxml", "/fundsxml/"])
    def test_client_routes_serve_shell(self, client: TestClient, path: str) -> None:
        r = client.get(path)
        assert r.status_code == 200
        assert "shell" in r.text
        assert r.headers["content-type"].startswith("text/html")
        assert "Content-Security-Policy" in r.headers

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
