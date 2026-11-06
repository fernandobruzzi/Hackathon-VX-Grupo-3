from dataclasses import replace
from pathlib import Path

import pytest

from domain.pdm_loader import load_pdm
from pipelines import sanitize
from pipelines.search_index import index_version
from repositories import classification, extraction
from repositories.embeddings.simulated_v1 import SimulatedV1EmbeddingRepository

KIT = Path(__file__).parents[2] / "data" / "desafio01" / "03_padrao_cadastro_PDM.xlsx"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT)


@pytest.fixture()
def repositories(catalog):
    return classification.get_classification_repository(catalog), extraction.get_extraction_repository()


def test_same_rules_give_the_same_version(catalog, repositories):
    assert index_version(catalog, *repositories) == index_version(load_pdm(KIT), *repositories)


def test_pdm_content_changes_the_version_even_with_the_same_label(catalog, repositories):
    edited = replace(catalog, source_sha256="0" * 64)
    assert edited.version == catalog.version
    assert index_version(edited, *repositories) != index_version(catalog, *repositories)


def test_classifier_revision_changes_the_version_with_the_same_name(catalog, repositories):
    classifier, extractor = repositories

    class Revised(type(classifier)):
        revision = classifier.revision + "-revisada"

    assert Revised.name == classifier.name
    assert index_version(catalog, Revised(catalog), extractor) != index_version(catalog, classifier, extractor)


def test_extractor_revision_changes_the_version_with_the_same_name(catalog, repositories):
    classifier, extractor = repositories

    class Revised(type(extractor)):
        revision = extractor.revision + "-revisada"

    assert Revised.name == extractor.name
    assert index_version(catalog, classifier, Revised()) != index_version(catalog, classifier, extractor)


def test_identity_rules_revision_changes_the_version(catalog, repositories, monkeypatch):
    before = index_version(catalog, *repositories)
    monkeypatch.setattr(sanitize, "IDENTITY_RULES_VERSION", "identity-revisada")
    assert index_version(catalog, *repositories) != before


def test_embedding_signature_changes_the_version(catalog, repositories):
    plain = index_version(catalog, *repositories)
    simulated = index_version(catalog, *repositories, SimulatedV1EmbeddingRepository().signature)
    assert plain != simulated
    assert simulated.endswith("simulated_v1:hashing-trigrams-v1:512")


# Contrato: todo algoritmo registrado declara uma revisão, inclusive os futuros.
@pytest.mark.parametrize("name", sorted(classification.REPOSITORIES))
def test_every_classifier_declares_a_revision(catalog, name):
    assert classification.REPOSITORIES[name](catalog).revision


@pytest.mark.parametrize("name", sorted(extraction.REPOSITORIES))
def test_every_extractor_declares_a_revision(name):
    assert extraction.REPOSITORIES[name]().revision


def test_index_uses_current_approved_attributes_even_without_canonical_flag(catalog, repositories):
    from domain.contracts import MaterialRecord
    from pipelines.search_index import analyze_source
    from repositories.batch_repository import SearchSource

    source = SearchSource(
        MaterialRecord("1", "ATIVO", "FILTRO OLEO FLEETGUARD LF9009"),
        "PDM100",
        {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9999"},
    )
    current = analyze_source(source, catalog, *repositories)
    assert current.attributes["REFERENCIA FABRICANTE"] == "LF9999"
    assert "LF9999" in current.identity_key
    assert "LF9009" not in current.identity_key
    assert source.record.description == "FILTRO OLEO FLEETGUARD LF9009"


def test_watch_retries_failures_without_claiming_a_pending_index_is_ready(monkeypatch, tmp_path, capsys):
    from pipelines import search_index

    ready = tmp_path / "ready"
    monkeypatch.setattr(search_index, "Path", lambda path: ready)
    attempts = iter(
        [RuntimeError("sensitive connection details"), {"pending": 1, "written": 0}, {"pending": 0, "written": 1}]
    )
    states = []

    def run(*args, **kwargs):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    def pause(seconds):
        assert seconds == 2
        states.append(ready.exists())
        if len(states) == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(search_index, "run_index", run)
    monkeypatch.setattr(search_index.time, "sleep", pause)
    with pytest.raises(KeyboardInterrupt):
        search_index.watch_index()
    assert states == [False, False, True]
    captured = capsys.readouterr()
    assert "INDEX_REFRESH_FAILED" in captured.err
    assert "sensitive connection details" not in captured.err


def test_partial_approved_unknown_value_does_not_reuse_an_old_inferred_identity(catalog, repositories):
    from domain.contracts import MaterialRecord
    from pipelines.search_index import analyze_source
    from repositories.batch_repository import SearchSource

    source = SearchSource(
        MaterialRecord("1", "ATIVO", "FILTRO OLEO FLEETGUARD LF9009"),
        "PDM100",
        {
            "FABRICANTE": "FLEETGUARD",
            "REFERENCIA FABRICANTE": None,
        },
    )
    current = analyze_source(source, catalog, *repositories)
    assert "REFERENCIA FABRICANTE" not in current.attributes
    assert current.identity_key is None
