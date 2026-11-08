"""Saída estruturada da recuperação de contexto, independente da decisão de domínio."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RagContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["rag_context_v1"]
    context_id: str
    query_sha256: str
    scope_sha256: str
    pdm_version: str
    pdm_source_sha256: str
    retrieval: str
    repository: str
    index_version: str | None
    ncm_status: Literal["OFFICIAL_SNAPSHOT", "UNAVAILABLE"]
    items: list[dict[str, Any]]
    sources: list[dict[str, str]]
    truncated: bool
    notice: str
