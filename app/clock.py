"""Single source of truth for timestamps written to the database.

All stored timestamps are UTC without tzinfo. SQLite carries no timezone
information, and SQLAlchemy's SQLite DATETIME type does not round-trip an
aware datetime unchanged; storing naive UTC makes the stored value
unambiguous. Conversion to Europe/Berlin happens at display time only.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Current UTC time, without tzinfo, for storage in the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
