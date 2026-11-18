"""Alembic environment: one SQLite database at DATA_DIR/app.db (DATABASE.md 9.1)."""

from alembic import context

from app.storage.db import make_engine

config = context.config
url = config.get_main_option("sqlalchemy.url")
engine = make_engine(url) if url else make_engine()

try:
    with engine.connect() as connection:
        context.configure(connection=connection, render_as_batch=True, transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
