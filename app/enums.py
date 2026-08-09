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


class Eingabeart(StrEnum):
    """Specification 4.3: a grade is entered either directly or as points."""

    NOTE = "note"
    PUNKTE = "punkte"


class NotenschluesselTyp(StrEnum):
    """Specification 4.2."""

    IHK = "ihk"
    RLP_STANDARD = "rlp_standard"
    BENUTZERDEFINIERT = "benutzerdefiniert"


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


class HistorieAktion(StrEnum):
    """Kind of change recorded in ``note_historie`` (specification 3.2)."""

    ANGELEGT = "angelegt"
    GEAENDERT = "geaendert"
    GELOESCHT = "geloescht"
