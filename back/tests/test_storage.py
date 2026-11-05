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
