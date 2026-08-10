"""Vocabulary of the domain string values stored in the database.

Deliberately free of any SQLAlchemy, FastAPI or Jinja dependency: the
persistence layer and the (database independent) grading module both need
these values, and the grading module must stay importable without a database.

The members are ``StrEnum``, so they compare equal to their string value and
can be bound to a text column directly.
"""

from enum import StrEnum


class NoteStatus(StrEnum):
    """Specification 4.3. A missing value is never implicitly 0 or 6."""

    GEWERTET = "gewertet"
    NICHT_GEWERTET = "nicht_gewertet"
    NICHT_ERBRACHT = "nicht_erbracht"


class Bezugszeitraum(StrEnum):
    """Period a manually fixed grade refers to (specification 3.1)."""

    HALBJAHR_1 = "halbjahr_1"
    HALBJAHR_2 = "halbjahr_2"
    JAHR = "jahr"


class UeberschreibungQuelle(StrEnum):
    """Whether the teacher accepted the calculated proposal or deviated from it.

    Both cases are stored, so the reported grade is frozen at the moment it was
    fixed and does not silently drift when a grade is entered afterwards.
    """

    BERECHNET_UEBERNOMMEN = "berechnet_uebernommen"
    MANUELL = "manuell"


class Sortierung(StrEnum):
    """Sort order for pupil lists (specification 5.1, 6). Persisted setting."""

    VORNAME = "vorname"
    NACHNAME = "nachname"


class Namensanzeige(StrEnum):
    """Name display format (specification 6). Persisted setting."""

    VORNAME_NACHNAME = "vorname_nachname"
    NACHNAME_VORNAME = "nachname_vorname"


class HistorieAktion(StrEnum):
    """Kind of change recorded in ``note_historie`` (specification 3.2)."""

    ANGELEGT = "angelegt"
    GEAENDERT = "geaendert"
    GELOESCHT = "geloescht"
