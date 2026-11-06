"""Mede carga real dentro do container Agent Linux, sem imprimir tokens ou credenciais.

Uso: docker compose exec -T agent python - --requests 8 < scripts/measure_agent.py
"""

import argparse
import asyncio
import json
import math
import os
import re
import statistics
import time
import uuid
from collections import Counter
from pathlib import Path, PurePosixPath

MESSAGE = "Preciso de parafuso sextavado M12x50, aço carbono, zincado branco, DIN 933."


def container_memory(proc_root=Path("/proc")):
    """Lê o cgroup do medidor no container, sem substituir por RSS ou pelo total do host."""
    result = {
        "container_memory_kib": None,
        "container_memory_source": None,
        "container_memory_unavailable_reason": "metadata_unreadable",
    }
    try:
        memberships = (proc_root / "self/cgroup").read_text().splitlines()
        mounts = (proc_root / "self/mountinfo").read_text().splitlines()
    except OSError:
        return result
    groups = {}
    for line in memberships:
        fields = line.split(":", 2)
        if len(fields) == 3:
            for controller in fields[1].split(","):
                groups[controller] = PurePosixPath(fields[2])
    result["container_memory_unavailable_reason"] = "no_matching_memory_cgroup"
    for line in mounts:
        before, _, after = line.partition(" - ")
        fields, filesystem = before.split(), after.split()
        if len(fields) < 5 or len(filesystem) < 3:
            continue
        if filesystem[0] == "cgroup2":
            controller, counter = "", "memory.current"
        elif filesystem[0] == "cgroup" and "memory" in filesystem[2].split(","):
            controller, counter = "memory", "memory.usage_in_bytes"
        else:
            continue
        group = groups.get(controller)
        if group is None or not group.is_absolute() or ".." in group.parts:
            continue
        root, mount = (re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), field) for field in fields[3:5])
        try:
            relative = group.relative_to(root)
        except ValueError:
            # Com namespace de cgroup, / identifica a raiz já montada do container.
            if group != PurePosixPath("/"):
                continue
            relative = PurePosixPath(".")
        source = Path(mount) / relative / counter
        result["container_memory_source"] = str(source)
        try:
            usage = int(source.read_text())
            if usage < 0:
                raise ValueError("negative counter")
        except OSError:
            result["container_memory_unavailable_reason"] = "counter_unreadable"
        except ValueError:
            result["container_memory_unavailable_reason"] = "counter_invalid"
        else:
            return {**result, "container_memory_kib": usage // 1024, "container_memory_unavailable_reason": None}
    return result


def peak_snapshot(samples):
    peak = {key: max(sample[key] for sample in samples) for key in ("processes", "mcp_processes", "rss_kib")}
    available = [sample for sample in samples if sample["container_memory_kib"] is not None]
    peak["container_memory_kib"] = max((sample["container_memory_kib"] for sample in available), default=None)
    peak["container_memory_sources"] = sorted({sample["container_memory_source"] for sample in available})
    peak["container_memory_unavailable_samples"] = len(samples) - len(available)
    return peak


def processes():
    result = {}
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit():
            continue
        try:
            fields = dict(line.split(":", 1) for line in (directory / "status").read_text().splitlines())
            result[int(directory.name)] = {
                "parent": int(fields["PPid"]),
                "rss_kib": int(fields.get("VmRSS", "0 kB").split()[0]),
                "command": (directory / "cmdline").read_bytes(),
            }
        except (OSError, KeyError, ValueError):
            continue
    return result


def snapshot(root):
    table = processes()
    selected = {root}
    while True:
        children = {pid for pid, row in table.items() if row["parent"] in selected}
        expanded = selected | children
        if expanded == selected:
            break
        selected = expanded
    metrics = {
        "processes": sum(pid in table for pid in selected),
        "mcp_processes": sum(b"vx_materials_mcp.server" in table[pid]["command"] for pid in selected if pid in table),
        "rss_kib": sum(table[pid]["rss_kib"] for pid in selected if pid in table),
    }
    return {**metrics, **container_memory()}


def payload(index):
    return {
        "turn_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "session_version": 0,
        "message": MESSAGE,
        "context": {
            "pdm_version": "pdm-kit-v1",
            "ncm_version": "ncm-demo-v1",
            "center_code": "1200",
            "history": [],
            "confirmed_attributes": {},
        },
    }


def headers(index):
    import jwt

    now = int(time.time())
    claims = {
        "iss": "vx-api",
        "aud": "vx-agent",
        "sub": f"load-{index}",
        "iat": now,
        "exp": now + 60,
        "permissions": ["chat:use", "inventory:read"],
        "center_codes": ["1200"],
    }
    token = jwt.encode(claims, os.environ["AGENT_INTERNAL_TOKEN_SECRET"], algorithm="HS256")
    return {"Authorization": f"Bearer {token}", "X-Request-ID": str(uuid.uuid4())}


async def measure(requests):
    roots = [pid for pid, row in processes().items() if b"/vx-agent" in row["command"] and pid != os.getpid()]
    if len(roots) != 1:
        raise RuntimeError("Execute dentro do container com exatamente um processo vx-agent")
    root = roots[0]
    baseline = snapshot(root)
    samples = [baseline]
    stop = asyncio.Event()

    async def monitor():
        while not stop.is_set():
            samples.append(snapshot(root))
            await asyncio.sleep(0.01)

    async def run(index):
        start = time.perf_counter()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(os.environ.get("AGENT_PORT", "8001")))
        try:
            data = json.dumps(payload(index)).encode()
            lines = [
                "POST /internal/v1/chat/run HTTP/1.1",
                "Host: agent",
                "Content-Type: application/json",
                "Connection: close",
                f"Content-Length: {len(data)}",
                *(f"{key}: {value}" for key, value in headers(index).items()),
                "",
                "",
            ]
            writer.write("\r\n".join(lines).encode() + data)
            await writer.drain()
            async with asyncio.timeout(30):
                status = int((await reader.readline()).split()[1])
                while await reader.readline() not in {b"\r\n", b""}:
                    pass
                response = json.loads(await reader.read())
            return status, response.get("error", {}).get("code"), time.perf_counter() - start
        finally:
            writer.close()
            await writer.wait_closed()

    monitoring = asyncio.create_task(monitor())
    try:
        responses = await asyncio.gather(*(run(index) for index in range(requests)))
        cancel = [asyncio.create_task(run(index)) for index in range(requests)]
        # Cancela durante a inicialização do stdio, em vez de esperar o resultado do turno.
        async with asyncio.timeout(5):
            while snapshot(root)["mcp_processes"] == 0 and not all(task.done() for task in cancel):
                await asyncio.sleep(0.005)
        cancelled = sum(not task.done() for task in cancel)
        for task in cancel:
            task.cancel()
        await asyncio.gather(*cancel, return_exceptions=True)
        async with asyncio.timeout(10):
            while snapshot(root)["mcp_processes"] != baseline["mcp_processes"]:
                await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)
    finally:
        stop.set()
        await monitoring
    after = snapshot(root)
    successful = sorted(duration for status, _, duration in responses if status == 200)
    result = {
        "limit_per_worker": int(os.environ.get("AGENT_MAX_CONCURRENT_TURNS", "2")),
        "parallel_requests": requests,
        "responses": dict(
            Counter(str(status) if code is None else f"{status}:{code}" for status, code, _ in responses)
        ),
        "successful_latency_seconds": {
            "p50": round(statistics.median(successful), 3) if successful else None,
            "p95": round(successful[math.ceil(0.95 * len(successful)) - 1], 3) if successful else None,
            "max": round(max(successful), 3) if successful else None,
        },
        "cancelled_requests": cancelled,
        "before": baseline,
        "peak": peak_snapshot(samples),
        "after": after,
        "rss_note": "Soma dos RSS do Agent e descendentes; páginas compartilhadas podem contar mais de uma vez.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if after["mcp_processes"] != baseline["mcp_processes"] or after["processes"] != baseline["processes"]:
        raise RuntimeError("A árvore de processos não voltou ao estado inicial")
    if result["peak"]["mcp_processes"] > result["limit_per_worker"]:
        raise RuntimeError("A concorrência ultrapassou o limite")
    if not successful:
        raise RuntimeError("Nenhum turno completou com sucesso")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=8)
    args = parser.parse_args()
    if args.requests < 1 or args.requests > 100:
        parser.error("requests deve estar entre 1 e 100")
    if not Path("/proc").is_dir():
        parser.error("Execute no container Linux do Agent")
    asyncio.run(measure(args.requests))


if __name__ == "__main__":
    main()
