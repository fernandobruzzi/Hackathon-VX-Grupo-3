from alembic import context
from sqlalchemy import create_engine, pool

from vx_materials_api import settings
from vx_materials_api.db.models import Base


def run_migrations() -> None:
    url = context.config.get_main_option("sqlalchemy.url") or settings.migration_database_url()
    engine = create_engine(url.replace("%%", "%"), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
