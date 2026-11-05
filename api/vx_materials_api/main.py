"""Aplicacao FastAPI: rotas em /api/v1 e build do front na mesma origem."""

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vx_materials_api import settings


def create_app(front_dist: Path | None = None) -> FastAPI:
    app = FastAPI(title="VX Materiais API", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.get("/api/v1/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Montado por ultimo: as rotas da API tem prioridade sobre os arquivos estaticos.
    if front_dist:
        app.mount("/", StaticFiles(directory=front_dist, html=True), name="front")
    return app


app = create_app(settings.front_dist_dir())


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=settings.api_port())
