"""CLI independente para preparar snapshots antes da integração fiscal (#22)."""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from clients.ncm_download import download_ncm_snapshot
from clients.ncm_snapshot_store import NcmSnapshotStore
from clients.storage import get_object_store
from domain.ncm_snapshot import NcmSourceKind, check_snapshot_ncm, load_ncm_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m clients.ncm_snapshot_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="Baixa o JSON oficial por HTTPS e registra snapshot")
    download.add_argument("--version")
    load = commands.add_parser("import-file", help="Importa JSON local, sempre com procedencia nao verificada")
    load.add_argument("path", type=Path)
    load.add_argument("--snapshot-date", type=date.fromisoformat, required=True)
    load.add_argument("--version")
    load.add_argument("--simulated", action="store_true", help="Identifica fixture sintetica explicitamente")
    check = commands.add_parser("check", help="Confere existencia/vigencia; nao aprova alteracao fiscal")
    check.add_argument("version")
    check.add_argument("code")
    args = parser.parse_args(argv)
    store = NcmSnapshotStore(get_object_store())
    if args.command == "check":
        result = asdict(check_snapshot_ncm(store.load(args.version), args.code))
    else:
        if args.command == "download":
            snapshot, raw = download_ncm_snapshot(version=args.version)
        else:
            raw = args.path.read_bytes()
            snapshot = load_ncm_snapshot(
                raw,
                snapshot_date=args.snapshot_date,
                version=args.version,
                source_kind=NcmSourceKind.SIMULATED if args.simulated else NcmSourceKind.IMPORTED_UNVERIFIED,
            )
        result = store.register(snapshot, raw)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
