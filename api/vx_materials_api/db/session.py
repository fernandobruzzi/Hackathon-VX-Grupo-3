"""Conexão da API com o banco."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from vx_materials_api import settings


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or settings.database_url(), pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
