from fastapi.testclient import TestClient

from domain.contracts import PdmCatalog
from vx_materials_mcp.app import create_app


def test_healthz():
    app = create_app(PdmCatalog(version="v", source_sha256="x", classes={}), "s" * 32, connect=None)
    assert TestClient(app).get("/healthz").json() == {"status": "ok"}


def test_shared_domain_package_is_importable():
    from domain.pdm_loader import DEFAULT_PDM_VERSION

    assert DEFAULT_PDM_VERSION == "pdm-kit-v1"
