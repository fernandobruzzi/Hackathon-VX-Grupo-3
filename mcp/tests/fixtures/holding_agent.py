"""Agent de teste: abre MCP real e mantém o turno ativo para receber SIGTERM."""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from mcp.client import stdio

from domain.pdm_loader import load_pdm
from vx_materials_mcp.app import create_app
from vx_materials_mcp.chatbot import mcp_client
from vx_materials_mcp.security import caller_to_environment

PDM = str(Path(__file__).parents[3] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")
original = stdio._create_platform_compatible_process


async def spawn(*args, **kwargs):
    process = await original(*args, **kwargs)
    temporary = Path(sys.argv[2]).with_suffix(".tmp")
    temporary.write_text(json.dumps({"pid": process.pid}))
    temporary.replace(sys.argv[2])
    return process


stdio._create_platform_compatible_process = spawn


@asynccontextmanager
async def connect(caller):
    async with mcp_client.connect(PDM, caller=caller_to_environment(caller)) as client:
        await asyncio.sleep(60)
        yield client


app = create_app(load_pdm(PDM), "test-only-internal-secret-with-32-bytes", connect)
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), timeout_graceful_shutdown=0.1, access_log=False)
