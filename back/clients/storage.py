"""Armazenamento de arquivos. STORAGE_BACKEND escolhe entre pasta local e S3.

Os arquivos são imutáveis: repetir o mesmo conteúdo não faz nada, e conteúdo diferente na mesma
chave é um erro.
"""

import hashlib
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import boto3
from botocore.exceptions import ClientError

_SHA256_METADATA = "sha256"


@dataclass(frozen=True)
class StoredObject:
    key: str
    version_id: str | None = None


class ObjectConflictError(ValueError):
    """Já existe outro conteúdo nesta chave."""


class ObjectStore(Protocol):
    name: str

    def put_if_absent(self, key: str, content: bytes) -> StoredObject: ...

    def get(self, key: str) -> bytes: ...


class LocalObjectStore:
    name = "local"

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self._root = Path(root or os.environ.get("STORAGE_LOCAL_DIR", ".storage")).resolve()

    def put_if_absent(self, key: str, content: bytes) -> StoredObject:
        path = self._path(key)
        if path.exists():
            if path.read_bytes() != content:
                raise ObjectConflictError(f"Conteudo diferente em {key}")
            return StoredObject(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # O hard link publica o inode completo e nunca substitui uma chave existente.
        staged = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
        temporary = Path(staged.name)
        try:
            with staged:
                staged.write(content)
                staged.flush()
                os.fsync(staged.fileno())
            # Fecha antes de publicar e remover o temporário, inclusive no Windows.
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != content:
                    raise ObjectConflictError(f"Conteudo diferente em {key}") from None
        finally:
            temporary.unlink()
        return StoredObject(key)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"Chave fora do armazenamento: {key}")
        return path


class S3ObjectStore:
    name = "s3"

    def __init__(self, bucket: str | None = None, client=None) -> None:
        self._bucket = bucket or os.environ.get("S3_BUCKET")
        if not self._bucket:
            raise ValueError("Defina S3_BUCKET para usar STORAGE_BACKEND=s3")
        self._client = client or boto3.client("s3")

    def put_if_absent(self, key: str, content: bytes) -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] not in ("404", "NoSuchKey"):
                raise
        else:
            if head["Metadata"].get(_SHA256_METADATA) != digest:
                raise ObjectConflictError(f"Conteudo diferente em {key}")
            return StoredObject(key, head.get("VersionId"))
        for attempt in range(3):
            try:
                result = self._client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=content,
                    Metadata={_SHA256_METADATA: digest},
                    IfNoneMatch="*",
                )
                return StoredObject(key, result.get("VersionId"))
            except ClientError as error:
                code = error.response["Error"]["Code"]
                if code in ("409", "ConditionalRequestConflict") and attempt < 2:
                    continue
                if code not in ("412", "PreconditionFailed"):
                    raise
                head = self._client.head_object(Bucket=self._bucket, Key=key)
                if head["Metadata"].get(_SHA256_METADATA) != digest:
                    raise ObjectConflictError(f"Conteudo diferente em {key}") from None
                return StoredObject(key, head.get("VersionId"))
        raise AssertionError("Unreachable conditional write")

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()


BACKENDS: dict[str, Callable[[], ObjectStore]] = {
    LocalObjectStore.name: LocalObjectStore,
    S3ObjectStore.name: S3ObjectStore,
}


def get_object_store(name: str | None = None) -> ObjectStore:
    selected = name or os.environ.get("STORAGE_BACKEND") or LocalObjectStore.name
    try:
        factory = BACKENDS[selected]
    except KeyError:
        available = ", ".join(sorted(BACKENDS))
        raise ValueError(f"Armazenamento desconhecido: {selected!r}. Disponiveis: {available}") from None
    return factory()
