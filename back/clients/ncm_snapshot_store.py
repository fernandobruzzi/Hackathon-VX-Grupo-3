"""Registro imutável de snapshots NCM no ObjectStore local ou S3 já existente."""

import hashlib
import json
import os
import re
from datetime import date

from clients.storage import ObjectStore, get_object_store
from domain.ncm_snapshot import (
    OFFICIAL_NCM_URL,
    NcmSnapshot,
    NcmSnapshotError,
    NcmSourceKind,
    load_ncm_snapshot,
    validate_ncm_version,
)


class NcmSnapshotStore:
    def __init__(self, store: ObjectStore) -> None:
        self._store = store

    def register(self, snapshot: NcmSnapshot, raw: bytes) -> dict:
        validated = load_ncm_snapshot(
            raw,
            snapshot_date=snapshot.snapshot_date,
            version=snapshot.version,
            source_kind=snapshot.source_kind,
        )
        if snapshot != validated:
            raise NcmSnapshotError("Snapshot diverge do arquivo original")
        key = f"references/ncm/raw/{snapshot.source_sha256}.json"
        manifest = {
            "format": "ncm_snapshot_v1",
            "version": snapshot.version,
            "source_sha256": snapshot.source_sha256,
            "snapshot_date": snapshot.snapshot_date.isoformat(),
            "source_kind": snapshot.source_kind.value,
            "source_url": OFFICIAL_NCM_URL if snapshot.source_kind is NcmSourceKind.OFFICIAL_DOWNLOAD else None,
            "source_last_update": snapshot.source_last_update,
            "raw_key": key,
            "code_count": len(snapshot.records),
        }
        self._store.put_if_absent(key, raw)
        self._store.put_if_absent(
            f"references/ncm/versions/{snapshot.version}.json",
            json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        )
        return manifest

    def load(self, version: str) -> NcmSnapshot:
        validate_ncm_version(version)
        manifest = json.loads(self._store.get(f"references/ncm/versions/{version}.json"))
        if manifest.get("format") != "ncm_snapshot_v1" or manifest.get("version") != version:
            raise NcmSnapshotError("Manifesto NCM invalido")
        digest = manifest["source_sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise NcmSnapshotError("Hash do manifesto NCM invalido")
        expected_url = OFFICIAL_NCM_URL if manifest["source_kind"] == NcmSourceKind.OFFICIAL_DOWNLOAD else None
        if manifest["source_url"] != expected_url:
            raise NcmSnapshotError("Procedencia do manifesto NCM invalida")
        key = f"references/ncm/raw/{digest}.json"
        if manifest["raw_key"] != key:
            raise NcmSnapshotError("Chave do arquivo NCM diverge do hash")
        raw = self._store.get(key)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise NcmSnapshotError("Hash NCM diverge do arquivo armazenado")
        snapshot = load_ncm_snapshot(
            raw,
            snapshot_date=date.fromisoformat(manifest["snapshot_date"]),
            version=version,
            source_kind=manifest["source_kind"],
        )
        if (
            manifest["code_count"] != len(snapshot.records)
            or manifest["source_last_update"] != snapshot.source_last_update
        ):
            raise NcmSnapshotError("Manifesto NCM diverge do arquivo armazenado")
        return snapshot


def load_configured_ncm_snapshot(requested_version: str | None = None) -> NcmSnapshot | None:
    """Uma referência do servidor para batch, MCP e API; não escolhe versão pelo cliente."""
    version = os.environ.get("NCM_SNAPSHOT_VERSION") or None
    if requested_version is not None and requested_version != version:
        raise NcmSnapshotError(f"Snapshot oficial NCM indisponível: {requested_version}")
    if version is None:
        return None
    try:
        return NcmSnapshotStore(get_object_store()).load(version)
    except Exception as error:
        # Falha de rede, integridade ou configuração nunca vira ausência silenciosa.
        raise NcmSnapshotError(f"Snapshot NCM configurado indisponível: {version}") from error
