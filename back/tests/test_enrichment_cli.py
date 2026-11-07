"""Comandos de enriquecimento preservam bytes e separação entre revisão e publicação."""

import json

from cli import main
from clients.storage import LocalObjectStore


def test_register_internal_sources_preserves_validated_bytes(tmp_path, monkeypatch, capsys):
    import cli

    content = json.dumps(
        {
            "schema_version": "internal-documents-v1",
            "dataset_id": "dataset",
            "documents": [{"id": "doc", "kind": "INTERNAL_DOCUMENT", "title": "Ficha", "text": "FILTRO"}],
        }
    ).encode()
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(content)
    store = LocalObjectStore(tmp_path / "storage")
    monkeypatch.setattr(cli, "get_object_store", lambda: store)
    assert main(["register-internal-sources", str(bundle), "--dataset-id", "dataset"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert store.get(result["object_key"]) == content


def test_packet_and_evaluate_commands_do_not_claim_unreviewed_precision(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"results": []}))
    assert main(["enrichment-review-packet", str(report)]) == 0
    packet = json.loads(capsys.readouterr().out)
    packet_file, reviews_file = tmp_path / "packet.json", tmp_path / "reviews.json"
    packet_file.write_text(json.dumps(packet))
    reviews_file.write_text(json.dumps({"packet_sha256": packet["packet_sha256"], "reviews": []}))
    assert main(["enrichment-evaluate", str(packet_file), str(reviews_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["authorizes_apply"] is False
    assert result["decided_precision"]["value"] is None
