"""Servidor HTTP interno do Agent, chamado somente pela API. Ver #17."""

import os

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="VX Materiais Agent", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AGENT_PORT", "8001")))
