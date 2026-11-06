"""Admissão sem fila e cancelamento cooperativo dos turnos, incluindo a limpeza do stdio."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import anyio

DEFAULT_MAX_CONCURRENT_TURNS = 2


def configured_limit() -> int:
    raw = os.environ.get("AGENT_MAX_CONCURRENT_TURNS", str(DEFAULT_MAX_CONCURRENT_TURNS))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError("AGENT_MAX_CONCURRENT_TURNS deve ser um inteiro positivo") from error
    if value <= 0:
        raise ValueError("AGENT_MAX_CONCURRENT_TURNS deve ser um inteiro positivo")
    return value


class AgentBusy(Exception):
    pass


class TurnCancelled(Exception):
    pass


@dataclass(eq=False)
class Turn:
    task: asyncio.Task | None = None
    scope: anyio.CancelScope | None = None
    cancelled: bool = False

    def cancel(self):
        self.cancelled = True
        if self.scope is not None:
            # O shield do SDK precisa continuar executando o fechamento dos pipes/processos.
            self.scope.cancel()

    async def finish(self):
        self.cancel()
        if self.task is not None:
            await asyncio.shield(asyncio.gather(self.task, return_exceptions=True))


class TurnManager:
    def __init__(self, limit: int):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("O limite de turnos deve ser um inteiro positivo")
        self.limit = limit
        self.active: set[Turn] = set()
        self.closing = False

    def start(self, execute: Callable[[], Awaitable[Any]]) -> Turn:
        # Executado no event loop sem await: verificar e reservar são uma operação só.
        if self.closing or len(self.active) >= self.limit:
            raise AgentBusy
        turn = Turn()

        async def owned():
            with anyio.CancelScope() as scope:
                turn.scope = scope
                if turn.cancelled:
                    raise TurnCancelled
                result = await execute()
            if scope.cancel_called:
                raise TurnCancelled
            return result

        self.active.add(turn)
        turn.task = asyncio.create_task(owned())
        turn.task.add_done_callback(lambda task: self.active.discard(turn))
        return turn

    async def close(self):
        self.closing = True
        turns = tuple(self.active)
        for turn in turns:
            turn.cancel()
        await asyncio.gather(*(turn.finish() for turn in turns))
