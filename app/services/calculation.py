"""Adapter between the database and the grading module.

:mod:`app.grading` knows nothing about SQLAlchemy on purpose. This is the one
place that translates stored rows into its input, so the rule stays in exactly
one place.
"""

from sqlalchemy.orm import Session

from app.db.models import Halbjahr, Kurs, Leistung, Note, Notenueberschreibung, Schueler
from app.enums import Bezugszeitraum, NoteStatus
from app.grading.berechnung import (
    Einzelnote,
    Ergebnis,
    Notengruppe,
    halbjahresnote,
    jahresnote,
)

BEZUGSZEITRAUM_JE_HALBJAHR = {
    1: Bezugszeitraum.HALBJAHR_1,
    2: Bezugszeitraum.HALBJAHR_2,
}


def _note_des_schuelers(leistung: Leistung, schueler: Schueler) -> Note | None:
    for note in leistung.noten:
        if note.schueler_id == schueler.id:
            return note
    return None


def halbjahresergebnis(
    kurs: Kurs, schueler: Schueler, halbjahr: Halbjahr
) -> Ergebnis | None:
    """Calculated term grade, or None if nothing can be calculated (T-7)."""
    gruppen = []
    for notengruppe in kurs.notengruppen:
        if notengruppe.halbjahr_id != halbjahr.id:
            continue
        noten = []
        for leistung in notengruppe.leistungen:
            note = _note_des_schuelers(leistung, schueler)
            if note is None:
                continue
            noten.append(
                Einzelnote(
                    status=NoteStatus(note.status),
                    notenwert=note.notenwert,
                    gewicht=leistung.gewicht,
                )
            )
        gruppen.append(Notengruppe(gewicht=notengruppe.gewicht, noten=tuple(noten)))
    return halbjahresnote(gruppen)


def festsetzung(
    session: Session,
    kurs: Kurs,
    schueler: Schueler,
    bezugszeitraum: Bezugszeitraum,
) -> Notenueberschreibung | None:
    """The grade the teacher fixed, i.e. the most recent record (3.1).

    The table is append-only; the newest row per pupil, course and period is
    the one in force, and the older ones remain readable as its history.
    """
    return (
        session.query(Notenueberschreibung)
        .filter_by(
            schueler_id=schueler.id,
            kurs_id=kurs.id,
            bezugszeitraum=str(bezugszeitraum),
        )
        .order_by(
            Notenueberschreibung.erstellt_am.desc(), Notenueberschreibung.id.desc()
        )
        .first()
    )


def _massgebliche_halbjahresnote(
    session: Session, kurs: Kurs, schueler: Schueler, halbjahr: Halbjahr
):
    """The term grade the year grade is built from.

    The grade the teacher fixed takes precedence; where none exists, the
    calculated value is used.
    """
    fixiert = festsetzung(
        session, kurs, schueler, BEZUGSZEITRAUM_JE_HALBJAHR[halbjahr.nummer]
    )
    if fixiert is not None:
        return fixiert.notenwert
    ergebnis = halbjahresergebnis(kurs, schueler, halbjahr)
    return None if ergebnis is None else ergebnis.wert


def jahresergebnis(session: Session, kurs: Kurs, schueler: Schueler) -> Ergebnis | None:
    """Calculated year grade, or None while either term has no grade (4.5)."""
    halbjahre = {
        halbjahr.nummer: halbjahr for halbjahr in kurs.klasse.schuljahr.halbjahre
    }
    if set(halbjahre) != {1, 2}:
        return None
    return jahresnote(
        _massgebliche_halbjahresnote(session, kurs, schueler, halbjahre[1]),
        _massgebliche_halbjahresnote(session, kurs, schueler, halbjahre[2]),
        kurs.gewicht_halbjahr_1,
        kurs.gewicht_halbjahr_2,
    )
