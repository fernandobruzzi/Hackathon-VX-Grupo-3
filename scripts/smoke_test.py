"""Smoke HTTP sem dependências: health, integração local ou sessão Cognito existente."""

import argparse
import http.cookiejar
import json
import sys
import time
import uuid
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

MESSAGE = "Preciso de parafuso sextavado M12x50, aço carbono, zincado branco, DIN 933."
FULL_MESSAGE = "Preciso de parafuso sextavado M12x50, classe 8.8, aço carbono, zincado branco, norma DIN 933"
AUTHORIZED_CENTERS = {"1100", "1200", "1300", "2100", "2200", "9000"}
# Recusas da regra de aprovação para propostas que a fila ainda lista como aprováveis.
REFUSED_ON_APPROVAL = {"PDM_INVALID", "NCM_REFERENCE_MISMATCH"}


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

    def chat(self, csrf=None, diagnostics=False):
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
        if not diagnostics:
            # Chamadas MCP são diagnóstico da role Dev/TI; perfis de negócio nunca as recebem.
            if calls:
                raise SmokeFailure("Perfil de negócio recebeu chamadas MCP sem chat:diagnostics")
            print("PASS API → Agent → validação PDM → persistência, sem diagnóstico MCP para o negócio")
            return
        for name in ("get_pdm_template", "validate_and_format_pdm"):
            if not any(
                c.get("name") == name and c.get("transport") == "MCP_STDIO" and c.get("status") == "SUCCEEDED"
                for c in calls
            ):
                raise SmokeFailure(f"Chamada MCP real ausente ou malsucedida: {name}")
        print("PASS Dev/TI: API → Agent → MCP stdio → validação PDM → persistência")

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
        me = self.json("/api/v1/auth/local-session", payload={"persona": "DEV_TI"}, headers={"Origin": self.base_url})
        self.chat(me["csrf_token"], diagnostics=True)
        for persona, area in [
            ("SOLICITANTE_OPERACAO", "TECHNICAL"),
            ("GESTOR_CADASTRO", "FISCAL"),
            ("AUDITOR_FISCAL", "TECHNICAL"),
            ("ALMOXARIFADO", "TECHNICAL"),
            ("COMPRAS", "FISCAL"),
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
            dashboard_path = "/api/v1/dashboard/metrics"
            if persona in ("SOLICITANTE_OPERACAO", "ALMOXARIFADO", "COMPRAS"):
                self.request(dashboard_path, expected=403)
            else:
                quality = self.json(dashboard_path)
                if "financial" in quality or quality["before"]["materials_total"] <= 0:
                    raise SmokeFailure("Dashboard de qualidade sem dados reais ou com valores financeiros")
                if quality.get("after") is not None:
                    raise SmokeFailure("Dashboard inventou um snapshot posterior")
                if persona == "GESTOR_CADASTRO":
                    self.request(dashboard_path + "?view=executive", expected=403)
                else:
                    financial = self.json(dashboard_path + "?view=executive")["financial"]
                    if financial["data_origin"] != "SYNTHETIC_CHALLENGE_DATA":
                        raise SmokeFailure("Dashboard não identificou os valores sintéticos")
        print("PASS dashboard persistido, comparação indisponível e visão financeira exclusiva do Fiscal")
        print("PASS RBAC: Solicitante não aprova saneamento, Governança não decide fiscal e Fiscal não unifica")
        self.json("/api/v1/auth/logout", payload={}, headers={"Origin": self.base_url, "X-CSRF-Token": csrf})
        self.request("/api/v1/auth/me", expected=401)
        print("PASS sessão local opaca, identidade do servidor e logout; Cognito não validado na AWS")

    # Fluxo completo (#47). Altera o banco: rode depois de `vx-demo reset` e de novo ao terminar.
    def login(self, persona):
        me = self.json("/api/v1/auth/local-session", payload={"persona": persona}, headers={"Origin": self.base_url})
        return {"Origin": self.base_url, "X-CSRF-Token": me["csrf_token"]}

    def write(self, path, payload, headers, expected=200):
        return self.json(
            path, expected=expected, payload=payload, headers={**headers, "Idempotency-Key": str(uuid.uuid4())}
        )

    def flow_chat(self):
        headers = self.login("SOLICITANTE_OPERACAO")
        turn = self.json(
            "/api/v1/chat/message",
            payload={
                "session_id": None,
                "client_message_id": str(uuid.uuid4()),
                "expected_session_version": 0,
                "message": FULL_MESSAGE,
                "center_code": "1200",
            },
            headers=headers,
        )
        card = turn["material_card"]
        # Sem a busca, a duplicidade fica PENDING sem candidatos; as chamadas MCP são só para Dev/TI.
        if card["duplicate_check_status"] == "PENDING" and not card.get("similar_candidates"):
            raise SmokeFailure("Chat não buscou similares: confira se o índice de busca está na versão atual")
        if card.get("missing_attributes"):
            raise SmokeFailure(f"Ficha completa ficou com pendências: {card['missing_attributes']}")
        offered = [c["material_code"] for c in card.get("similar_candidates") or []]
        if turn["status"] == "NEEDS_INPUT" and offered:
            turn = self.json(
                "/api/v1/chat/message",
                payload={
                    "session_id": turn["session_id"],
                    "client_message_id": str(uuid.uuid4()),
                    "expected_session_version": turn["session_version"],
                    "message": "Nenhum desses é o meu item",
                    "center_code": "1200",
                    "action": {"type": "DISMISS_CANDIDATES"},
                },
                headers=headers,
            )
        if turn["status"] not in {"READY_TO_SUBMIT", "EXISTING"}:
            raise SmokeFailure(f"Chat terminou em {turn['status']}, esperado READY_TO_SUBMIT ou EXISTING")
        print(f"PASS chat com busca de similares, {len(offered)} candidatos descartados e status {turn['status']}")
        materials = self.json("/api/v1/materials?q=parafuso&limit=20")["items"]
        centers = {row["center_code"] for item in materials for row in item["inventory"]}
        if not materials or not centers <= AUTHORIZED_CENTERS:
            raise SmokeFailure("/materiais sem resultados ou com estoque fora dos centros do usuário")
        if any(key in json.dumps(materials) for key in ("unit_price", "total_value")):
            raise SmokeFailure("/materiais expôs valores financeiros ao Solicitante")
        print(f"PASS /materiais com {len(materials)} resultados e estoque só dos centros autorizados")

    def pending_merges(self, fiscal):
        """Unificações pendentes sem conflito, com a classe do roteiro (parafuso sextavado) primeiro."""
        items, cursor = [], ""
        for _ in range(20):
            page = self.json(f"/api/v1/sanitization/queue?proposal_type=MERGE&status=PENDING&limit=100{cursor}")
            items += [
                item
                for item in page["items"]
                if not item["conflicts"] and (item["fiscal_review_status"] == "PENDING") == fiscal
            ]
            if not page["next_cursor"]:
                break
            cursor = f"&cursor={page['next_cursor']}"
        if not items:
            raise SmokeFailure(f"Nenhuma unificação pendente sem conflito (fiscal={fiscal}): rode o reset da demo")
        return sorted(items, key=lambda item: not item["title"].startswith("PARAFUSO SEXTAVADO"))

    def send(self, path, payload, headers):
        """POST que devolve status e corpo, para tratar recusas esperadas sem abortar."""
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers={"Accept": "application/json", "Content-Type": "application/json", **headers},
        )
        try:
            response = self.opener.open(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read() or b"null")

    def decide(self, item, area, headers):
        payload = {
            "expected_version": item["version"],
            "review_area": area,
            "decision": "APPROVE",
            "reason": "Fluxo completo local (#47)",
        }
        path = f"/api/v1/sanitization/{item['id']}/decide"
        return self.send(path, payload, {**headers, "Idempotency-Key": str(uuid.uuid4())})

    def approve_first(self, items, area, headers):
        """Aprova a primeira que a regra de aprovação aceita. A fila ainda lista algumas que ela recusa."""
        refused = []
        for item in items[:10]:
            status, body = self.decide(item, area, headers)
            if status == 200:
                return item, body, refused
            code = (body or {}).get("error", {}).get("code")
            if status != 422 or code not in REFUSED_ON_APPROVAL:
                raise SmokeFailure(f"Decisão da proposta {item['id']}: HTTP {status} {code}")
            refused.append(code)
        raise SmokeFailure(f"Nenhuma das 10 primeiras unificações pôde ser aprovada: {refused}")

    def flow_approvals(self):
        governance = self.login("GESTOR_CADASTRO")
        orders = self.json("/api/v1/registration-orders?limit=100")["items"]
        if not orders or {o["origin"] for o in orders} != {"IMPORT"}:
            raise SmokeFailure("Pedidos do kit não foram importados: rode o reset da demo")
        print(f"PASS pedidos importados e analisados ({len(orders)} na primeira página)")

        _, applied, refused = self.approve_first(self.pending_merges(fiscal=False), "TECHNICAL", governance)
        if applied["status"] != "APPLIED":
            raise SmokeFailure(f"Unificação técnica não foi aplicada: {applied['status']}")
        both, waiting, refused_fiscal = self.approve_first(self.pending_merges(fiscal=True), "TECHNICAL", governance)
        if waiting["status"] != "PENDING" or waiting["fiscal_review_status"] != "PENDING":
            raise SmokeFailure("Aprovação técnica aplicou uma unificação que ainda exige revisão fiscal")
        fiscal = self.login("AUDITOR_FISCAL")
        status, final = self.decide({**both, "version": waiting["version"]}, "FISCAL", fiscal)
        if status != 200 or final["status"] != "APPLIED":
            raise SmokeFailure(f"Aprovação fiscal não aplicou a unificação: HTTP {status} {final}")
        if refused or refused_fiscal:
            print(f"INFO fila listou como aprováveis unificações recusadas na decisão: {refused + refused_fiscal}")
        events = {applied["audit_event_id"], waiting["audit_event_id"], final["audit_event_id"]}
        # A Governança só vê a auditoria técnica; o Fiscal, ainda logado, vê as três decisões.
        audit = {event["id"] for event in self.json("/api/v1/audit?limit=100")["items"]}
        if not events <= audit:
            raise SmokeFailure("Decisões aplicadas sem evento de auditoria correspondente")
        print("PASS Governança aplica, Fiscal conclui a revisão fiscal e as três decisões estão na auditoria")

    def flow_batch(self, timeout):
        governance = self.login("GESTOR_CADASTRO")
        jobs = self.json("/api/v1/batch/jobs")
        job = self.write(
            "/api/v1/batch/jobs",
            {
                "dataset_id": jobs["latest_dataset_id"],
                "job_type": "SANITIZE",
                "pdm_version": "pdm-kit-v1",
                "ncm_version": "ncm-demo-v1",
                "scope": {"pdm_class_ids": [], "include_statuses": ["ATIVO", "BLOQUEADO", "OBSOLETO"]},
            },
            governance,
            expected=202,
        )
        deadline = time.monotonic() + timeout
        while job["status"] in {"QUEUED", "RUNNING"}:
            if time.monotonic() > deadline:
                raise SmokeFailure(f"Job do batch não terminou em {timeout} s")
            time.sleep(5)
            job = self.json(f"/api/v1/batch/jobs/{job['id']}")
        if job["status"] != "SUCCEEDED" or not job["counts"]["proposals"]:
            raise SmokeFailure(f"Job do batch terminou em {job['status']}: {job.get('error')}")
        print(f"PASS job do batch pela API: {job['counts']['proposals']} propostas")

    def flow_dashboard(self):
        governance = self.login("GESTOR_CADASTRO")
        self.write("/api/v1/dashboard/snapshots", {}, governance, expected=201)
        metrics = self.json("/api/v1/dashboard/metrics")
        if metrics.get("after") is None or "financial" in metrics:
            raise SmokeFailure("Dashboard sem snapshot posterior ou com valores financeiros na visão de qualidade")
        print("PASS snapshot posterior registrado e comparado no dashboard")

    def flow(self, batch_timeout):
        self.flow_chat()
        self.flow_batch(batch_timeout)
        self.flow_approvals()
        self.flow_dashboard()
        print("PASS fluxo completo local; rode o reset da demo antes do próximo ensaio")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--mode", choices=("health", "local", "flow", "authenticated"), default="health")
    parser.add_argument("--batch-timeout", type=int, default=600, help="Segundos para o job do batch no modo flow")
    parser.add_argument("--cookie-jar", help="Arquivo Netscape com sessão Solicitante real; nunca é impresso")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme not in {"http", "https"} or not url.netloc or url.path not in {"", "/"} or url.query or url.fragment:
        parser.error("base_url deve ser uma origem HTTP(S), sem caminho, query ou fragmento")
    if url.username or url.password:
        parser.error("Não inclua credenciais na URL")
    if args.mode in {"local", "flow"} and (
        url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        parser.error(f"modo {args.mode} exige loopback HTTP")
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
        elif args.mode == "flow":
            smoke.flow(args.batch_timeout)
        else:
            smoke.local()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SmokeFailure, OSError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        sys.exit(1)
