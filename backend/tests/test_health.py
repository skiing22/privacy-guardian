from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def client(static_dir: Path | None = None) -> TestClient:
    s = Settings(static_dir=static_dir or Path("/nonexistent"))
    return TestClient(create_app(s))


def test_health_shape() -> None:
    with client() as c:
        res = c.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok" and body["model_ready"] is False and body["version"]


def test_unknown_api_path_uses_error_format() -> None:
    with client() as c:
        res = c.get("/api/v1/nothing-here")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_spa_fallback_serves_index_for_client_routes(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "a.js").write_text("x")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    with client(tmp_path) as c:
        assert c.get("/scans/123").text == "<html>app</html>"
        assert c.get("/assets/a.js").text == "x"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert c.get("/../../etc/passwd").text == "<html>app</html>"  # never leaves static_dir
        assert c.get("/api/v1/x").status_code == 404  # API paths never fall back to the SPA
