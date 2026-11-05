from fastapi.testclient import TestClient

from vx_materials_mcp.app import app


def test_healthz():
    assert TestClient(app).get("/healthz").json() == {"status": "ok"}


def test_shared_domain_package_is_importable():
    from domain.pdm_loader import DEFAULT_PDM_VERSION

    assert DEFAULT_PDM_VERSION == "pdm-kit-v1"
