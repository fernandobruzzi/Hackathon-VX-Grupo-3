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


def test_front_trailing_slash_redirect_stays_on_the_browser_domain(tmp_path):
    # Atrás do CloudFront, o Host que chega é o do Express; um redirect absoluto
    # mandaria o navegador para fora do domínio próprio, onde o login não vale.
    (tmp_path / "index.html").write_text("<h1>front</h1>")
    (tmp_path / "saneamento" / "revisao").mkdir(parents=True)
    (tmp_path / "saneamento" / "revisao" / "index.html").write_text("<h1>revisao</h1>")
    client = TestClient(create_app(tmp_path), base_url="http://express-origin.internal")
    response = client.get("/saneamento/revisao?id=abc", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/saneamento/revisao/?id=abc"
    assert client.get("/saneamento/revisao/?id=abc").text == "<h1>revisao</h1>"
