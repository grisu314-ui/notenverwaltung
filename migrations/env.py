"""Alembic environment.

Two things differ from the generated default and both matter on SQLite:

* ``render_as_batch=True`` — SQLite cannot ALTER most things in place. Batch
  mode rebuilds the table instead. It needs every constraint to have a name,
  which the naming convention in :mod:`app.db.base` guarantees.
* Foreign keys are switched **off** for the migration connection. A table
  rebuild in batch mode passes through a state that an enforced foreign key
  would reject. After the migration ``PRAGMA foreign_key_check`` verifies that
  nothing was orphaned, and fails loudly if it was.
"""

from logging.config import fileConfig

from alembic import context

from app.config import database_url
from app.db.base import Base
from app.db import models  # noqa: F401  -- registers all tables on Base.metadata
from app.db.session import create_app_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _target_url() -> str:
    """URL from alembic.ini if a caller set one, otherwise the app config."""
    return config.get_main_option("sqlalchemy.url") or database_url()


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(
        url=_target_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_app_engine(_target_url(), enable_foreign_keys=False)
    try:
        with engine.connect() as connection:
            _configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()

        with engine.connect() as connection:
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "Migration hat verwaiste Datensätze hinterlassen "
                f"(PRAGMA foreign_key_check): {violations!r}"
            )
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
