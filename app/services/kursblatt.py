"""The course overview as a matrix (specification 5.3).

Rows are pupils, columns are assessments grouped by Notengruppe, and to the
right the calculated result. Below the matrix a Notenspiegel per assessment:
average and distribution.

**Deviation from 5.3, decided by the operator: no group averages.** Since the
calculation became single-stage, a per-group mean is not a step of it, and the
total is expressly not the weighted mean of such means. A column inviting that
arithmetic would mislead more than it informs.

Read-only. Grades are entered through the serial entry of 5.4; every column
heading links there.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import Halbjahr, Kurs, Leistung, Note, Notengruppe, Schueler
from app.enums import Bezugszeitraum, NoteStatus
from app.grading.berechnung import Ergebnis, beitrag
from app.grading.notenwert import ganze_notenstufe, runde_auf_anzeige
from app.services.calculation import (
    BEZUGSZEITRAUM_JE_HALBJAHR,
    festsetzung,
    halbjahresergebnis,
    jahresergebnis,
)
from app.services.settings import lies_einstellungen
from app.services.sorting import namensschluessel

ANSICHT_HALBJAHR_1 = "halbjahr_1"
ANSICHT_HALBJAHR_2 = "halbjahr_2"
ANSICHT_JAHR = "jahr"
ANSICHTEN = (ANSICHT_HALBJAHR_1, ANSICHT_HALBJAHR_2, ANSICHT_JAHR)

NOTENSTUFEN = (1, 2, 3, 4, 5, 6)


@dataclass(frozen=True)
class Spaltengruppe:
    """One Notengruppe with its assessments, i.e. a block of columns."""

    halbjahr: Halbjahr
    notengruppe: Notengruppe
    leistungen: tuple[Leistung, ...]


@dataclass(frozen=True)
class Zeile:
    schueler: Schueler
    noten: dict[int, Note | None]
    ergebnis_halbjahr: dict[int, Ergebnis | None]
    festsetzung_halbjahr: dict[int, object]
    jahresergebnis: Ergebnis | None
    jahresfestsetzung: object


@dataclass(frozen=True)
class Notenspiegel:
    """Average and distribution of one assessment across the course."""

    leistung: Leistung
    durchschnitt: Decimal | None
    verteilung: dict[int, int]
    nicht_gewertet: int

    @property
    def anzahl(self) -> int:
        return sum(self.verteilung.values())


@dataclass(frozen=True)
class Kursblatt:
    kurs: Kurs
    ansicht: str
    halbjahre: tuple[Halbjahr, ...]
    gruppen: tuple[Spaltengruppe, ...]
    zeilen: tuple[Zeile, ...]
    spiegel: tuple[Notenspiegel, ...]

    @property
    def leistungen(self) -> tuple[Leistung, ...]:
        return tuple(
            leistung for gruppe in self.gruppen for leistung in gruppe.leistungen
        )


def _teilnehmer(kurs: Kurs, session: Session) -> list[Schueler]:
    einstellungen = lies_einstellungen(session)
    aktive = [
        teilnahme.schueler
        for teilnahme in kurs.teilnahmen
        if teilnahme.ist_aktiv and teilnahme.schueler.ist_aktiv
    ]
    return sorted(
        aktive,
        key=lambda s: namensschluessel(s.vorname, s.nachname, einstellungen.sortierung),
    )


def _gezeigte_halbjahre(kurs: Kurs, ansicht: str) -> tuple[Halbjahr, ...]:
    halbjahre = sorted(kurs.klasse.schuljahr.halbjahre, key=lambda h: h.nummer)
    if ansicht == ANSICHT_HALBJAHR_1:
        return tuple(h for h in halbjahre if h.nummer == 1)
    if ansicht == ANSICHT_HALBJAHR_2:
        return tuple(h for h in halbjahre if h.nummer == 2)
    return tuple(halbjahre)


def _spaltengruppen(kurs: Kurs, halbjahre) -> tuple[Spaltengruppe, ...]:
    gruppen = []
    for halbjahr in halbjahre:
        passende = sorted(
            (g for g in kurs.notengruppen if g.halbjahr_id == halbjahr.id),
            key=lambda gruppe: (gruppe.reihenfolge, gruppe.id),
        )
        for notengruppe in passende:
            gruppen.append(
                Spaltengruppe(
                    halbjahr=halbjahr,
                    notengruppe=notengruppe,
                    leistungen=tuple(
                        sorted(
                            notengruppe.leistungen,
                            key=lambda leistung: (leistung.datum, leistung.id),
                        )
                    ),
                )
            )
    return tuple(gruppen)


def _note_von(leistung: Leistung, schueler_id: int) -> Note | None:
    for note in leistung.noten:
        if note.schueler_id == schueler_id:
            return note
    return None


def notenspiegel(leistung: Leistung, teilnehmer: list[Schueler]) -> Notenspiegel:
    """Average and distribution of one assessment.

    Follows the same rule as the grade calculation: ``nicht_erbracht`` counts
    as 6.0, ``nicht_gewertet`` is left out entirely and reported separately --
    otherwise a test where half the class was excused would look better than
    it was.

    A tendency counts towards its base grade: 2+ and 2- both land on 2.
    """
    werte: list[Decimal] = []
    ohne_wertung = 0
    for schueler in teilnehmer:
        note = _note_von(leistung, schueler.id)
        if note is None:
            continue
        if note.status == NoteStatus.NICHT_GEWERTET:
            ohne_wertung += 1
            continue
        wert = beitrag(NoteStatus(note.status), note.notenwert)
        if wert is not None:
            werte.append(wert)

    verteilung = {stufe: 0 for stufe in NOTENSTUFEN}
    for wert in werte:
        verteilung[ganze_notenstufe(wert)] += 1

    durchschnitt = (
        runde_auf_anzeige(sum(werte) / Decimal(len(werte))) if werte else None
    )
    return Notenspiegel(
        leistung=leistung,
        durchschnitt=durchschnitt,
        verteilung=verteilung,
        nicht_gewertet=ohne_wertung,
    )


def blatt(session: Session, kurs: Kurs, ansicht: str = ANSICHT_HALBJAHR_1) -> Kursblatt:
    if ansicht not in ANSICHTEN:
        ansicht = ANSICHT_HALBJAHR_1

    halbjahre = _gezeigte_halbjahre(kurs, ansicht)
    gruppen = _spaltengruppen(kurs, halbjahre)
    teilnehmer = _teilnehmer(kurs, session)
    alle_halbjahre = sorted(kurs.klasse.schuljahr.halbjahre, key=lambda h: h.nummer)

    zeilen = []
    for schueler in teilnehmer:
        noten = {
            leistung.id: _note_von(leistung, schueler.id)
            for gruppe in gruppen
            for leistung in gruppe.leistungen
        }
        zeilen.append(
            Zeile(
                schueler=schueler,
                noten=noten,
                ergebnis_halbjahr={
                    halbjahr.nummer: halbjahresergebnis(kurs, schueler, halbjahr)
                    for halbjahr in alle_halbjahre
                },
                festsetzung_halbjahr={
                    halbjahr.nummer: festsetzung(
                        session,
                        kurs,
                        schueler,
                        BEZUGSZEITRAUM_JE_HALBJAHR[halbjahr.nummer],
                    )
                    for halbjahr in alle_halbjahre
                },
                jahresergebnis=jahresergebnis(session, kurs, schueler),
                jahresfestsetzung=festsetzung(
                    session, kurs, schueler, Bezugszeitraum.JAHR
                ),
            )
        )

    spiegel = tuple(
        notenspiegel(leistung, teilnehmer)
        for gruppe in gruppen
        for leistung in gruppe.leistungen
    )

    return Kursblatt(
        kurs=kurs,
        ansicht=ansicht,
        halbjahre=halbjahre,
        gruppen=gruppen,
        zeilen=tuple(zeilen),
        spiegel=spiegel,
    )
