import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import HTTPError

import pytest

from clients.ncm_download import _NoRedirect, download_ncm_snapshot
from clients.ncm_snapshot_cli import main
from clients.ncm_snapshot_store import NcmSnapshotStore
from clients.storage import LocalObjectStore, ObjectConflictError
from domain.ncm_snapshot import (
    MAX_SNAPSHOT_BYTES,
    OFFICIAL_NCM_URL,
    NcmSnapshotError,
    NcmSourceKind,
    check_snapshot_ncm,
    load_ncm_snapshot,
)

SNAPSHOT_DATE = date(2026, 11, 6)
FIXTURE = Path(__file__).parent / "fixtures/ncm_simulated.json"
RAW = FIXTURE.read_bytes()


def load(raw=RAW, **kwargs):
    return load_ncm_snapshot(raw, snapshot_date=SNAPSHOT_DATE, **kwargs)


def test_registers_original_bytes_version_date_and_readonly_records():
    snapshot = load(source_kind=NcmSourceKind.SIMULATED)
    assert snapshot.version.startswith("ncm-2026-11-06-")
    assert snapshot.source_sha256 == hashlib.sha256(RAW).hexdigest()
    assert snapshot.snapshot_date == SNAPSHOT_DATE
    assert snapshot.source_kind is NcmSourceKind.SIMULATED
    assert len(snapshot.records) == 4
    assert "0101.21.00" in snapshot.records
    with pytest.raises(TypeError):
        snapshot.records["7318.15.00"] = None
    assert load(b"\xef\xbb\xbf" + RAW).source_sha256 != snapshot.source_sha256


@pytest.mark.parametrize(
    ("code", "exists", "valid", "reason"),
    [
        ("73181500", True, True, None),
        ("7318.16.00", True, True, None),
        ("8482.10.10", True, False, "NCM_NOT_EFFECTIVE_IN_SNAPSHOT"),
        ("0101.21.00", True, False, "NCM_NOT_EFFECTIVE_IN_SNAPSHOT"),
        ("9999.99.99", False, False, "NCM_NOT_IN_SNAPSHOT"),
        ("73", False, False, "NCM_INVALID_FORMAT"),
        (None, False, False, "NCM_INVALID_FORMAT"),
        ("", False, False, "NCM_INVALID_FORMAT"),
    ],
)
def test_existence_and_inclusive_validity_at_recorded_date(code, exists, valid, reason):
    # OFFICIAL_DOWNLOAD aqui simula somente a origem do transporte de teste.
    snapshot = load(source_kind=NcmSourceKind.OFFICIAL_DOWNLOAD)
    result = check_snapshot_ncm(snapshot, code)
    assert result.input_ncm == code
    assert result.exists_in_snapshot is exists
    assert result.valid_in_snapshot is valid
    assert result.reasons == ((reason,) if reason else ())
    assert result.requires_fiscal_review is bool(reason)
    assert result.snapshot_date == SNAPSHOT_DATE
    assert result.ncm_version == snapshot.version
    assert result.source_sha256 == snapshot.source_sha256


def test_imported_and_simulated_sources_never_clear_fiscal_review():
    for kind in (NcmSourceKind.SIMULATED, NcmSourceKind.IMPORTED_UNVERIFIED):
        result = check_snapshot_ncm(load(source_kind=kind), "73181500")
        assert result.valid_in_snapshot
        assert result.requires_fiscal_review
        assert result.reasons == ("NCM_SOURCE_UNVERIFIED",)


def test_effectiveness_uses_snapshot_date_and_never_current_clock():
    payload = json.loads(RAW)
    payload["Data_Ultima_Atualizacao_NCM"] = "Vigente em 07/11/2026"
    snapshot = load_ncm_snapshot(json.dumps(payload).encode(), snapshot_date=date(2026, 11, 7))
    assert check_snapshot_ncm(snapshot, "01012100").valid_in_snapshot
    assert not check_snapshot_ncm(snapshot, "73181600").valid_in_snapshot


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(Nomenclaturas=[]),
        lambda p: p.update(Nomenclaturas={}),
        lambda p: p.update(Data_Ultima_Atualizacao_NCM="Vigente em 05/11/2026"),
        lambda p: p.update(Data_Ultima_Atualizacao_NCM="07/11/2026"),
        lambda p: p["Nomenclaturas"].append(p["Nomenclaturas"][-1]),
        lambda p: p["Nomenclaturas"][3].update(Data_Inicio="31/02/2026"),
        lambda p: p["Nomenclaturas"][3].update(Data_Fim="05/11/2026"),
        lambda p: p["Nomenclaturas"][3].update(Codigo=73181500),
        lambda p: p["Nomenclaturas"][3].update(Codigo="7318.BAD"),
        lambda p: p["Nomenclaturas"][3].update(Descricao=""),
        lambda p: p["Nomenclaturas"][3].pop("Data_Fim"),
        lambda p: p["Nomenclaturas"].append(None),
    ],
)
def test_bad_exports_fail_closed(mutate):
    payload = json.loads(RAW)
    mutate(payload)
    with pytest.raises(NcmSnapshotError):
        load(json.dumps(payload).encode())


@pytest.mark.parametrize("raw", [b"", b"<html>error</html>", b"[]", b"\xff", b"x" * (MAX_SNAPSHOT_BYTES + 1)])
def test_rejects_invalid_or_oversized_input(raw):
    with pytest.raises(NcmSnapshotError):
        load(raw)


@pytest.mark.parametrize("version", ["../outside", "", "a/b", "/absolute", "x" * 129])
def test_version_cannot_escape_storage(version):
    with pytest.raises(NcmSnapshotError):
        load(version=version)


def test_storage_roundtrip_is_idempotent_and_refuses_version_drift(tmp_path):
    store = NcmSnapshotStore(LocalObjectStore(tmp_path))
    snapshot = load(version="simulated-v1", source_kind=NcmSourceKind.SIMULATED)
    first = store.register(snapshot, RAW)
    assert first == store.register(snapshot, RAW)
    assert first["code_count"] == 4
    assert store.load(snapshot.version) == snapshot
    changed = RAW.replace(b"parafusos", b"PARAFUSOS")
    with pytest.raises(ObjectConflictError):
        store.register(load(changed, version=snapshot.version, source_kind=NcmSourceKind.SIMULATED), changed)
    with pytest.raises(ObjectConflictError):
        store.register(load(version=snapshot.version, source_kind=NcmSourceKind.OFFICIAL_DOWNLOAD), RAW)
    assert store.load(snapshot.version) == snapshot


def test_registry_revalidates_raw_and_detects_corruption(tmp_path):
    registry = NcmSnapshotStore(LocalObjectStore(tmp_path))
    snapshot = load()
    with pytest.raises(NcmSnapshotError, match="diverge"):
        registry.register(replace(snapshot, source_sha256="wrong"), RAW)
    registry.register(snapshot, RAW)
    (tmp_path / f"references/ncm/raw/{snapshot.source_sha256}.json").write_bytes(b"corrupted")
    with pytest.raises(NcmSnapshotError, match="Hash"):
        registry.load(snapshot.version)


def test_download_uses_fixed_https_endpoint_timeout_and_bounded_body(monkeypatch):
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = RAW
    monkeypatch.setattr("clients.ncm_download.urllib.request.build_opener", lambda handler: opener)
    clock = MagicMock()
    clock.now.return_value.date.return_value = SNAPSHOT_DATE
    monkeypatch.setattr("clients.ncm_download.datetime", clock)
    snapshot, raw = download_ncm_snapshot()
    assert raw == RAW
    assert snapshot.source_kind is NcmSourceKind.OFFICIAL_DOWNLOAD
    request = opener.open.call_args.args[0]
    assert request.full_url == OFFICIAL_NCM_URL
    assert opener.open.call_args.kwargs["timeout"] == 30
    opener.open.return_value.__enter__.return_value.read.assert_called_once_with(MAX_SNAPSHOT_BYTES + 1)
    assert _NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.org") is None


def test_download_failure_never_returns_a_fallback(monkeypatch):
    opener = MagicMock()
    opener.open.side_effect = HTTPError(OFFICIAL_NCM_URL, 403, "blocked", {}, None)
    monkeypatch.setattr("clients.ncm_download.urllib.request.build_opener", lambda handler: opener)
    with pytest.raises(HTTPError):
        download_ncm_snapshot()


def test_offline_cli_import_and_check_are_honest(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    assert (
        main(["import-file", str(FIXTURE), "--snapshot-date", "2026-11-06", "--version", "sim-v1", "--simulated"]) == 0
    )
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["source_kind"] == "SIMULATED"
    assert main(["check", "sim-v1", "73181500"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["normalized_ncm"] == "7318.15.00"
    assert result["requires_fiscal_review"]
    assert result["reasons"] == ["NCM_SOURCE_UNVERIFIED"]
