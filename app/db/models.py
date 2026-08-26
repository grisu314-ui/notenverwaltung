"""Persistence model, specification section 3.

Entity and column names stay German because they are domain terms of the
German school system; translating half of them would be less consistent than
keeping all of them. Comments and docstrings are English.

Deviations from section 3.1, all approved before implementation:

* **No point entry.** Grades are entered directly as 1+ ... 6; any conversion
  from points happens outside this application. The Notenschluessel entity of
  3.1, ``leistung.max_punkte`` and ``note.eingabeart``/``punkte`` are therefore
  not built, and with them sections 4.2 and the point entry half of 4.3.
* ``kurs.gewicht_halbjahr_1`` / ``_2`` — section 4.5 requires the weighting of
  the two terms to be configurable per course, but 3.1 lists no such field.
  Default 50/50 (open point O-7), editable per course.
* ``notenueberschreibung.quelle`` — a fixed grade is stored even when it equals
  the calculated proposal, so it is frozen at that moment and does not drift
  when a grade is entered later. The column records whether the proposal was
  accepted or deviated from.
* ``note_historie`` carries more than the four columns named in 3.2; see the
  class docstring for why the literal version does not work.
* ``einstellung`` — sections 4.4, 5.1 and 6 require persisted settings and 3.1
  has no entity for them. There is no user table, so a single key/value table
  holds them.

Numeric values use :class:`~app.db.types.DecimalText`; see there for the
consequences for SQL-side sorting and aggregation.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import utc_now
from app.db.base import Base
from app.db.types import DecimalText
from app.enums import (
    Bezugszeitraum,
    HistorieAktion,
    NoteStatus,
    UeberschreibungQuelle,
)

# Answer to open point O-7. The weighting of the two terms for the year grade;
# the teacher fixes the actual report grade anyway (Notenueberschreibung).
VORGABE_GEWICHT_HALBJAHR = Decimal("50")

# Section 5.6. Grid of a seating plan: rows and seats per row, adjustable
# independently. The upper bound guards against a typo; it says nothing about
# any real room.
VORGABE_REIHEN = 5
VORGABE_SITZE_JE_REIHE = 6
MIN_RASTER = 1
MAX_RASTER = 12

# Section 3.1: the three groups every new course starts with, per term. Name
# and weight are editable afterwards; this is a starting point, not a rule.
#
# The 3 for Mitarbeit is the point of the whole table. The calculation is
# single-stage (4.4), so a group weighs more the more grades it holds, and
# participation grades accumulate one by one over the term (5.6). At a weight
# in the order of the other groups they would end up the heaviest item on the
# report.
BEZEICHNUNG_MITARBEIT = "Mitarbeit"
VORGABE_NOTENGRUPPEN: tuple[tuple[str, Decimal, int], ...] = (
    ("Klassenarbeit", Decimal("70"), 1),
    ("Kleiner Nachweis", Decimal("30"), 2),
    (BEZEICHNUNG_MITARBEIT, Decimal("3"), 3),
)


def _in_clause(column: str, allowed: Iterable[str]) -> str:
    """SQL ``IN`` predicate over the fixed vocabulary from :mod:`app.enums`.

    The values are internal constants, never user input.
    """
    values = ", ".join(f"'{value}'" for value in allowed)
    return f"{column} IN ({values})"


class Schuljahr(Base):
    __tablename__ = "schuljahr"

    id: Mapped[int] = mapped_column(primary_key=True)
    bezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    beginn: Mapped[date] = mapped_column(Date, nullable=False)
    ende: Mapped[date] = mapped_column(Date, nullable=False)
    ist_aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    halbjahre: Mapped[list["Halbjahr"]] = relationship(
        back_populates="schuljahr",
        cascade="all, delete",
        passive_deletes=True,
        order_by="Halbjahr.nummer",
    )
    klassen: Mapped[list["Klasse"]] = relationship(
        back_populates="schuljahr", cascade="all, delete", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("bezeichnung"),
        CheckConstraint("ende > beginn", name="ende_nach_beginn"),
    )


class Halbjahr(Base):
    __tablename__ = "halbjahr"

    id: Mapped[int] = mapped_column(primary_key=True)
    schuljahr_id: Mapped[int] = mapped_column(
        ForeignKey("schuljahr.id", ondelete="CASCADE"), nullable=False
    )
    nummer: Mapped[int] = mapped_column(Integer, nullable=False)
    beginn: Mapped[date] = mapped_column(Date, nullable=False)
    ende: Mapped[date] = mapped_column(Date, nullable=False)

    schuljahr: Mapped["Schuljahr"] = relationship(back_populates="halbjahre")
    notengruppen: Mapped[list["Notengruppe"]] = relationship(
        back_populates="halbjahr", cascade="all, delete", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("schuljahr_id", "nummer"),
        CheckConstraint("nummer IN (1, 2)", name="nummer_gueltig"),
        CheckConstraint("ende > beginn", name="ende_nach_beginn"),
    )


class Klasse(Base):
    __tablename__ = "klasse"

    id: Mapped[int] = mapped_column(primary_key=True)
    schuljahr_id: Mapped[int] = mapped_column(
        ForeignKey("schuljahr.id", ondelete="CASCADE"), nullable=False
    )
    bezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    notiz: Mapped[str | None] = mapped_column(Text, nullable=True)

    schuljahr: Mapped["Schuljahr"] = relationship(back_populates="klassen")
    schueler: Mapped[list["Schueler"]] = relationship(
        back_populates="klasse", cascade="all, delete", passive_deletes=True
    )
    kurse: Mapped[list["Kurs"]] = relationship(
        back_populates="klasse", cascade="all, delete", passive_deletes=True
    )
    sitzplan: Mapped["Sitzplan | None"] = relationship(
        back_populates="klasse",
        cascade="all, delete",
        passive_deletes=True,
        uselist=False,
    )

    __table_args__ = (UniqueConstraint("schuljahr_id", "bezeichnung"),)


class Schueler(Base):
    """A pupil belongs to exactly one class per school year (3.1).

    ``ist_aktiv = False`` replaces deletion when a pupil leaves; the grades
    stay. Real deletion exists only through the explicit delete function
    (section 11) and is carried by the database-side cascades.

    ``arbeitet_digital`` defaults to False, for both new and existing rows.
    The default runs in the harmless direction: too many paper copies costs
    paper, too few costs a lesson.
    """

    __tablename__ = "schueler"

    id: Mapped[int] = mapped_column(primary_key=True)
    vorname: Mapped[str] = mapped_column(String, nullable=False)
    nachname: Mapped[str] = mapped_column(String, nullable=False)
    klasse_id: Mapped[int] = mapped_column(
        ForeignKey("klasse.id", ondelete="CASCADE"), nullable=False
    )
    listennummer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Deferred so that listing a class does not pull thirty photos into memory;
    # the image is served through its own endpoint.
    foto: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    foto_geaendert_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notiz: Mapped[str | None] = mapped_column(Text, nullable=True)
    ist_aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Section 3.1: whether the pupil works on a device of their own. Display
    # only -- it must never reach the calculation, the export or the course
    # enrolment. Its two effects are the copy count of 5.1 and the marking on
    # the seat in 5.6.
    arbeitet_digital: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    klasse: Mapped["Klasse"] = relationship(back_populates="schueler")
    kursteilnahmen: Mapped[list["Kursteilnahme"]] = relationship(
        back_populates="schueler", cascade="all, delete", passive_deletes=True
    )
    noten: Mapped[list["Note"]] = relationship(
        back_populates="schueler", cascade="all, delete", passive_deletes=True
    )
    ueberschreibungen: Mapped[list["Notenueberschreibung"]] = relationship(
        back_populates="schueler", cascade="all, delete", passive_deletes=True
    )
    sitzplaetze: Mapped[list["Sitzplatz"]] = relationship(
        back_populates="schueler", cascade="all, delete", passive_deletes=True
    )


class Kurs(Base):
    """A subject taught in one class. A course belongs to exactly one class."""

    __tablename__ = "kurs"

    id: Mapped[int] = mapped_column(primary_key=True)
    klasse_id: Mapped[int] = mapped_column(
        ForeignKey("klasse.id", ondelete="CASCADE"), nullable=False
    )
    fach: Mapped[str] = mapped_column(String, nullable=False)
    notiz: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Section 4.5: weighting of the two terms for the year grade, per course.
    gewicht_halbjahr_1: Mapped[Decimal] = mapped_column(
        DecimalText, nullable=False, default=VORGABE_GEWICHT_HALBJAHR
    )
    gewicht_halbjahr_2: Mapped[Decimal] = mapped_column(
        DecimalText, nullable=False, default=VORGABE_GEWICHT_HALBJAHR
    )

    klasse: Mapped["Klasse"] = relationship(back_populates="kurse")
    teilnahmen: Mapped[list["Kursteilnahme"]] = relationship(
        back_populates="kurs", cascade="all, delete", passive_deletes=True
    )
    notengruppen: Mapped[list["Notengruppe"]] = relationship(
        back_populates="kurs", cascade="all, delete", passive_deletes=True
    )
    ueberschreibungen: Mapped[list["Notenueberschreibung"]] = relationship(
        back_populates="kurs", cascade="all, delete", passive_deletes=True
    )

    __table_args__ = (UniqueConstraint("klasse_id", "fach"),)


class Kursteilnahme(Base):
    """Explicit n:m link between pupil and course (3.1).

    Not every pupil of a class attends every course of that class; without
    this table the class averages would be wrong.
    """

    __tablename__ = "kursteilnahme"

    kurs_id: Mapped[int] = mapped_column(
        ForeignKey("kurs.id", ondelete="CASCADE"), primary_key=True
    )
    schueler_id: Mapped[int] = mapped_column(
        ForeignKey("schueler.id", ondelete="CASCADE"), primary_key=True
    )
    ist_aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    kurs: Mapped["Kurs"] = relationship(back_populates="teilnahmen")
    schueler: Mapped["Schueler"] = relationship(back_populates="kursteilnahmen")


class Notengruppe(Base):
    """Weights are defined per course and term (3.1).

    They need not add up to 100 and are never normalised: the calculation is
    single-stage (4.4), so a weight acts as a factor and only the ratios
    between the groups matter. A group without a counted grade drops out of
    numerator and denominator by itself.

    The database cannot express that ``halbjahr`` must belong to the same
    school year as ``kurs.klasse.schuljahr`` without redundant columns and a
    composite key. The service layer checks it.
    """

    __tablename__ = "notengruppe"

    id: Mapped[int] = mapped_column(primary_key=True)
    kurs_id: Mapped[int] = mapped_column(
        ForeignKey("kurs.id", ondelete="CASCADE"), nullable=False
    )
    halbjahr_id: Mapped[int] = mapped_column(
        ForeignKey("halbjahr.id", ondelete="CASCADE"), nullable=False
    )
    bezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    gewicht: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    reihenfolge: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    kurs: Mapped["Kurs"] = relationship(back_populates="notengruppen")
    halbjahr: Mapped["Halbjahr"] = relationship(back_populates="notengruppen")
    leistungen: Mapped[list["Leistung"]] = relationship(
        back_populates="notengruppe", cascade="all, delete", passive_deletes=True
    )

    __table_args__ = (UniqueConstraint("kurs_id", "halbjahr_id", "bezeichnung"),)


class Leistung(Base):
    """One assessment occasion, e.g. "2. Klassenarbeit".

    ``gewicht`` weights this assessment within its Notengruppe (4.4). There is
    no ``max_punkte``: grades are entered directly, not as points.
    """

    __tablename__ = "leistung"

    id: Mapped[int] = mapped_column(primary_key=True)
    notengruppe_id: Mapped[int] = mapped_column(
        ForeignKey("notengruppe.id", ondelete="CASCADE"), nullable=False
    )
    bezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    datum: Mapped[date] = mapped_column(Date, nullable=False)
    gewicht: Mapped[Decimal] = mapped_column(
        DecimalText, nullable=False, default=Decimal("1.0")
    )
    notiz: Mapped[str | None] = mapped_column(Text, nullable=True)

    notengruppe: Mapped["Notengruppe"] = relationship(back_populates="leistungen")
    noten: Mapped[list["Note"]] = relationship(
        back_populates="leistung", cascade="all, delete", passive_deletes=True
    )


class Note(Base):
    """One pupil's assessment of one Leistung.

    ``notenwert`` holds one of the sixteen canonical values of 4.1 (0.7 for
    "1+" up to 6.0). The mapping to and from the displayed grade lives in the
    grading module, not here.

    It stays NULL for ``nicht_erbracht``: the 6.0 that such a status
    contributes is produced by the grading module from the status and is never
    written into the row. Otherwise a later status change could no longer be
    told apart from a genuine 6.
    """

    __tablename__ = "note"

    id: Mapped[int] = mapped_column(primary_key=True)
    leistung_id: Mapped[int] = mapped_column(
        ForeignKey("leistung.id", ondelete="CASCADE"), nullable=False
    )
    schueler_id: Mapped[int] = mapped_column(
        ForeignKey("schueler.id", ondelete="CASCADE"), nullable=False
    )
    notenwert: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    notiz: Mapped[str | None] = mapped_column(Text, nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    geaendert_am: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    leistung: Mapped["Leistung"] = relationship(back_populates="noten")
    schueler: Mapped["Schueler"] = relationship(back_populates="noten")

    __table_args__ = (
        UniqueConstraint("leistung_id", "schueler_id"),
        CheckConstraint(_in_clause("status", NoteStatus), name="status_gueltig"),
        CheckConstraint(
            "status <> 'gewertet' OR notenwert IS NOT NULL", name="notenwert_bei_gewertet"
        ),
    )


class Notenueberschreibung(Base):
    """The grade the teacher fixes for a term or the year.

    Append-only: there is no unique constraint and no ``geaendert_am``. The
    valid record is the most recent one per (pupil, course, period), which
    gives the history of a report grade at no extra cost.

    The calculated value is never overwritten, only overlaid (3.1) — it is not
    stored here at all, it is recomputed and displayed next to this one.
    """

    __tablename__ = "notenueberschreibung"

    id: Mapped[int] = mapped_column(primary_key=True)
    schueler_id: Mapped[int] = mapped_column(
        ForeignKey("schueler.id", ondelete="CASCADE"), nullable=False
    )
    kurs_id: Mapped[int] = mapped_column(
        ForeignKey("kurs.id", ondelete="CASCADE"), nullable=False
    )
    bezugszeitraum: Mapped[str] = mapped_column(String, nullable=False)
    notenwert: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    quelle: Mapped[str] = mapped_column(String, nullable=False)
    begruendung: Mapped[str | None] = mapped_column(Text, nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )

    schueler: Mapped["Schueler"] = relationship(back_populates="ueberschreibungen")
    kurs: Mapped["Kurs"] = relationship(back_populates="ueberschreibungen")

    __table_args__ = (
        CheckConstraint(
            _in_clause("bezugszeitraum", Bezugszeitraum), name="bezugszeitraum_gueltig"
        ),
        CheckConstraint(_in_clause("quelle", UeberschreibungQuelle), name="quelle_gueltig"),
    )


class NoteHistorie(Base):
    """Append-only log of every change to a Note (3.2).

    Three deviations from the four columns named in 3.2, each forced:

    * ``note_id`` carries **no** foreign key. A deletion is one of the events
      to be recorded, and ``ON DELETE CASCADE`` would remove exactly the row
      that documents it. The reference may therefore point at a Note that no
      longer exists; that is intended, not an oversight.
    * ``schueler_id`` and ``leistung_id`` do have foreign keys with cascade.
      Section 11 requires deleting a pupil or a school year to remove the
      history as well, and after the Note is gone ``note_id`` alone would not
      find these rows.
    * Status is recorded next to the value. A change from ``gewertet`` to
      ``nicht_erbracht`` changes the result without changing the value.

    Written by the service layer, never updated, never deleted except by the
    delete function.
    """

    __tablename__ = "note_historie"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(Integer, nullable=False)
    schueler_id: Mapped[int] = mapped_column(
        ForeignKey("schueler.id", ondelete="CASCADE"), nullable=False
    )
    leistung_id: Mapped[int] = mapped_column(
        ForeignKey("leistung.id", ondelete="CASCADE"), nullable=False
    )
    aktion: Mapped[str] = mapped_column(String, nullable=False)
    alter_notenwert: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    alter_status: Mapped[str | None] = mapped_column(String, nullable=True)
    neuer_notenwert: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    neuer_status: Mapped[str | None] = mapped_column(String, nullable=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint(_in_clause("aktion", HistorieAktion), name="aktion_gueltig"),
        CheckConstraint(
            f"alter_status IS NULL OR {_in_clause('alter_status', NoteStatus)}",
            name="alter_status_gueltig",
        ),
        CheckConstraint(
            f"neuer_status IS NULL OR {_in_clause('neuer_status', NoteStatus)}",
            name="neuer_status_gueltig",
        ),
    )


class Sitzplan(Base):
    """The seating order of one class (5.6).

    Exactly one per class -- hence ``UNIQUE(klasse_id)``. The row is created
    when the plan is opened for the first time, not together with the class:
    a class that is never seated needs none.

    Only **occupied** seats carry a :class:`Sitzplatz` row; the empty ones
    follow from the grid. That a seat lies inside the grid cannot be a CHECK
    -- SQLite allows no subquery there -- so the service layer enforces it,
    the same way it enforces the term of a Notengruppe.
    """

    __tablename__ = "sitzplan"

    id: Mapped[int] = mapped_column(primary_key=True)
    klasse_id: Mapped[int] = mapped_column(
        ForeignKey("klasse.id", ondelete="CASCADE"), nullable=False
    )
    reihen: Mapped[int] = mapped_column(
        Integer, nullable=False, default=VORGABE_REIHEN
    )
    sitze_je_reihe: Mapped[int] = mapped_column(
        Integer, nullable=False, default=VORGABE_SITZE_JE_REIHE
    )

    klasse: Mapped["Klasse"] = relationship(back_populates="sitzplan")
    plaetze: Mapped[list["Sitzplatz"]] = relationship(
        back_populates="sitzplan", cascade="all, delete", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("klasse_id"),
        CheckConstraint(
            f"reihen BETWEEN {MIN_RASTER} AND {MAX_RASTER}", name="reihen_gueltig"
        ),
        CheckConstraint(
            f"sitze_je_reihe BETWEEN {MIN_RASTER} AND {MAX_RASTER}",
            name="sitze_je_reihe_gueltig",
        ),
    )


class Sitzplatz(Base):
    """One occupied seat of a seating plan (5.6).

    A seat holds at most one pupil, and a pupil sits on at most one seat of a
    plan. Both are unique constraints: the other cases have no sensible
    display, and a plan that cannot be displayed is worse than a refused
    input.

    The row **survives the pupil going inactive**. The plan hides an inactive
    pupil and shows the seat as free, so deactivating stays as reversible here
    as it is everywhere else in this application. Assigning that seat to
    someone else replaces the old row.
    """

    __tablename__ = "sitzplatz"

    id: Mapped[int] = mapped_column(primary_key=True)
    sitzplan_id: Mapped[int] = mapped_column(
        ForeignKey("sitzplan.id", ondelete="CASCADE"), nullable=False
    )
    schueler_id: Mapped[int] = mapped_column(
        ForeignKey("schueler.id", ondelete="CASCADE"), nullable=False
    )
    reihe: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    sitzplan: Mapped["Sitzplan"] = relationship(back_populates="plaetze")
    schueler: Mapped["Schueler"] = relationship(back_populates="sitzplaetze")

    __table_args__ = (
        UniqueConstraint("sitzplan_id", "reihe", "position"),
        UniqueConstraint("sitzplan_id", "schueler_id"),
        CheckConstraint(f"reihe >= {MIN_RASTER}", name="reihe_gueltig"),
        CheckConstraint(f"position >= {MIN_RASTER}", name="position_gueltig"),
    )


class Einstellung(Base):
    """Persisted settings (4.4 rounding threshold, 5.1/6 sorting and name format).

    There is no user table and there will not be one, so a single key/value
    table holds the settings of the one operator. Defaults live in the code;
    a row exists only where the default was changed.
    """

    __tablename__ = "einstellung"

    schluessel: Mapped[str] = mapped_column(String, primary_key=True)
    wert: Mapped[str] = mapped_column(Text, nullable=False)
