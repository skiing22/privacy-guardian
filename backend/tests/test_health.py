from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def client(data: Path, static_dir: Path | None = None, threads: bool = False) -> TestClient:
    s = Settings(data_dir=data, static_dir=static_dir or Path("/nonexistent"))
    return TestClient(create_app(s, start_threads=threads))


def test_health_is_503_until_model_ready(tmp_path: Path) -> None:
    with client(tmp_path) as c:
        res = c.get("/health")
        assert res.status_code == 503
        body = res.json()
        assert body["model_ready"] is False and body["error"]["code"] == "model_not_ready"
        assert res.headers["cache-control"] == "no-store"
        c.app.state.container.model_ready.set()  # type: ignore[attr-defined]
        res = c.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "model_ready": True, "version": res.json()["version"]}


def test_unknown_api_path_uses_error_format(tmp_path: Path) -> None:
    with client(tmp_path) as c:
        res = c.get("/api/v1/nothing-here")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_spa_fallback_serves_index_for_client_routes(tmp_path: Path) -> None:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "assets" / "a.js").write_text("x")
    (static / "favicon.svg").write_text("<svg/>")
    with client(tmp_path / "data", static) as c:
        assert c.get("/scans/123").text == "<html>app</html>"
        assert c.get("/assets/a.js").text == "x"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert c.get("/../../etc/passwd").text == "<html>app</html>"  # never leaves static_dir
        assert c.get("/api/v1/x").status_code == 404  # API paths never fall back to the SPA
