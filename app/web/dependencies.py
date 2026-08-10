"""Per-request database session.

The engine is created on first use, never at import time: importing the
application must not touch the file system.
"""

from typing import Iterator

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.session import create_app_engine, create_session_factory

_engine: Engine | None = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_app_engine()
    return _engine


def datenbanksitzung() -> Iterator[Session]:
    """One session per request, closed no matter how the request ends."""
    session = create_session_factory(engine())()
    try:
        yield session
    finally:
        session.close()
