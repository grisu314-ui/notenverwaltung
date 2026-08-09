"""Configuration.

The application reads exactly one environment variable: the path to the
SQLite database file. It has no API keys, no external services and no further
configuration surface, so there is nothing else to configure.
"""

import os
from pathlib import Path

ENV_DB_PATH = "NOTENVERWALTUNG_DB"
DEFAULT_DB_PATH = Path("data/notenverwaltung.db")


def database_path() -> Path:
    """Path to the SQLite file, relative paths resolved against the cwd."""
    configured = os.environ.get(ENV_DB_PATH)
    return Path(configured) if configured else DEFAULT_DB_PATH


def database_url(path: Path | None = None) -> str:
    """SQLAlchemy URL for the given (or configured) database file."""
    target = path if path is not None else database_path()
    return f"sqlite+pysqlite:///{target}"
