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
    OFFICIAL_NCM_REDIRECT_URL,
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
        ("٧٣١٨١٥٠٠", False, False, "NCM_INVALID_FORMAT"),
        ("７３１８１５００", False, False, "NCM_INVALID_FORMAT"),
        (None, False, False, "NCM_INVALID_FORMAT"),
        ("", False, False, "NCM_INVALID_FORMAT"),
    ],
)
def test_existence_and_inclusive_validity_at_recorded_date(code, exists, valid, reason):
    # OFFICIAL_DOWNLOAD aqui simula somente a origem do transporte de teste.
    snapshot = load(source_kind=NcmSourceKind.OFFICIAL_DOWNLOAD)
    result = check_snapshot_ncm(snapshot, code)
    assert result.input_ncm == code
    assert result.syntax_valid is (reason != "NCM_INVALID_FORMAT")
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
        lambda p: p["Nomenclaturas"][3].update(Codigo="73.1"),
        lambda p: p["Nomenclaturas"][3].update(Codigo="731.8"),
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


def test_download_follows_only_the_public_profile_redirect_of_the_official_url():
    from urllib.request import Request

    handler = _NoRedirect()
    official = Request(OFFICIAL_NCM_URL, headers={"Accept": "application/json"})
    followed = handler.redirect_request(official, None, 307, "", {}, OFFICIAL_NCM_REDIRECT_URL)
    assert followed is not None and followed.full_url == OFFICIAL_NCM_REDIRECT_URL
    assert handler.max_redirections == 1
    for target in (
        "https://example.org/ncm.json",
        "http://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO",
        f"{OFFICIAL_NCM_URL}?perfil=OUTRO",
        f"{OFFICIAL_NCM_REDIRECT_URL}&extra=1",
    ):
        assert handler.redirect_request(official, None, 307, "", {}, target) is None
    # Um redirecionamento a partir de outro endereço nunca é seguido, nem para o destino esperado.
    other = Request("https://example.org/ncm.json")
    assert handler.redirect_request(other, None, 307, "", {}, OFFICIAL_NCM_REDIRECT_URL) is None


def test_official_export_shape_loads_positions_items_and_extra_fields():
    raw = (Path(__file__).parent / "fixtures/ncm_official_excerpt.json").read_bytes()
    snapshot = load_ncm_snapshot(raw, snapshot_date=date(2026, 11, 8))
    assert snapshot.source_kind is NcmSourceKind.IMPORTED_UNVERIFIED
    assert snapshot.source_last_update == "Vigente em 08/11/2026"
    assert set(snapshot.records) == {"0102.29.11", "7318.15.00", "7318.16.00", "8482.10.10"}
    # Posições "73.18" e itens de sete dígitos ficam só na hierarquia.
    assert {"73", "7318", "73181", "0102291", "848210"} <= set(snapshot.hierarchy)
    check = check_snapshot_ncm(snapshot, "73181500")
    assert check.exists_in_snapshot and check.valid_in_snapshot
    assert check.reasons == ("NCM_SOURCE_UNVERIFIED",)
    assert check_snapshot_ncm(snapshot, "7318.15").reasons[0] == "NCM_INVALID_FORMAT"
    assert check_snapshot_ncm(snapshot, "73181900").reasons[0] == "NCM_NOT_IN_SNAPSHOT"


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


@pytest.fixture
def catalog():
    from domain.pdm_loader import load_pdm

    return load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")


@pytest.mark.parametrize("kind", list(NcmSourceKind))
def test_consistency_combines_snapshot_and_pdm_without_promoting_imports(catalog, kind):
    from domain.ncm_rules import check_ncm_consistency

    snapshot = load(source_kind=kind)
    result = check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00", snapshot=snapshot)
    assert result.technical_consistency == "CONSISTENT"
    assert result.exists_in_snapshot and result.valid_in_snapshot
    assert result.requires_fiscal_review is (kind is not NcmSourceKind.OFFICIAL_DOWNLOAD)
    assert result.ncm_source_sha256 == snapshot.source_sha256
    assert result.ncm_snapshot_date == "2026-11-06"
    assert result.ncm_source_kind == kind.value
    if kind is not NcmSourceKind.OFFICIAL_DOWNLOAD:
        assert "NCM_SOURCE_UNVERIFIED" in result.pending_checks
    # Existência/vigência não removem a inconsistência técnica.
    assert check_ncm_consistency(catalog, "PDM003", {}, "7318.15.00", snapshot=snapshot).requires_fiscal_review


@pytest.mark.parametrize("absent", [False, True])
def test_consistent_pdm_code_still_requires_review_if_absent_or_expired(catalog, absent):
    from domain.ncm_rules import check_ncm_consistency

    payload = json.loads(RAW)
    row = next(r for r in payload["Nomenclaturas"] if r["Codigo"] == "7318.16.00")
    row.update({"Codigo": "9999.99.99"} if absent else {"Data_Fim": "05/11/2026"})
    snapshot = load(json.dumps(payload).encode(), source_kind=NcmSourceKind.OFFICIAL_DOWNLOAD)
    result = check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00", snapshot=snapshot)
    assert result.technical_consistency == "CONSISTENT"
    assert result.exists_in_snapshot is not absent
    assert not result.valid_in_snapshot
    assert result.requires_fiscal_review
    assert result.fiscal_approval_status == "PENDING"


def test_every_snapshot_identity_field_is_bound_to_evaluation_hash(catalog):
    from domain.ncm_rules import check_ncm_consistency

    snapshot = load()
    first = check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00", snapshot=snapshot)
    for changed in (
        replace(snapshot, version="new-version"),
        replace(snapshot, source_sha256="0" * 64),
        replace(snapshot, snapshot_date=date(2026, 11, 7)),
        replace(snapshot, source_kind=NcmSourceKind.SIMULATED),
    ):
        result = check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00", snapshot=changed)
        assert result.evaluation_hash != first.evaluation_hash
    with pytest.raises(ValueError, match="indisponível"):
        check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00", snapshot=snapshot, ncm_version="different")


def test_server_configuration_pins_one_version_and_fails_closed(monkeypatch, tmp_path):
    from clients.ncm_snapshot_store import load_configured_ncm_snapshot

    monkeypatch.delenv("NCM_SNAPSHOT_VERSION", raising=False)
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    assert load_configured_ncm_snapshot() is None
    with pytest.raises(NcmSnapshotError):
        load_configured_ncm_snapshot("client-picked-version")
    snapshot = load(version="configured")
    NcmSnapshotStore(LocalObjectStore(tmp_path)).register(snapshot, RAW)
    monkeypatch.setenv("NCM_SNAPSHOT_VERSION", snapshot.version)
    assert load_configured_ncm_snapshot(snapshot.version) == snapshot
    with pytest.raises(NcmSnapshotError):
        load_configured_ncm_snapshot("other")
    monkeypatch.setenv("NCM_SNAPSHOT_VERSION", "missing")
    with pytest.raises(NcmSnapshotError, match="configurado indisponível"):
        load_configured_ncm_snapshot()


def test_snapshot_review_reason_is_separate_from_a_possible_format_change(catalog):
    from dataclasses import asdict

    from domain.ncm_rules import check_ncm_consistency, requires_snapshot_fiscal_review

    snapshot = load(source_kind=NcmSourceKind.OFFICIAL_DOWNLOAD)
    result = check_ncm_consistency(catalog, "PDM003", {}, "73181600", snapshot=snapshot)
    assert result.requires_fiscal_review  # Normalizar essa grafia seria uma alteração.
    assert not requires_snapshot_fiscal_review(asdict(result))
    unverified = check_ncm_consistency(catalog, "PDM003", {}, "73181600", snapshot=load())
    assert requires_snapshot_fiscal_review(asdict(unverified))
