"""Credenciais descartáveis para testes de banco.

Roles e senhas são globais no servidor PostgreSQL: trocar a senha de `api_user` num banco `_test`
derruba a API local e outras suítes rodando ao mesmo tempo. Em vez disso, cada teste cria uma role
de login própria, membro da role real, e a apaga no fim. Os privilégios vêm por herança, então
o teste exercita as mesmas permissões sem tocar nas credenciais compartilhadas.
"""

import secrets
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

PREFIX = "vx_tmp_"


def _conninfo(admin_url: str) -> str:
    return make_url(admin_url).set(drivername="postgresql").render_as_string(hide_password=False)


@contextmanager
def temporary_login(admin_url: str, role: str) -> Iterator[str]:
    """URL de uma role descartável com os privilégios de `role`. Exige CREATEROLE e ADMIN em `role`."""
    name = f"{PREFIX}{role}_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    with psycopg.connect(_conninfo(admin_url), autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN INHERIT PASSWORD {} IN ROLE {}").format(
                sql.Identifier(name), sql.Literal(password), sql.Identifier(role)
            )
        )
    try:
        yield make_url(admin_url).set(username=name, password=password).render_as_string(hide_password=False)
    finally:
        with psycopg.connect(_conninfo(admin_url), autocommit=True) as connection:
            # Encerra sessões ainda abertas por pools, para a role poder ser removida.
            connection.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = %s", (name,))
            connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(name)))
