"""Engine and session construction.

No engine is created at import time: importing this module must never touch
the file system or open a database.
"""

from sqlalchemy import Connection, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import database_url

BUSY_TIMEOUT_MS = 5000


def _apply_pragmas(dbapi_connection, enable_foreign_keys: bool) -> None:
    """Apply the pragmas required by specification section 2 to one connection.

    ``PRAGMA foreign_keys`` is a no-op inside a transaction, which is why this
    runs on the ``connect`` event, before any transaction has begun.

    ``synchronous`` is deliberately left at the SQLite default. Trading
    durability for speed is the wrong trade for an application whose worst
    conceivable failure is a grade that was silently not written.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"PRAGMA foreign_keys = {'ON' if enable_foreign_keys else 'OFF'}")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def create_app_engine(url: str | None = None, *, enable_foreign_keys: bool = True) -> Engine:
    """Create an engine that configures every new connection.

    ``enable_foreign_keys=False`` exists for Alembic only: SQLite batch
    migrations rebuild a table, and an enforced foreign key would reject the
    intermediate state. The migration verifies integrity afterwards with
    ``PRAGMA foreign_key_check``. Application code never disables them.
    """
    engine = create_engine(url if url is not None else database_url())

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, connection_record):
        _apply_pragmas(dbapi_connection, enable_foreign_keys)

    return engine


def create_session_factory(bind: Engine | Connection) -> sessionmaker[Session]:
    """Session factory bound to an engine or to an existing connection."""
    return sessionmaker(bind=bind)
