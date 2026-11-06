"""Cliente OAuth e validação estrita dos tokens emitidos pelo User Pool configurado."""

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import jwt
from cryptography.fernet import Fernet
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.permissions import ROLE_PERMISSIONS


def invalid_login():
    return ApiProblem(401, "UNAUTHENTICATED", "Login inválido ou expirado. Entre novamente.")


@dataclass(frozen=True)
class CognitoConfig:
    issuer: str
    client_id: str
    domain: str
    origin: str
    encryption_key: str
    center_codes: tuple[str, ...]
    audience: str | None = None
    client_secret: str | None = None

    @property
    def redirect_uri(self):
        return self.origin + "/auth/callback/"

    @classmethod
    def from_environment(cls):
        def required(key):
            value = os.environ.get(key)
            if not value:
                raise RuntimeError(f"Variável obrigatória para Cognito: {key}")
            return value

        region = required("AWS_REGION")
        pool = required("COGNITO_USER_POOL_ID")
        if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", region) or not pool.startswith(region + "_"):
            raise RuntimeError("Região e User Pool Cognito incompatíveis")
        origin = required("APP_ORIGIN").rstrip("/")
        domain = required("COGNITO_DOMAIN").rstrip("/")
        for value in (origin, domain):
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise RuntimeError("Cognito exige origens HTTPS sem caminho ou credenciais")
        key = required("SESSION_ENCRYPTION_KEY")
        Fernet(key.encode())
        centers = tuple(part.strip() for part in required("AUTHORIZED_CENTER_CODES").split(",") if part.strip())
        if not centers:
            raise RuntimeError("Defina pelo menos um centro autorizado")
        return cls(
            f"https://cognito-idp.{region}.amazonaws.com/{pool}",
            required("COGNITO_APP_CLIENT_ID"),
            domain,
            origin,
            key,
            centers,
            os.environ.get("COGNITO_RESOURCE_AUDIENCE") or None,
            os.environ.get("COGNITO_APP_CLIENT_SECRET") or None,
        )


class CognitoClient:
    def __init__(self, config: CognitoConfig, *, key_provider=None, transport=None):
        self.config = config
        self.keys = key_provider or PyJWKClient(config.issuer + "/.well-known/jwks.json", lifespan=300, timeout=5)
        self.transport = transport

    def validate(self, token: str, token_use: str) -> dict:
        try:
            if not isinstance(token, str) or len(token) > 16384:
                raise invalid_login()
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str) or len(header["kid"]) > 128:
                raise invalid_login()
            key = self.keys.get_signing_key_from_jwt(token).key
            audience = self.config.client_id if token_use == "id" else self.config.audience
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.config.issuer,
                audience=audience,
                options={"require": ["exp", "iat", "iss", "sub", "token_use"], "verify_aud": audience is not None},
            )
            if claims["token_use"] != token_use or not isinstance(claims["sub"], str) or not claims["sub"]:
                raise invalid_login()
            if type(claims["exp"]) is not int or type(claims["iat"]) is not int:
                raise invalid_login()
            if token_use == "access":
                scope = claims.get("scope")
                if (
                    claims.get("client_id") != self.config.client_id
                    or not isinstance(scope, str)
                    or "openid" not in scope.split()
                ):
                    raise invalid_login()
                groups = claims.get("cognito:groups", [])
                if not isinstance(groups, list) or not all(isinstance(group, str) for group in groups):
                    raise invalid_login()
                claims["roles"] = tuple(sorted(set(groups) & ROLE_PERMISSIONS.keys()))
                if not claims["roles"]:
                    raise ApiProblem(403, "FORBIDDEN", "Conta sem grupo autorizado para a aplicação.")
            return claims
        except PyJWKClientConnectionError:
            raise ApiProblem(
                503, "IDENTITY_UNAVAILABLE", "Não foi possível consultar o provedor de identidade."
            ) from None
        except (jwt.InvalidTokenError, PyJWKClientError, TypeError, ValueError):
            raise invalid_login() from None

    def validate_pair(self, tokens: dict, nonce: str) -> tuple[dict, dict]:
        access = self.validate(tokens.get("access_token"), "access")
        profile = self.validate(tokens.get("id_token"), "id")
        if access["sub"] != profile["sub"] or not hmac.compare_digest(str(profile.get("nonce", "")), nonce):
            raise invalid_login()
        if "at_hash" in profile:
            expected = (
                base64.urlsafe_b64encode(hashlib.sha256(tokens["access_token"].encode()).digest()[:16])
                .decode()
                .rstrip("=")
            )
            if not hmac.compare_digest(str(profile["at_hash"]), expected):
                raise invalid_login()
        return access, profile

    def exchange(self, code: str, verifier: str) -> dict:
        data = {
            "grant_type": "authorization_code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
        auth = httpx.BasicAuth(self.config.client_id, self.config.client_secret) if self.config.client_secret else None
        try:
            with httpx.Client(transport=self.transport, timeout=10, follow_redirects=False) as client:
                response = client.post(self.config.domain + "/oauth2/token", data=data, auth=auth)
            if response.status_code >= 500 or response.status_code == 429:
                raise ApiProblem(503, "IDENTITY_UNAVAILABLE", "Provedor de identidade temporariamente indisponível.")
            if response.status_code != 200:
                raise invalid_login()
            result = response.json()
            if not isinstance(result, dict) or result.get("token_type", "").lower() != "bearer":
                raise invalid_login()
            return result
        except (httpx.HTTPError, ValueError):
            raise ApiProblem(503, "IDENTITY_UNAVAILABLE", "Não foi possível concluir o login.") from None
