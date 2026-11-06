"""Smoke HTTP sem dependências: health, integração local ou sessão Cognito existente."""

import argparse
import http.cookiejar
import json
import sys
import uuid
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

MESSAGE = "Preciso de parafuso sextavado M12x50, aço carbono, zincado branco, DIN 933."


class SmokeFailure(Exception):
    pass


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in {"src", "href"} and value and value.startswith("/_next/static/"):
                self.paths.add(value)


class Smoke:
    def __init__(self, base_url, cookie_jar=None):
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(cookie_jar or http.cookiejar.CookieJar()))

    def request(self, path, expected=200, payload=None, headers=None):
        request_headers = {"Accept": "application/json", **(headers or {})}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=data, headers=request_headers)
        try:
            response = self.opener.open(request, timeout=30)
        except HTTPError as error:
            response = error
        except (URLError, TimeoutError) as error:
            raise SmokeFailure(f"{path}: serviço indisponível") from error
        with response:
            if response.status != expected:
                raise SmokeFailure(f"{path}: esperado HTTP {expected}, recebido {response.status}")
            return response.read(), response.headers

    def json(self, path, **kwargs):
        body, _ = self.request(path, **kwargs)
        try:
            value = json.loads(body)
        except ValueError as error:
            raise SmokeFailure(f"{path}: resposta não é JSON") from error
        if not isinstance(value, dict):
            raise SmokeFailure(f"{path}: esperado objeto JSON")
        return value

    def health(self):
        if self.json("/api/v1/healthz").get("status") != "ok":
            raise SmokeFailure("healthz não retornou status=ok")
        print("PASS health HTTP/JSON (liveness, não comprova prontidão das dependências)")

    def front(self):
        body, headers = self.request("/")
        if "text/html" not in headers.get("Content-Type", ""):
            raise SmokeFailure("/ não retornou HTML")
        assets = Assets()
        assets.feed(body.decode())
        if not assets.paths:
            raise SmokeFailure("Nenhum asset Next.js encontrado")
        for path in sorted(assets.paths):
            content, asset_headers = self.request(path)
            if not content or "text/html" in asset_headers.get("Content-Type", ""):
                raise SmokeFailure(f"Asset ausente ou substituído por HTML: {path}")
        self.request("/auth/callback/?code=smoke&state=smoke")
        print("PASS front, assets e rota estática do callback")

    def chat(self, csrf=None):
        payload = {
            "session_id": None,
            "client_message_id": str(uuid.uuid4()),
            "expected_session_version": 0,
            "message": MESSAGE,
            "center_code": "1200",
        }
        headers = {"Origin": self.base_url}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        result = self.json("/api/v1/chat/message", payload=payload, headers=headers)
        card = result.get("material_card", {})
        if result.get("status") != "NEEDS_INPUT" or "CLASSE RESISTENCIA" not in card.get("missing_attributes", []):
            raise SmokeFailure("Chat não identificou a pendência CLASSE RESISTENCIA")
        calls = result.get("tool_calls", [])
        for name in ("get_pdm_template", "validate_and_format_pdm"):
            if not any(
                c.get("name") == name and c.get("transport") == "MCP_STDIO" and c.get("status") == "SUCCEEDED"
                for c in calls
            ):
                raise SmokeFailure(f"Chamada MCP real ausente ou malsucedida: {name}")
        print("PASS API → Agent → MCP stdio → validação PDM → persistência")

    def authenticated(self):
        Smoke(self.base_url).request("/api/v1/auth/me", expected=401)
        identity = self.json("/api/v1/auth/me")
        csrf = identity.get("csrf_token")
        permissions = identity.get("permissions", [])
        if (
            not csrf
            or "chat:use" not in permissions
            or "ROLE_SOLICITANTE" not in identity.get("user", {}).get("roles", [])
        ):
            raise SmokeFailure("Informe uma sessão Solicitante válida com CSRF e chat:use")
        payload = {
            "session_id": None,
            "client_message_id": str(uuid.uuid4()),
            "expected_session_version": 0,
            "message": MESSAGE,
            "center_code": "1200",
        }
        self.request("/api/v1/chat/message", expected=403, payload=payload, headers={"Origin": self.base_url})
        self.request(
            "/api/v1/chat/message",
            expected=403,
            payload=payload,
            headers={"Origin": self.base_url, "X-CSRF-Token": "invalid-smoke-token"},
        )
        self.request(
            "/api/v1/chat/message",
            expected=403,
            payload=payload,
            headers={"Origin": "https://invalid.example", "X-CSRF-Token": csrf},
        )
        self.request(
            f"/api/v1/sanitization/{uuid.uuid4()}/decide",
            expected=403,
            payload={"expected_version": 1, "review_area": "TECHNICAL", "decision": "REJECT", "reason": "Smoke RBAC"},
            headers={"Origin": self.base_url, "X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
        )
        print("PASS auth/me, CSRF ausente/inválido, origem hostil e RBAC Solicitante")
        self.chat(csrf)

    def local(self):
        self.request("/api/v1/auth/me", expected=401)
        me = self.json(
            "/api/v1/auth/local-session", payload={"persona": "SOLICITANTE_OPERACAO"}, headers={"Origin": self.base_url}
        )
        csrf = me["csrf_token"]
        self.chat(csrf)
        for persona, area in [
            ("SOLICITANTE_OPERACAO", "TECHNICAL"),
            ("GESTOR_CADASTRO", "FISCAL"),
            ("AUDITOR_FISCAL", "TECHNICAL"),
        ]:
            me = self.json(
                "/api/v1/auth/local-session", payload={"persona": persona}, headers={"Origin": self.base_url}
            )
            csrf = me["csrf_token"]
            self.request(
                f"/api/v1/sanitization/{uuid.uuid4()}/decide",
                expected=403,
                payload={
                    "expected_version": 1,
                    "review_area": area,
                    "decision": "REJECT",
                    "reason": "Smoke de autorização",
                },
                headers={"Origin": self.base_url, "X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
            )
        print("PASS RBAC: Solicitante não aprova saneamento, Governança não decide fiscal e Fiscal não unifica")
        self.json("/api/v1/auth/logout", payload={}, headers={"Origin": self.base_url, "X-CSRF-Token": csrf})
        self.request("/api/v1/auth/me", expected=401)
        print("PASS sessão local opaca, identidade do servidor e logout; Cognito não validado na AWS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--mode", choices=("health", "local", "authenticated"), default="health")
    parser.add_argument("--cookie-jar", help="Arquivo Netscape com sessão Solicitante real; nunca é impresso")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme not in {"http", "https"} or not url.netloc or url.path not in {"", "/"} or url.query or url.fragment:
        parser.error("base_url deve ser uma origem HTTP(S), sem caminho, query ou fragmento")
    if url.username or url.password:
        parser.error("Não inclua credenciais na URL")
    if args.mode == "local" and (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}):
        parser.error("modo local exige loopback HTTP")
    jar = None
    if args.mode == "authenticated":
        if url.scheme != "https" or not args.cookie_jar:
            parser.error("modo authenticated exige HTTPS e --cookie-jar")
        jar = http.cookiejar.MozillaCookieJar(args.cookie_jar)
        jar.load(ignore_discard=True)
        if not any(
            c.name == "__Host-vx_session" and c.secure and c.path == "/" and not c.domain_specified for c in jar
        ):
            parser.error("Cookie __Host-vx_session Secure, host-only e Path=/ ausente")
    smoke = Smoke(args.base_url, jar)
    smoke.health()
    if args.mode != "health":
        smoke.front()
        if args.mode == "authenticated":
            smoke.authenticated()
        else:
            smoke.local()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SmokeFailure, OSError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        sys.exit(1)
