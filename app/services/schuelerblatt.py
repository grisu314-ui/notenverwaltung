"""The grade sheet of one pupil (specification 5.2).

Assembles a ready-made structure for display: per course the terms, inside
them the grade groups with their assessments, plus the term and year results
and any grade the teacher fixed.

Free of any web dependency, so it can be checked without a test client.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import (
    Halbjahr,
    Kurs,
    Leistung,
    Note,
    Notengruppe,
    Notenueberschreibung,
    Schueler,
)
from app.enums import Bezugszeitraum
from app.grading.berechnung import Ergebnis
from app.grading.notenwert import als_anzeige, als_dezimalanzeige
from app.services.calculation import (
    BEZUGSZEITRAUM_JE_HALBJAHR,
    festsetzung,
    halbjahresergebnis,
    jahresergebnis,
)
from app.services.sorting import vereinfacht

OHNE_WERT = "—"


@dataclass(frozen=True)
class LeistungMitNote:
    leistung: Leistung
    note: Note | None


@dataclass(frozen=True)
class Gruppenblock:
    notengruppe: Notengruppe
    eintraege: tuple[LeistungMitNote, ...]


@dataclass(frozen=True)
class Halbjahrblock:
    halbjahr: Halbjahr
    gruppen: tuple[Gruppenblock, ...]
    ergebnis: Ergebnis | None
    festsetzung: Notenueberschreibung | None

    @property
    def anzeige(self) -> str:
        return notenanzeige(self.ergebnis, self.festsetzung)


@dataclass(frozen=True)
class Kursblock:
    kurs: Kurs
    nimmt_teil: bool
    halbjahre: tuple[Halbjahrblock, ...]
    jahresergebnis: Ergebnis | None
    jahresfestsetzung: Notenueberschreibung | None

    @property
    def jahresanzeige(self) -> str:
        return notenanzeige(self.jahresergebnis, self.jahresfestsetzung)


@dataclass(frozen=True)
class Schuelerblatt:
    schueler: Schueler
    kurse: tuple[Kursblock, ...]


def notenanzeige(
    ergebnis: Ergebnis | None, gesetzt: Notenueberschreibung | None
) -> str:
    """Whole grade and calculated value side by side (4.5, test case T-9).

    The calculated value is never overwritten, only overlaid, so it stays
    visible next to a grade the teacher fixed: "2 (berechnet 2,6)".
    """
    if gesetzt is not None and ergebnis is not None:
        return (
            f"{als_anzeige(gesetzt.notenwert)} "
            f"(berechnet {als_dezimalanzeige(ergebnis.wert)})"
        )
    if gesetzt is not None:
        return f"{als_anzeige(gesetzt.notenwert)} (festgesetzt)"
    if ergebnis is not None:
        return f"{ergebnis.ganze_note} (berechnet {als_dezimalanzeige(ergebnis.wert)})"
    return OHNE_WERT


def _note_des_schuelers(leistung: Leistung, schueler: Schueler) -> Note | None:
    for note in leistung.noten:
        if note.schueler_id == schueler.id:
            return note
    return None


def _gruppenbloecke(
    kurs: Kurs, schueler: Schueler, halbjahr: Halbjahr
) -> tuple[Gruppenblock, ...]:
    gruppen = sorted(
        (g for g in kurs.notengruppen if g.halbjahr_id == halbjahr.id),
        key=lambda gruppe: (gruppe.reihenfolge, gruppe.id),
    )
    bloecke = []
    for gruppe in gruppen:
        leistungen = sorted(
            gruppe.leistungen, key=lambda leistung: (leistung.datum, leistung.id)
        )
        bloecke.append(
            Gruppenblock(
                notengruppe=gruppe,
                eintraege=tuple(
                    LeistungMitNote(
                        leistung=leistung, note=_note_des_schuelers(leistung, schueler)
                    )
                    for leistung in leistungen
                ),
            )
        )
    return tuple(bloecke)


def _hat_noten(kurs: Kurs, schueler: Schueler) -> bool:
    return any(
        note.schueler_id == schueler.id
        for gruppe in kurs.notengruppen
        for leistung in gruppe.leistungen
        for note in leistung.noten
    )


def kursblock(session: Session, kurs: Kurs, schueler: Schueler) -> Kursblock:
    halbjahre = sorted(kurs.klasse.schuljahr.halbjahre, key=lambda h: h.nummer)
    bloecke = tuple(
        Halbjahrblock(
            halbjahr=halbjahr,
            gruppen=_gruppenbloecke(kurs, schueler, halbjahr),
            ergebnis=halbjahresergebnis(kurs, schueler, halbjahr),
            festsetzung=festsetzung(
                session, kurs, schueler, BEZUGSZEITRAUM_JE_HALBJAHR[halbjahr.nummer]
            ),
        )
        for halbjahr in halbjahre
    )
    teilnahme = next(
        (t for t in kurs.teilnahmen if t.schueler_id == schueler.id), None
    )
    return Kursblock(
        kurs=kurs,
        nimmt_teil=bool(teilnahme and teilnahme.ist_aktiv),
        halbjahre=bloecke,
        jahresergebnis=jahresergebnis(session, kurs, schueler),
        jahresfestsetzung=festsetzung(session, kurs, schueler, Bezugszeitraum.JAHR),
    )


def blatt(session: Session, schueler: Schueler) -> Schuelerblatt:
    """All grades of one pupil, grouped by course (5.2).

    A course appears when the pupil takes part in it **or** has a grade in it.
    Otherwise grades entered earlier would vanish from the view without trace
    once the pupil was taken out of the course.
    """
    kurse = []
    for kurs in sorted(
        schueler.klasse.kurse, key=lambda k: (vereinfacht(k.fach), k.fach)
    ):
        teilnahme = next(
            (t for t in kurs.teilnahmen if t.schueler_id == schueler.id), None
        )
        if (teilnahme and teilnahme.ist_aktiv) or _hat_noten(kurs, schueler):
            kurse.append(kursblock(session, kurs, schueler))
    return Schuelerblatt(schueler=schueler, kurse=tuple(kurse))
