import boto3
import pytest
from moto import mock_aws

from clients.storage import LocalObjectStore, ObjectConflictError, S3ObjectStore, get_object_store


@pytest.fixture(params=["local", "s3"])
def store(request, tmp_path):
    if request.param == "local":
        yield LocalObjectStore(tmp_path)
        return
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="kit")
        client.put_bucket_versioning(Bucket="kit", VersioningConfiguration={"Status": "Enabled"})
        yield S3ObjectStore("kit", client)


def test_stores_and_reads_back(store):
    stored = store.put_if_absent("raw/x/a.csv", b"conteudo")
    assert stored.key == "raw/x/a.csv"
    assert store.get("raw/x/a.csv") == b"conteudo"


def test_same_content_is_not_written_twice(store):
    first = store.put_if_absent("a", b"1")
    assert store.put_if_absent("a", b"1") == first


def test_different_content_on_same_key_is_rejected(store):
    store.put_if_absent("a", b"1")
    with pytest.raises(ObjectConflictError):
        store.put_if_absent("a", b"2")
    assert store.get("a") == b"1"


def test_s3_records_object_version():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="kit")
        client.put_bucket_versioning(Bucket="kit", VersioningConfiguration={"Status": "Enabled"})
        assert S3ObjectStore("kit", client).put_if_absent("a", b"1").version_id


def test_local_store_rejects_keys_outside_its_folder(tmp_path):
    with pytest.raises(ValueError, match="fora"):
        LocalObjectStore(tmp_path / "root").put_if_absent("../fora.txt", b"1")


def test_backend_comes_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    assert get_object_store().name == "local"
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "")
    with pytest.raises(ValueError, match="S3_BUCKET"):
        get_object_store()
    monkeypatch.setenv("STORAGE_BACKEND", "outro")
    with pytest.raises(ValueError, match="local, s3"):
        get_object_store()


@pytest.mark.parametrize("same_content", [False, True])
def test_concurrent_local_writers(tmp_path, monkeypatch, same_content):
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from threading import Barrier

    barrier = Barrier(2)
    original_exists = Path.exists
    target = tmp_path / "object"

    def exists(path):
        result = original_exists(path)
        if path == target and not result:
            barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(Path, "exists", exists)
    store = LocalObjectStore(tmp_path)
    contents = [b"a" * 100000, (b"a" if same_content else b"b") * 100000]

    def write(content):
        try:
            return store.put_if_absent("object", content)
        except ObjectConflictError:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, contents))
    assert sum(result is not None for result in results) == (2 if same_content else 1)
    assert store.get("object") in contents
    assert list(tmp_path.iterdir()) == [target]


def test_local_publishes_only_complete_file(tmp_path, monkeypatch):
    import os

    called = []
    original_link = os.link
    content = b"complete" * 10000

    def link(source, destination):
        assert not destination.exists()
        assert source.read_bytes() == content
        called.append(True)
        original_link(source, destination)
        assert destination.read_bytes() == content

    monkeypatch.setattr(os, "link", link)
    LocalObjectStore(tmp_path).put_if_absent("object", content)
    assert called


@pytest.mark.parametrize("operation", ["fsync", "link"])
def test_local_failure_leaves_no_partial_object_or_temporary(tmp_path, monkeypatch, operation):
    import os

    store = LocalObjectStore(tmp_path)

    def fail(*args):
        raise OSError("falha de armazenamento")

    with monkeypatch.context() as patch:
        patch.setattr(os, operation, fail)
        with pytest.raises(OSError, match="falha de armazenamento"):
            store.put_if_absent("object", b"conteudo")
    assert list(tmp_path.iterdir()) == []
    store.put_if_absent("object", b"conteudo")
    assert store.get("object") == b"conteudo"


@pytest.mark.parametrize("same_content", [False, True])
def test_concurrent_s3_writers(same_content):
    import hashlib
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock

    from botocore.exceptions import ClientError

    class Client:
        def __init__(self):
            self.barrier = Barrier(2)
            self.lock = Lock()
            self.saved = None
            self.puts = 0

        def head_object(self, **kwargs):
            if self.saved is None:
                raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
            return {"Metadata": self.saved["Metadata"], "VersionId": "winner"}

        def put_object(self, **kwargs):
            self.barrier.wait(timeout=5)
            with self.lock:
                self.puts += 1
                if self.saved is not None and kwargs.get("IfNoneMatch") == "*":
                    raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
                self.saved = kwargs
                return {"VersionId": "winner"}

    client = Client()
    store = S3ObjectStore("kit", client)
    contents = [b"a", b"a" if same_content else b"b"]

    def write(content):
        try:
            return store.put_if_absent("object", content)
        except ObjectConflictError:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, contents))
    assert sum(result is not None for result in results) == (2 if same_content else 1)
    assert client.saved["Body"] in contents
    assert client.saved["Metadata"]["sha256"] == hashlib.sha256(client.saved["Body"]).hexdigest()
    assert all(result.version_id == "winner" for result in results if result is not None)


def test_s3_retries_conditional_request_conflict():
    from unittest.mock import Mock

    from botocore.exceptions import ClientError

    client = Mock()
    client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
    client.put_object.side_effect = [
        ClientError({"Error": {"Code": "ConditionalRequestConflict"}}, "PutObject"),
        {"VersionId": "created"},
    ]
    result = S3ObjectStore("kit", client).put_if_absent("object", b"a")
    assert result.version_id == "created"
    assert client.put_object.call_count == 2
    assert all(call.kwargs["IfNoneMatch"] == "*" for call in client.put_object.call_args_list)


def test_s3_does_not_retry_unrelated_errors():
    from unittest.mock import Mock

    from botocore.exceptions import ClientError

    client = Mock()
    client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
    client.put_object.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
    with pytest.raises(ClientError, match="AccessDenied"):
        S3ObjectStore("kit", client).put_if_absent("object", b"a")
    assert client.put_object.call_count == 1
