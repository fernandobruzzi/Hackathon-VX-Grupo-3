"""Admissão e limpeza sob rajada, com subprocessos MCP reais e identidades distintas."""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp.client import stdio
from test_conversation_flow import BOLT, PDM, SECRET, token

from domain.pdm_loader import load_pdm
from vx_materials_mcp.app import create_app
from vx_materials_mcp.chatbot import mcp_client
from vx_materials_mcp.chatbot.turns import AgentBusy, TurnManager, configured_limit
from vx_materials_mcp.security import caller_to_environment

PATH = "/internal/v1/chat/run"


def body(center="1200"):
    return {
        "turn_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "session_version": 0,
        "message": BOLT,
        "context": {
            "pdm_version": "pdm-kit-v1",
            "ncm_version": "ncm-demo-v1",
            "center_code": center,
            "history": [],
            "confirmed_attributes": {},
        },
    }


def headers(user="user", center="1200"):
    return {"X-Request-ID": str(uuid.uuid4()), "Authorization": f"Bearer {token(sub=user, center_codes=[center])}"}


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(PDM)


@pytest.fixture
def spawned(monkeypatch):
    processes = []
    original = stdio._create_platform_compatible_process

    async def spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append((process, json.loads(kwargs["env"]["VX_CALLER"])))
        return process

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", spawn)
    yield processes
    assert all(process.returncode is not None for process, _ in processes)
    for process, _ in processes:
        with pytest.raises(ProcessLookupError):
            os.kill(process.pid, 0)


def held_connection(ready, release):
    @asynccontextmanager
    async def connect(caller):
        async with mcp_client.connect(PDM, caller=caller_to_environment(caller)) as client:
            ready.append(caller)
            await release.wait()
            yield client

    return connect


async def wait_ready(ready, count=1):
    # A partida real do MCP faz parte do teste; o foco é isolamento, não velocidade de importação.
    async with asyncio.timeout(20):
        while len(ready) < count:
            await asyncio.sleep(0.01)


def test_burst_rejects_excess_without_spawning_and_preserves_callers(catalog, spawned):
    async def exercise():
        ready, release = [], asyncio.Event()
        app = create_app(catalog, SECRET, held_connection(ready, release), max_concurrent_turns=2)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://agent") as client,
        ):
            first = [
                asyncio.create_task(client.post(PATH, json=body(center), headers=headers(user, center)))
                for user, center in [("alice", "1100"), ("bob", "1200")]
            ]
            await wait_ready(ready, 2)
            rejected = await asyncio.gather(*(client.post(PATH, json=body(), headers=headers()) for _ in range(12)))
            assert all(r.status_code == 503 and r.json()["error"]["code"] == "AGENT_BUSY" for r in rejected)
            assert all(r.headers["Retry-After"] == "1" for r in rejected)
            assert len(spawned) == 2
            assert {(caller["user_id"], tuple(caller["center_codes"])) for _, caller in spawned} == {
                ("alice", ("1100",)),
                ("bob", ("1200",)),
            }
            release.set()
            responses = await asyncio.gather(*first)
            assert all(r.status_code == 200 for r in responses)
            await asyncio.sleep(0)
            assert not app.state.turns.active

    asyncio.run(exercise())


def test_timeout_finishes_stdio_cleanup_before_releasing_capacity(catalog, spawned):
    async def exercise():
        ready, release = [], asyncio.Event()
        # O primeiro turno fica retido após o handshake, e o segundo precisa partir normalmente.
        app = create_app(catalog, SECRET, held_connection(ready, release), timeout_seconds=10, max_concurrent_turns=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://agent") as client:
            response = await client.post(PATH, json=body(), headers=headers())
            assert response.status_code == 503 and response.json()["error"]["code"] == "AGENT_TIMEOUT"
            assert ready  # O timeout também precisa cobrir o servidor já conectado.
            assert len(spawned) == 1 and spawned[0][0].returncode is not None
            assert not app.state.turns.active
            release.set()
            assert (await client.post(PATH, json=body(), headers=headers())).status_code == 200

    asyncio.run(exercise())


def test_http_disconnect_cancels_the_real_subprocess(catalog, spawned):
    async def exercise():
        ready, release = [], asyncio.Event()
        app = create_app(catalog, SECRET, held_connection(ready, release))
        inbox = asyncio.Queue()
        await inbox.put({"type": "http.request", "body": json.dumps(body()).encode(), "more_body": False})
        sent = []
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": PATH,
            "raw_path": PATH.encode(),
            "query_string": b"",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers().items()]
            + [(b"content-type", b"application/json")],
            "server": ("agent", 80),
            "client": ("test", 1),
        }

        async def send(message):
            sent.append(message)

        request = asyncio.create_task(app(scope, inbox.get, send))
        await wait_ready(ready)
        await inbox.put({"type": "http.disconnect"})
        await asyncio.wait_for(request, 5)
        assert next(m for m in sent if m["type"] == "http.response.start")["status"] == 499
        assert not app.state.turns.active

    asyncio.run(exercise())


def test_cancelled_http_task_still_reaps_the_mcp_process(catalog, spawned):
    async def exercise():
        ready, release = [], asyncio.Event()
        app = create_app(catalog, SECRET, held_connection(ready, release))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://agent") as client:
            request = asyncio.create_task(client.post(PATH, json=body(), headers=headers()))
            await wait_ready(ready)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            assert not app.state.turns.active

    asyncio.run(exercise())


def test_lifespan_shutdown_cancels_active_turns_and_rejects_new_ones(catalog, spawned):
    async def exercise():
        ready, release = [], asyncio.Event()
        app = create_app(catalog, SECRET, held_connection(ready, release))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://agent") as client:
            async with app.router.lifespan_context(app):
                request = asyncio.create_task(client.post(PATH, json=body(), headers=headers()))
                await wait_ready(ready)
            response = await request
            assert response.status_code == 503 and response.json()["error"]["code"] == "AGENT_STOPPING"
            response = await client.post(PATH, json=body(), headers=headers())
            assert response.status_code == 503 and len(spawned) == 1
            assert not app.state.turns.active

    asyncio.run(exercise())


@pytest.mark.parametrize("value", ["0", "-1", "2.5", "garbage", ""])
def test_invalid_environment_limit_fails_startup(monkeypatch, value):
    monkeypatch.setenv("AGENT_MAX_CONCURRENT_TURNS", value)
    with pytest.raises(ValueError, match="AGENT_MAX_CONCURRENT_TURNS"):
        configured_limit()


def test_default_and_configured_limit(monkeypatch):
    monkeypatch.delenv("AGENT_MAX_CONCURRENT_TURNS", raising=False)
    assert configured_limit() == 2
    monkeypatch.setenv("AGENT_MAX_CONCURRENT_TURNS", "3")
    assert configured_limit() == 3


def test_slot_is_held_until_cancelled_connection_finishes_cleanup():
    async def exercise():
        import anyio

        manager = TurnManager(1)
        entered, cleaned = asyncio.Event(), asyncio.Event()

        async def execute():
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                with anyio.CancelScope(shield=True):
                    await cleaned.wait()

        turn = manager.start(execute)
        await entered.wait()
        turn.cancel()
        with pytest.raises(AgentBusy):
            manager.start(execute)
        cleaned.set()
        await turn.finish()
        assert not manager.active

    asyncio.run(exercise())


def test_sigterm_of_http_server_reaps_its_separate_stdio_process(tmp_path):
    import signal
    import socket
    import subprocess
    import sys
    import time
    from pathlib import Path
    from urllib.request import urlopen

    if os.name != "posix":
        pytest.skip("SIGTERM e grupos POSIX são verificados no ambiente dos containers")
    pid_file = tmp_path / "child.json"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    fixture = Path(__file__).parent / "fixtures/holding_agent.py"
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen([sys.executable, str(fixture), str(port), str(pid_file)], stdout=log, stderr=log)
        mcp_pid = None
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.2) as response:
                        assert response.status == 200
                    break
                except OSError:
                    assert time.monotonic() < deadline and process.poll() is None
                    time.sleep(0.02)
            with socket.create_connection(("127.0.0.1", port)) as client:
                data = json.dumps(body()).encode()
                lines = [
                    f"POST {PATH} HTTP/1.1",
                    "Host: agent",
                    "Content-Type: application/json",
                    f"Content-Length: {len(data)}",
                    *(f"{key}: {value}" for key, value in headers().items()),
                    "",
                    "",
                ]
                client.sendall("\r\n".join(lines).encode() + data)
                deadline = time.monotonic() + 5
                while not pid_file.exists():
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
                mcp_pid = json.loads(pid_file.read_text())["pid"]
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=10)
            with pytest.raises(ProcessLookupError):
                os.kill(mcp_pid, 0)
            assert "Application shutdown complete" in (tmp_path / "server.log").read_text()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if mcp_pid is not None:
                try:
                    os.killpg(mcp_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def test_parallel_searches_keep_their_centers_and_financial_permissions(catalog, database, spawned):
    async def exercise():
        ready, release, results = [], asyncio.Event(), {}

        @asynccontextmanager
        async def connect(caller):
            async with mcp_client.connect(PDM, database["reader"], caller_to_environment(caller)) as client:
                ready.append(caller)
                await release.wait()

                class Capture:
                    async def call_tool(self, name, arguments):
                        result = await client.call_tool(name, arguments)
                        if name == "search_similar_materials":
                            results[caller.user_id] = result
                        return result

                yield Capture()

        app = create_app(catalog, SECRET, connect, max_concurrent_turns=2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://agent") as client:
            requests = []
            for user, centers, permissions in [
                ("requester", ["9999"], ["chat:use", "inventory:read"]),
                ("fiscal", ["1200"], ["chat:use", "inventory:read", "metrics:financial"]),
            ]:
                request = body(centers[0])
                request["message"] = "Preciso de filtro oleo lubrificante Fleetguard LF 9009"
                bearer = token(sub=user, center_codes=centers, permissions=permissions)
                requests.append(
                    asyncio.create_task(
                        client.post(
                            PATH, json=request, headers={"X-Request-ID": user, "Authorization": f"Bearer {bearer}"}
                        )
                    )
                )
            await wait_ready(ready, 2)
            release.set()
            responses = await asyncio.gather(*requests)
            for response, user, visible in zip(responses, ["requester", "fiscal"], [False, True], strict=True):
                assert response.status_code == 200, response.text
                entries = response.json()["material_card"]["existing"]["inventory"]
                assert bool(entries) == visible
                assert {row["center_code"] for row in entries} <= {"1200"}
                assert all("unit_price" not in row and "total_value" not in row for row in entries)
                raw = results[user]["candidates"][0]["inventory"]
                assert bool(raw) == visible
                if visible:
                    assert all(row.get("unit_price") is not None for row in raw)

    asyncio.run(exercise())
