"""Entering grades and recording every change (specification 5.4, 3.2).

Two things matter more here than anywhere else in the application:

* A grade is either written and confirmed, or it is not written and that is
  visible. Nothing in this module reports success before the caller's commit.
* Every change is appended to ``note_historie`` **in the same transaction**
  as the change itself. Otherwise grade and history could drift apart, and
  the history exists precisely for the case where someone asks what the grade
  was before.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import (
    Kursteilnahme,
    Leistung,
    Note,
    NoteHistorie,
    Notengruppe,
    Schueler,
)
from app.enums import HistorieAktion, NoteStatus
from app.grading.notenwert import UngueltigeNoteError, pruefe_notenwert
from app.services.fehler import Verwaltungsfehler


def _pruefe_teilnahme(session: Session, leistung: Leistung, schueler: Schueler) -> None:
    """A grade only for a pupil who actually attends the course (3.1).

    No foreign key can express this: pupil and Leistung are only connected
    through the course.
    """
    kurs_id = leistung.notengruppe.kurs_id
    teilnahme = session.get(Kursteilnahme, (kurs_id, schueler.id))
    if teilnahme is None or not teilnahme.ist_aktiv:
        raise Verwaltungsfehler(
            f"{schueler.vorname} {schueler.nachname} nimmt an diesem Kurs nicht "
            "(mehr) teil; eine Note lässt sich deshalb nicht eintragen."
        )


def _pruefe_eingabe(status: NoteStatus, notenwert: Decimal | None) -> Decimal | None:
    """Only a counted grade carries a value; the others carry none.

    A missing value is never turned into 0 or 6 here. The 6.0 that
    ``nicht_erbracht`` contributes is produced by the grading module from the
    status and is not stored.
    """
    if status != NoteStatus.GEWERTET:
        return None
    if notenwert is None:
        raise Verwaltungsfehler("Eine gewertete Note braucht einen Notenwert.")
    try:
        return pruefe_notenwert(notenwert)
    except UngueltigeNoteError as fehler:
        raise Verwaltungsfehler(str(fehler)) from fehler


def _protokolliere(
    session: Session,
    note: Note,
    aktion: HistorieAktion,
    alter_notenwert: Decimal | None,
    alter_status: str | None,
    neuer_notenwert: Decimal | None,
    neuer_status: str | None,
) -> None:
    session.add(
        NoteHistorie(
            note_id=note.id,
            schueler_id=note.schueler_id,
            leistung_id=note.leistung_id,
            aktion=aktion,
            alter_notenwert=alter_notenwert,
            alter_status=alter_status,
            neuer_notenwert=neuer_notenwert,
            neuer_status=neuer_status,
        )
    )


def note_von(leistung: Leistung, schueler: Schueler) -> Note | None:
    for note in leistung.noten:
        if note.schueler_id == schueler.id:
            return note
    return None


def setze_note(
    session: Session,
    leistung: Leistung,
    schueler: Schueler,
    status: NoteStatus,
    notenwert: Decimal | None = None,
) -> Note:
    """Write or change one grade and record the change.

    Caller commits. Nothing is confirmed to the user before that.
    """
    _pruefe_teilnahme(session, leistung, schueler)
    wert = _pruefe_eingabe(status, notenwert)

    note = note_von(leistung, schueler)
    if note is None:
        note = Note(
            leistung=leistung, schueler=schueler, status=str(status), notenwert=wert
        )
        session.add(note)
        session.flush()  # the history entry needs the id
        _protokolliere(
            session, note, HistorieAktion.ANGELEGT, None, None, wert, str(status)
        )
        return note

    alter_wert, alter_status = note.notenwert, note.status
    if alter_wert == wert and alter_status == str(status):
        return note  # nothing changed, nothing to record

    note.notenwert = wert
    note.status = str(status)
    session.flush()
    _protokolliere(
        session,
        note,
        HistorieAktion.GEAENDERT,
        alter_wert,
        alter_status,
        wert,
        str(status),
    )
    return note


def loesche_note(session: Session, leistung: Leistung, schueler: Schueler) -> None:
    """Remove a grade entirely and record that it was removed.

    The history entry outlives the row it describes; that is why it carries no
    foreign key on ``note_id``.
    """
    note = note_von(leistung, schueler)
    if note is None:
        return

    _protokolliere(
        session,
        note,
        HistorieAktion.GELOESCHT,
        note.notenwert,
        note.status,
        None,
        None,
    )
    session.delete(note)
    session.flush()


# ---------------------------------------------------------------------------
# Leistungen. Neither 5.4 nor 5.5 says where these are managed; they belong
# next to the grade entry, because that is the actual sequence of work.
# ---------------------------------------------------------------------------


def lege_leistung_an(
    session: Session,
    notengruppe: Notengruppe,
    bezeichnung: str,
    datum: date,
    gewicht: Decimal,
) -> Leistung:
    if gewicht <= 0:
        raise Verwaltungsfehler("Das Gewicht einer Leistung muss größer als 0 sein.")
    if not bezeichnung.strip():
        raise Verwaltungsfehler("Die Leistung braucht eine Bezeichnung.")
    leistung = Leistung(
        notengruppe=notengruppe,
        bezeichnung=bezeichnung.strip(),
        datum=datum,
        gewicht=gewicht,
    )
    session.add(leistung)
    session.flush()
    return leistung


def aendere_leistung(
    session: Session,
    leistung: Leistung,
    bezeichnung: str,
    datum: date,
    gewicht: Decimal,
) -> Leistung:
    if gewicht <= 0:
        raise Verwaltungsfehler("Das Gewicht einer Leistung muss größer als 0 sein.")
    if not bezeichnung.strip():
        raise Verwaltungsfehler("Die Leistung braucht eine Bezeichnung.")
    leistung.bezeichnung = bezeichnung.strip()
    leistung.datum = datum
    leistung.gewicht = gewicht
    session.flush()
    return leistung


def loesche_leistung(session: Session, leistung: Leistung) -> None:
    """Only while no grade hangs on it -- as everywhere in this application."""
    if leistung.noten:
        raise Verwaltungsfehler(
            "Die Leistung lässt sich nicht löschen, solange Noten daran hängen. "
            "Entfernen Sie die Noten zuerst über die Eingabemaske."
        )
    session.delete(leistung)
    session.flush()
