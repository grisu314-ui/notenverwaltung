"""Calculation of the term and year grade.

Free of any database or web dependency: input and output are plain
dataclasses, never ORM objects, so the calculation is testable without a
running application.

**Deviation from 4.4, decided by the operator.** The specification describes a
two-stage calculation: a mean per Notengruppe first, then a mean of those
group means weighted by group weight. That makes a group's influence
independent of how many grades it holds. The operator wants the opposite --
many small grades may weigh more -- so the calculation is single-stage:

    Halbjahresnote = sum(notenwert * gruppengewicht * leistungsgewicht)
                     ----------------------------------------------------
                     sum(gruppengewicht * leistungsgewicht)

Group weights keep their effect: a grade in a group weighted 70 counts more
than one in a group weighted 30. What changes is that a group with four
grades now outweighs a group with one at equal group weight.

This reproduces the expected value of test case T-1 exactly, which the
two-stage rule of 4.4 does not.

A group holding no grade that enters the calculation contributes to neither
numerator nor denominator and thus drops out by itself; the normalisation
demanded by 4.4 needs no code of its own (open point O-2).
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from app.enums import NoteStatus
from app.grading.notenwert import ganze_notenstufe, pruefe_notenwert, runde_auf_anzeige

# The value a "nicht erbracht" grade contributes (4.3). It is produced here,
# from the status, and is never stored in the database -- otherwise a later
# change of status could not be told apart from a genuine 6.
WERT_NICHT_ERBRACHT = Decimal("6.0")


class UngueltigeGewichtungError(ValueError):
    """A weight that is zero or negative would silently drop or invert a grade."""


class FehlenderNotenwertError(ValueError):
    """A grade counted as ``gewertet`` without a value.

    Never silently treated as 0 or 6.
    """


def _pruefe_gewicht(gewicht: Decimal, bezeichnung: str) -> Decimal:
    if gewicht <= 0:
        raise UngueltigeGewichtungError(
            f"{bezeichnung} muss größer als 0 sein, ist aber {gewicht}."
        )
    return gewicht


@dataclass(frozen=True)
class Einzelnote:
    """One pupil's grade for one Leistung, with that Leistung's weight."""

    status: NoteStatus
    notenwert: Decimal | None = None
    gewicht: Decimal = Decimal("1.0")

    def __post_init__(self) -> None:
        _pruefe_gewicht(self.gewicht, "Das Gewicht einer Leistung")
        if self.notenwert is not None:
            pruefe_notenwert(self.notenwert)
        if self.status == NoteStatus.GEWERTET and self.notenwert is None:
            raise FehlenderNotenwertError(
                "Eine gewertete Note braucht einen Notenwert. Ein fehlender Wert "
                "wird nie als 0 oder 6 behandelt."
            )


@dataclass(frozen=True)
class Notengruppe:
    """A weighted group of grades, e.g. "Klassenarbeiten" (4.4)."""

    gewicht: Decimal
    noten: tuple[Einzelnote, ...] = ()

    def __post_init__(self) -> None:
        _pruefe_gewicht(self.gewicht, "Das Gewicht einer Notengruppe")


@dataclass(frozen=True)
class Ergebnis:
    """A calculated grade: the displayed value and the whole grade from it."""

    wert: Decimal
    ganze_note: int


def beitrag(status: NoteStatus, notenwert: Decimal | None) -> Decimal | None:
    """The value a grade contributes, or None if it does not enter at all.

    Public because the class statistics of the course overview have to follow
    exactly the same rule; two places deciding what counts would eventually
    disagree.
    """
    if status == NoteStatus.NICHT_GEWERTET:
        return None
    if status == NoteStatus.NICHT_ERBRACHT:
        return WERT_NICHT_ERBRACHT
    return notenwert


def _rechenwert(note: Einzelnote) -> Decimal | None:
    return beitrag(note.status, note.notenwert)


def _gewichtetes_mittel(paare: Sequence[tuple[Decimal, Decimal]]) -> Decimal | None:
    """Weighted mean of (value, weight) pairs, or None if nothing counts."""
    zaehler = Decimal(0)
    nenner = Decimal(0)
    for wert, gewicht in paare:
        zaehler += wert * gewicht
        nenner += gewicht
    if nenner == 0:
        return None
    return zaehler / nenner


def halbjahresnote(gruppen: Sequence[Notengruppe]) -> Ergebnis | None:
    """Term grade for one pupil in one course.

    Returns None when not a single grade enters the calculation -- no
    calculation, no division by zero, empty display (T-7).
    """
    paare = [
        (wert, gruppe.gewicht * note.gewicht)
        for gruppe in gruppen
        for note in gruppe.noten
        if (wert := _rechenwert(note)) is not None
    ]
    return _als_ergebnis(_gewichtetes_mittel(paare))


def jahresnote(
    halbjahr_1: Decimal | None,
    halbjahr_2: Decimal | None,
    gewicht_halbjahr_1: Decimal,
    gewicht_halbjahr_2: Decimal,
) -> Ergebnis | None:
    """Year grade from the two term grades (4.5).

    The caller passes the term grade that applies: the grade the teacher fixed
    where there is one, otherwise the calculated value. This module knows
    nothing about Notenueberschreibung.

    Returns None while either term has no grade -- in January the second term
    is empty, and no year grade is shown rather than falling back to the one
    term that exists.
    """
    _pruefe_gewicht(gewicht_halbjahr_1, "Das Gewicht von Halbjahr 1")
    _pruefe_gewicht(gewicht_halbjahr_2, "Das Gewicht von Halbjahr 2")
    if halbjahr_1 is None or halbjahr_2 is None:
        return None
    return _als_ergebnis(
        _gewichtetes_mittel(
            [(halbjahr_1, gewicht_halbjahr_1), (halbjahr_2, gewicht_halbjahr_2)]
        )
    )


def _als_ergebnis(roh: Decimal | None) -> Ergebnis | None:
    if roh is None:
        return None
    wert = runde_auf_anzeige(roh)
    return Ergebnis(wert=wert, ganze_note=ganze_notenstufe(wert))
