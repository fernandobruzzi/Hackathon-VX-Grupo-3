import pytest
from fastapi.testclient import TestClient

from vx_materials_api.main import create_app


def test_healthz():
    assert TestClient(create_app()).get("/api/v1/healthz").json() == {"status": "ok"}


def test_api_rejects_simulated_client_at_startup(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "simulated_v1")
    with pytest.raises(RuntimeError, match="simulated_v1"):
        create_app()


def test_serves_front_build_without_hiding_api(tmp_path):
    (tmp_path / "index.html").write_text("<h1>front</h1>")
    client = TestClient(create_app(tmp_path))
    assert client.get("/").text == "<h1>front</h1>"
    assert client.get("/api/v1/healthz").json() == {"status": "ok"}
