"""Hash canonico compartilhado pelo produtor de propostas e pelo consumidor da API."""

import hashlib
import json


def canonical_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def proposal_hash(members: list[dict], changeset: dict, evidence_ids: list[str] | None = None) -> str:
    return canonical_hash({"members": members, "changeset": changeset, "evidence_ids": evidence_ids or []})
