import os
import tempfile
from pathlib import Path

import pytest

from clients.storage import LocalObjectStore


@pytest.mark.parametrize("failure", [None, "fsync", "link"])
def test_local_closes_staging_file_before_publish_and_cleanup(tmp_path, monkeypatch, failure):
    """Modela o compartilhamento do Windows, mantendo escritas reais no sistema de arquivos."""
    handles = []
    create = tempfile.NamedTemporaryFile
    original_link = os.link
    original_unlink = Path.unlink

    def create_staged(*args, **kwargs):
        staged = create(*args, **kwargs)
        handles.append(staged)
        return staged

    def require_closed():
        if any(not handle.closed for handle in handles):
            raise PermissionError("staging file still open")

    def link(source, destination):
        require_closed()
        if failure == "link":
            raise OSError("storage unavailable")
        return original_link(source, destination)

    def unlink(path, *args, **kwargs):
        require_closed()
        return original_unlink(path, *args, **kwargs)

    def fail_sync(*args):
        raise OSError("storage unavailable")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", create_staged)
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(Path, "unlink", unlink)
    if failure == "fsync":
        monkeypatch.setattr(os, "fsync", fail_sync)

    store = LocalObjectStore(tmp_path)
    if failure:
        with pytest.raises(OSError, match="storage unavailable"):
            store.put_if_absent("object", b"complete")
        assert list(tmp_path.iterdir()) == []
    else:
        store.put_if_absent("object", b"complete")
        assert store.get("object") == b"complete"
        assert list(tmp_path.iterdir()) == [tmp_path / "object"]
