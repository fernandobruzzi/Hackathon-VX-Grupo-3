"""Sem rede real: valida a política e o cliente HTTP, inclusive redirecionamentos e streaming."""

import io
import socket
import time

import pytest

from enrichment import trusted_sources
from enrichment.trusted_sources import (
    FetchLimits,
    SourceError,
    SourceSpec,
    TrustedSourceClient,
    resolve_public,
    validate_url,
)

SOURCE = SourceSpec("reviewed", "https://catalog.example/product/123", "Catálogo de teste", ("catalog.example",))


@pytest.mark.parametrize(
    "url",
    [
        "http://catalog.example/product",
        "https://catalog.example.attacker.test/product",
        "https://catalog.example:8080/product",
        "https://user:secret@catalog.example/product",
        "https://127.0.0.1/product",
        "file:///etc/passwd",
        "https://catalog.example/product#fragment",
        "https://catalog.example/\r\nInjected",
        "https://catalog.example\\@attacker.test/product",
    ],
)
def test_untrusted_urls_are_rejected(url):
    with pytest.raises(SourceError, match="URL"):
        validate_url(url, SOURCE.allowed_hosts)


@pytest.mark.parametrize(
    "ips",
    [
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["10.0.0.1"],
        ["::1"],
        ["fc00::1"],
        ["93.184.216.34", "192.168.1.1"],
        ["::ffff:127.0.0.1"],
        ["0.0.0.0"],
        ["224.0.0.1"],
    ],
)
def test_all_dns_answers_must_be_public(monkeypatch, ips):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, (ip, 443)) for ip in ips]
    )
    with pytest.raises(SourceError, match="não público"):
        resolve_public("catalog.example", 1)


def test_dns_has_a_deadline(monkeypatch):
    def slow(*args, **kwargs):
        time.sleep(0.1)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", slow)
    with pytest.raises(SourceError, match="DNS excedido"):
        resolve_public("catalog.example", 0.01)


class Response:
    def __init__(self, content=b"product", status=200, headers=None):
        self.status = status
        self.headers = {"Content-Type": "text/plain", **(headers or {})}
        self.stream = io.BytesIO(content)

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read1(self, size):
        return self.stream.read(size)


@pytest.fixture
def transport(monkeypatch):
    responses, connections, resolved = [], [], []

    def resolver(host, timeout):
        resolved.append(host)
        return "93.184.216.34"

    class Connection:
        def __init__(self, host, ip, timeout):
            self.host, self.ip, self.timeout = host, ip, timeout
            self.sock = self
            self.closed = False
            connections.append(self)

        def request(self, method, path, headers):
            self.request_data = (method, path, headers)

        def settimeout(self, timeout):
            self.timeout = timeout

        def getresponse(self):
            return responses.pop(0)

        def close(self):
            self.closed = True

    monkeypatch.setattr(trusted_sources, "resolve_public", resolver)
    monkeypatch.setattr(trusted_sources, "_PinnedHTTPSConnection", Connection)
    return responses, connections, resolved


def test_client_uses_the_validated_ip_without_a_second_resolution(transport):
    responses, connections, resolved = transport
    responses.append(Response())
    document = TrustedSourceClient().fetch(SOURCE)
    assert document.content == b"product"
    assert document.source_id == SOURCE.id
    assert resolved == ["catalog.example"]
    assert connections[0].ip == "93.184.216.34"
    assert connections[0].closed
    assert connections[0].request_data[0:2] == ("GET", "/product/123")
    assert connections[0].request_data[2]["Accept-Encoding"] == "identity"


def test_redirect_to_untrusted_domain_is_rejected_before_connecting(transport):
    responses, connections, resolved = transport
    responses.append(Response(status=302, headers={"Location": "https://169.254.169.254/latest/meta-data"}))
    with pytest.raises(SourceError, match="URL"):
        TrustedSourceClient().fetch(SOURCE)
    assert len(connections) == len(resolved) == 1
    assert connections[0].closed


def test_each_allowed_redirect_is_resolved_again_and_the_final_url_is_recorded(transport):
    responses, connections, resolved = transport
    responses.extend([Response(status=302, headers={"Location": "/final"}), Response()])
    document = TrustedSourceClient().fetch(SOURCE)
    assert document.url == "https://catalog.example/final"
    assert len(resolved) == 2
    assert all(connection.closed for connection in connections)


def test_redirect_loops_are_bounded(transport):
    responses, connections, _ = transport
    responses.extend(Response(status=302, headers={"Location": "/again"}) for _ in range(3))
    with pytest.raises(SourceError, match="redirecionamentos"):
        TrustedSourceClient(FetchLimits(max_redirects=2)).fetch(SOURCE)
    assert len(connections) == 3


@pytest.mark.parametrize(
    ("headers", "content", "message"),
    [
        ({"Content-Length": "100"}, b"x", "tamanho"),
        ({}, b"123456", "tamanho"),
        ({"Content-Length": "invalid"}, b"x", "tamanho"),
        ({"Content-Encoding": "gzip"}, b"x", "comprimido"),
        ({"Content-Type": "application/octet-stream"}, b"x", "conteúdo"),
    ],
)
def test_response_limits_apply_before_and_during_reading(transport, headers, content, message):
    responses, connections, _ = transport
    responses.append(Response(content, headers=headers))
    with pytest.raises(SourceError, match=message):
        TrustedSourceClient(FetchLimits(max_bytes=5)).fetch(SOURCE)
    assert connections[0].closed


def test_total_deadline_applies_across_redirects(transport, monkeypatch):
    responses, _, _ = transport
    responses.append(Response(status=302, headers={"Location": "/again"}))
    ticks = iter([0, 0, 0, 0, 13])
    monkeypatch.setattr(trusted_sources.time, "monotonic", lambda: next(ticks))
    with pytest.raises(SourceError, match="Tempo total"):
        TrustedSourceClient().fetch(SOURCE)


def test_network_failures_are_explicit_pending_errors(transport):
    _, connections, _ = transport

    # Usa o mesmo construtor observado no teste para simular uma falha de conexão.
    class FailingConnection:
        def __init__(self, *args):
            self.closed = False
            connections.append(self)

        def request(self, *args, **kwargs):
            raise TimeoutError("timeout")

        def close(self):
            self.closed = True

    original = trusted_sources._PinnedHTTPSConnection
    trusted_sources._PinnedHTTPSConnection = FailingConnection
    try:
        with pytest.raises(SourceError, match="tempo"):
            TrustedSourceClient().fetch(SOURCE)
        assert connections[0].closed
    finally:
        trusted_sources._PinnedHTTPSConnection = original
