"""Deleting a pupil or a school year for good (specification 11).

The rows themselves go through the cascades that have been in the schema
since the beginning. The work here is everything around that:

* counting beforehand what will disappear, so the confirmation page can name
  it instead of asking for a blind yes;
* making the deletion actually reach the file.

**The second point is not obvious.** SQLite does not hand freed pages back to
the file system, so after a DELETE the bytes of a deleted photograph are
still in the file, merely unlinked. ``VACUUM`` rewrites the file without
them -- but in WAL mode that is *still* not enough: the old content stays in
the -wal file until a checkpoint folds it in. Measured, not assumed; see
``tests/test_loeschen.py``, which searches the raw files for a marker.

What this cannot do is reach into the backups. Deleting here removes nothing
from last night's snapshot, and the confirmation page says so.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import (
    Klasse,
    Kurs,
    Kursteilnahme,
    Leistung,
    Note,
    NoteHistorie,
    Notengruppe,
    Notenueberschreibung,
    Schueler,
    Schuljahr,
    Sitzplatz,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Umfang:
    """What a deletion will remove, in the words the user reads."""

    posten: tuple[tuple[str, int], ...]

    @property
    def gesamt(self) -> int:
        return sum(anzahl for _, anzahl in self.posten)

    def als_protokoll(self) -> str:
        """Counts only -- a log entry must not preserve the names."""
        return ", ".join(f"{name}: {anzahl}" for name, anzahl in self.posten)


def _anzahl(session: Session, modell, bedingung) -> int:
    return session.execute(
        select(func.count()).select_from(modell).where(bedingung)
    ).scalar_one()


def umfang_schueler(session: Session, schueler: Schueler) -> Umfang:
    return Umfang(
        posten=(
            ("Schülerdatensatz", 1),
            ("Foto", 1 if schueler.foto_geaendert_am is not None else 0),
            ("Noten", _anzahl(session, Note, Note.schueler_id == schueler.id)),
            (
                "Einträge der Änderungshistorie",
                _anzahl(session, NoteHistorie, NoteHistorie.schueler_id == schueler.id),
            ),
            (
                "Kursteilnahmen",
                _anzahl(
                    session, Kursteilnahme, Kursteilnahme.schueler_id == schueler.id
                ),
            ),
            (
                "festgesetzte Noten",
                _anzahl(
                    session,
                    Notenueberschreibung,
                    Notenueberschreibung.schueler_id == schueler.id,
                ),
            ),
            (
                "Sitzplatzzuweisungen",
                _anzahl(session, Sitzplatz, Sitzplatz.schueler_id == schueler.id),
            ),
        )
    )


def umfang_schuljahr(session: Session, schuljahr: Schuljahr) -> Umfang:
    klassen = list(schuljahr.klassen)
    schueler = [s for klasse in klassen for s in klasse.schueler]
    kurse = [kurs for klasse in klassen for kurs in klasse.kurse]
    notengruppen = [gruppe for kurs in kurse for gruppe in kurs.notengruppen]
    leistungen = [le for gruppe in notengruppen for le in gruppe.leistungen]

    sitzplaene = [klasse.sitzplan for klasse in klassen if klasse.sitzplan is not None]

    schueler_ids = [s.id for s in schueler]
    kurs_ids = [k.id for k in kurse]
    leistung_ids = [le.id for le in leistungen]
    sitzplan_ids = [plan.id for plan in sitzplaene]

    def zaehle(modell, spalte, werte) -> int:
        return _anzahl(session, modell, spalte.in_(werte)) if werte else 0

    return Umfang(
        posten=(
            ("Schuljahr mit beiden Halbjahren", 1),
            ("Klassen", len(klassen)),
            ("Schüler", len(schueler)),
            ("Fotos", sum(1 for s in schueler if s.foto_geaendert_am is not None)),
            ("Kurse", len(kurse)),
            ("Notengruppen", len(notengruppen)),
            ("Leistungen", len(leistungen)),
            ("Noten", zaehle(Note, Note.leistung_id, leistung_ids)),
            (
                "Einträge der Änderungshistorie",
                zaehle(NoteHistorie, NoteHistorie.schueler_id, schueler_ids),
            ),
            ("Kursteilnahmen", zaehle(Kursteilnahme, Kursteilnahme.kurs_id, kurs_ids)),
            (
                "festgesetzte Noten",
                zaehle(Notenueberschreibung, Notenueberschreibung.kurs_id, kurs_ids),
            ),
            ("Sitzpläne", len(sitzplaene)),
            (
                "Sitzplatzzuweisungen",
                zaehle(Sitzplatz, Sitzplatz.sitzplan_id, sitzplan_ids),
            ),
        )
    )


def verdichte(engine: Engine) -> None:
    """Rewrite the file without the freed pages, then fold in the WAL.

    Both steps are needed. VACUUM alone leaves the old content in the -wal
    file, where it stays readable until a checkpoint.
    """
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as verbindung:
        verbindung.exec_driver_sql("VACUUM")
        verbindung.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")


def loesche_schueler(session: Session, schueler: Schueler) -> Umfang:
    """Remove a pupil with grades, photo and history (11). Caller commits."""
    umfang = umfang_schueler(session, schueler)
    kennung = schueler.id
    session.delete(schueler)
    session.flush()
    # Identifier and counts only: a log line naming the pupil would keep
    # exactly the data this function exists to remove.
    logger.warning("Schüler %s endgültig gelöscht — %s", kennung, umfang.als_protokoll())
    return umfang


def loesche_schuljahr(session: Session, schuljahr: Schuljahr) -> Umfang:
    """Remove a school year with everything below it (11). Caller commits."""
    umfang = umfang_schuljahr(session, schuljahr)
    kennung = schuljahr.id
    session.delete(schuljahr)
    session.flush()
    logger.warning(
        "Schuljahr %s endgültig gelöscht — %s", kennung, umfang.als_protokoll()
    )
    return umfang
