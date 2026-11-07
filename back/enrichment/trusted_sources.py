"""Consulta HTTPS limitada a fontes selecionadas pelo servidor, com proteção contra SSRF."""

import hashlib
import http.client
import io
import ipaddress
import queue
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from urllib.parse import urljoin, urlsplit


class SourceError(ValueError):
    """Fonte recusada ou indisponível: o atributo deve continuar pendente."""


@dataclass(frozen=True)
class SourceSpec:
    id: str
    url: str
    title: str
    allowed_hosts: tuple[str, ...]
    kind: str = "MANUFACTURER"


@dataclass(frozen=True)
class FetchLimits:
    max_bytes: int = 2_000_000
    max_redirects: int = 2
    io_timeout: float = 4
    total_timeout: float = 12

    def __post_init__(self):
        if self.max_bytes <= 0 or self.max_redirects < 0 or self.io_timeout <= 0 or self.total_timeout <= 0:
            raise ValueError("Limites de consulta inválidos")


@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    url: str
    content: bytes
    content_type: str
    retrieved_at: str
    simulated: bool = False

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def validate_url(url: str, allowed_hosts: tuple[str, ...]):
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in allowed_hosts
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
            and not any(ord(char) <= 32 or ord(char) == 127 for char in url)
            and "\\" not in url
        )
    except ValueError:
        valid = False
    if not valid:
        raise SourceError("URL fora da política da fonte")
    return parsed


def resolve_public(host: str, timeout: float) -> str:
    """Resolve uma vez e fixa o IP público na conexão; o prazo também cobre o DNS."""
    results = queue.Queue(maxsize=1)

    def resolve():
        try:
            results.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
        except OSError as error:
            results.put(error)

    threading.Thread(target=resolve, daemon=True).start()
    try:
        addresses = results.get(timeout=timeout)
    except queue.Empty:
        raise SourceError("Tempo de DNS excedido") from None
    if isinstance(addresses, OSError):
        raise SourceError("Falha de DNS") from addresses
    ips = [row[4][0] for row in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast for ip in ips):
        raise SourceError("Endereço de rede não público")
    return ips[0]


def _socket_timeout(deadline: float, io_timeout: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Tempo total de consulta excedido")
    return min(io_timeout, remaining)


class _DeadlineReader(io.RawIOBase):
    """Recalcula o prazo em cada recv, inclusive dentro de readline/chunk framing."""

    def __init__(self, raw, transport, deadline: float, io_timeout: float):
        self._raw, self._transport = raw, transport
        self._deadline, self._io_timeout = deadline, io_timeout

    def readable(self):
        return True

    def readinto(self, buffer):
        self._transport.settimeout(_socket_timeout(self._deadline, self._io_timeout))
        return self._raw.readinto(buffer)

    def close(self):
        try:
            self._raw.close()
        finally:
            super().close()


class _DeadlineHTTPResponse(http.client.HTTPResponse):
    def __init__(self, sock, *args, deadline: float, io_timeout: float, **kwargs):
        super().__init__(sock, *args, **kwargs)
        # Conserva o SocketIO original: ele mantém o descritor vivo se getresponse
        # fechar a conexão por Connection: close, e o libera ao fechar a resposta.
        self.fp = io.BufferedReader(_DeadlineReader(self.fp.detach(), sock, deadline, io_timeout))


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, timeout: float):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip
        self._deadline = None

    def _connect_timeout(self):
        return _socket_timeout(self._deadline, self.timeout) if self._deadline is not None else self.timeout

    def connect(self):
        self.sock = socket.create_connection((self._ip, 443), timeout=self._connect_timeout())
        try:
            self.sock.settimeout(self._connect_timeout())
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)
            self.sock.settimeout(self._connect_timeout())
        except BaseException:
            self.sock.close()
            raise


class TrustedSourceClient:
    def __init__(self, limits: FetchLimits | None = None):
        self.limits = limits or FetchLimits()

    def fetch(self, source: SourceSpec) -> SourceDocument:
        deadline = time.monotonic() + self.limits.total_timeout
        url = source.url
        try:
            for hop in range(self.limits.max_redirects + 1):
                parsed = validate_url(url, source.allowed_hosts)
                ip = resolve_public(parsed.hostname, self._remaining(deadline))
                connection = _PinnedHTTPSConnection(parsed.hostname, ip, self._remaining(deadline))
                connection._deadline = deadline
                connection.response_class = partial(
                    _DeadlineHTTPResponse, deadline=deadline, io_timeout=self.limits.io_timeout
                )
                response = None
                try:
                    path = parsed.path or "/"
                    if parsed.query:
                        path += "?" + parsed.query
                    connection.request(
                        "GET", path, headers={"User-Agent": "VX-Materials/1.0", "Accept-Encoding": "identity"}
                    )
                    transport = connection.sock
                    transport.settimeout(self._remaining(deadline))
                    response = connection.getresponse()
                    if response.status in (301, 302, 303, 307, 308):
                        target = response.getheader("Location")
                        if not target or hop == self.limits.max_redirects:
                            raise SourceError("Limite de redirecionamentos excedido")
                        url = urljoin(url, target)
                        validate_url(url, source.allowed_hosts)
                        continue
                    if response.status != 200:
                        raise SourceError(f"Fonte respondeu HTTP {response.status}")
                    content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
                    if content_type not in ("text/html", "text/plain", "application/pdf"):
                        raise SourceError("Tipo de conteúdo não permitido")
                    if response.getheader("Content-Encoding", "identity").lower() != "identity":
                        raise SourceError("Conteúdo comprimido não permitido")
                    length = response.getheader("Content-Length")
                    if length is not None and (not length.isdigit() or int(length) > self.limits.max_bytes):
                        raise SourceError("Fonte excede o limite de tamanho")
                    body = bytearray()
                    while True:
                        self._remaining(deadline)
                        chunk = response.read1(min(65536, self.limits.max_bytes + 1 - len(body)))
                        if not chunk:
                            break
                        body.extend(chunk)
                        if len(body) > self.limits.max_bytes:
                            raise SourceError("Fonte excede o limite de tamanho")
                    self._remaining(deadline)
                    return SourceDocument(source.id, url, bytes(body), content_type, datetime.now(UTC).isoformat())
                finally:
                    try:
                        if response is not None:
                            response.close()
                    finally:
                        connection.close()
        except (OSError, http.client.HTTPException) as error:
            raise SourceError("Falha ou tempo de consulta excedido") from error
        raise SourceError("Fonte indisponível")

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceError("Tempo total de consulta excedido")
        return min(self.limits.io_timeout, remaining)
