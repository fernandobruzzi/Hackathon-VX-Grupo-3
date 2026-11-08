"""Download somente do endpoint público oficial; sem fallback nem redirecionamento para outro destino."""

import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from domain.ncm_snapshot import (
    MAX_SNAPSHOT_BYTES,
    OFFICIAL_NCM_REDIRECT_URL,
    OFFICIAL_NCM_URL,
    NcmSnapshot,
    NcmSourceKind,
    load_ncm_snapshot,
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Segue apenas o redirecionamento do endereço publicado para o perfil público, uma vez."""

    max_redirections = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req is not None and req.full_url == OFFICIAL_NCM_URL and newurl == OFFICIAL_NCM_REDIRECT_URL:
            return super().redirect_request(req, fp, code, msg, headers, newurl)
        return None


def download_ncm_snapshot(*, version: str | None = None) -> tuple[NcmSnapshot, bytes]:
    # O arquivo é diário no fuso do órgão publicador. Se a captura cruzar a
    # meia-noite e o cabeçalho ainda não acompanhar, a validação rejeita a carga.
    captured = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    request = urllib.request.Request(OFFICIAL_NCM_URL, headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=30) as response:
        raw = response.read(MAX_SNAPSHOT_BYTES + 1)
    return load_ncm_snapshot(
        raw,
        snapshot_date=captured,
        version=version,
        source_kind=NcmSourceKind.OFFICIAL_DOWNLOAD,
    ), raw
