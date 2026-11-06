"""Substituição das propostas pendentes ao gravar uma execução (#115).

O comportamento no banco real, com duas execuções, está em `api/tests/test_superseded_proposals.py`,
onde ficam as migrações. Aqui só a ordem das chamadas: a substituição recebe apenas os ids recém-gravados.
"""

from types import SimpleNamespace

from repositories import batch_repository


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self.rows)


class FakeConnection:
    def __init__(self, existing):
        self.existing = existing
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if "FROM datasets" in sql:
            return FakeResult(["dataset-1"])
        if "INSERT INTO sanitization_proposals" in sql:
            return FakeResult([] if params["id"] in self.existing else [params["id"]])
        return FakeResult([])


def proposals(*ids):
    return [SimpleNamespace(id=proposal_id) for proposal_id in ids]


def run(monkeypatch, existing, ids):
    monkeypatch.setattr(batch_repository, "_proposal_row", lambda proposal, *_: {"id": proposal.id})
    connection = FakeConnection(existing)
    inserted = batch_repository.insert_proposals(connection, proposals(*ids), [], "tenant")
    supersede = [params for sql, params in connection.calls if "supersede_proposals" in sql]
    return inserted, supersede


def test_new_content_asks_to_supersede_only_the_new_ids(monkeypatch):
    inserted, supersede = run(monkeypatch, existing={"a"}, ids=["a", "b", "c"])
    assert inserted == 2
    assert supersede == [{"ids": ["b", "c"]}]


def test_same_content_again_supersedes_nothing(monkeypatch):
    inserted, supersede = run(monkeypatch, existing={"a", "b"}, ids=["a", "b"])
    assert (inserted, supersede) == (0, [])
