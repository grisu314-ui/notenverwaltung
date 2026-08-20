"""Single source of truth for timestamps written to the database.

All stored timestamps are UTC without tzinfo. SQLite carries no timezone
information, and SQLAlchemy's SQLite DATETIME type does not round-trip an
aware datetime unchanged; storing naive UTC makes the stored value
unambiguous. Conversion to Europe/Berlin happens at display time only.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

# The one place the operator teaches in. A participation grade belongs to the
# school day as the teacher experienced it, not to the server's UTC date --
# those differ for two hours every evening.
ORTSZONE = ZoneInfo("Europe/Berlin")


def utc_now() -> datetime:
    """Current UTC time, without tzinfo, for storage in the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def heute_lokal() -> date:
    """Today's date where the teaching happens (5.6)."""
    return datetime.now(ORTSZONE).date()
