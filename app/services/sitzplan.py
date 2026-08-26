"""The seating plan of a class (specification 5.6).

A view onto pupils. The one grade it touches is the participation grade of
the current day -- see :func:`mitarbeitsnote` at the end of this module.

Two rules of the section need code rather than a constraint, because SQLite
allows no subquery in a CHECK:

* a seat has to lie inside the grid of its plan;
* shrinking the grid is refused while an active pupil would fall off it.

A third rule looks like an omission and is not. A seat whose pupil went
inactive keeps its row, and the plan draws that seat as free -- deactivating
stays as reversible here as everywhere else in this application. The pupil
returns to the seat when they are reactivated, unless the seat was given
away in the meantime.
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import heute_lokal
from app.db.models import (
    BEZEICHNUNG_MITARBEIT,
    MAX_RASTER,
    MIN_RASTER,
    Halbjahr,
    Klasse,
    Kurs,
    Leistung,
    Note,
    Notengruppe,
    Schueler,
    Sitzplan,
    Sitzplatz,
)
from app.enums import NoteStatus
from app.services import noten as notendienst
from app.services.fehler import Verwaltungsfehler
from app.services.klasse import Zahlen
from app.services.klasse import zahlen as klassenzahlen
from app.services.settings import lies_einstellungen
from app.services.sorting import namensschluessel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Platz:
    """One seat of the grid, with the pupil sitting on it or None."""

    reihe: int
    position: int
    schueler: Schueler | None

    @property
    def ist_frei(self) -> bool:
        return self.schueler is None


@dataclass(frozen=True)
class Reihe:
    nummer: int
    plaetze: tuple[Platz, ...]


@dataclass(frozen=True)
class Blatt:
    """Everything one rendering of the plan needs."""

    klasse: Klasse
    sitzplan: Sitzplan
    reihen: tuple[Reihe, ...]
    ohne_platz: tuple[Schueler, ...]
    # The same two numbers the class view shows (5.1). Counted once, in
    # app/services/klasse.py, so the two views cannot drift apart.
    zahlen: Zahlen

    @property
    def anzahl_ohne_platz(self) -> int:
        return len(self.ohne_platz)

    @property
    def anzahl_besetzt(self) -> int:
        return sum(
            1 for reihe in self.reihen for platz in reihe.plaetze if not platz.ist_frei
        )


def hole_oder_lege_an(session: Session, klasse: Klasse) -> Sitzplan:
    """The plan of this class, created on first use.

    Not created together with the class: a class that is never seated needs
    no row, and the default grid would then be a claim nobody made.
    """
    if klasse.sitzplan is not None:
        return klasse.sitzplan
    sitzplan = Sitzplan(klasse=klasse)
    session.add(sitzplan)
    session.flush()
    return sitzplan


def _im_raster(sitzplan: Sitzplan, reihe: int, position: int) -> bool:
    return 1 <= reihe <= sitzplan.reihen and 1 <= position <= sitzplan.sitze_je_reihe


def _pruefe_im_raster(sitzplan: Sitzplan, reihe: int, position: int) -> None:
    if not _im_raster(sitzplan, reihe, position):
        raise Verwaltungsfehler(
            f"Reihe {reihe}, Platz {position} liegt außerhalb des Rasters "
            f"({sitzplan.reihen} Reihen zu je {sitzplan.sitze_je_reihe} Sitzen)."
        )


def _plaetze(session: Session, sitzplan: Sitzplan) -> list[Sitzplatz]:
    """The seats of a plan, queried rather than read off the relationship.

    ``sitzplan.plaetze`` still holds a row that was deleted and flushed in
    the same session, and a second pass over it would try to delete that row
    again. Querying gives the state the database is actually in.
    """
    return list(
        session.execute(
            select(Sitzplatz).where(Sitzplatz.sitzplan_id == sitzplan.id)
        ).scalars()
    )


def _belegung(session: Session, sitzplan: Sitzplan) -> dict[tuple[int, int], Sitzplatz]:
    return {(platz.reihe, platz.position): platz for platz in _plaetze(session, sitzplan)}


def _platz_von(
    session: Session, sitzplan: Sitzplan, schueler: Schueler
) -> Sitzplatz | None:
    for platz in _plaetze(session, sitzplan):
        if platz.schueler_id == schueler.id:
            return platz
    return None


def blatt(session: Session, klasse: Klasse) -> Blatt:
    """Build the grid and the list of pupils who have no seat in it.

    A pupil whose seat lies outside the grid -- possible after the grid was
    made smaller -- counts as unseated. Otherwise they would appear neither
    on the plan nor in the list, and that is the one state in which someone
    can be overlooked.
    """
    sitzplan = hole_oder_lege_an(session, klasse)
    einstellungen = lies_einstellungen(session)
    belegung = _belegung(session, sitzplan)

    reihen = tuple(
        Reihe(
            nummer=reihe,
            plaetze=tuple(
                Platz(
                    reihe=reihe,
                    position=position,
                    schueler=_sichtbarer_schueler(belegung.get((reihe, position))),
                )
                for position in range(1, sitzplan.sitze_je_reihe + 1)
            ),
        )
        for reihe in range(1, sitzplan.reihen + 1)
    )

    gesetzt = {
        platz.schueler.id
        for reihe in reihen
        for platz in reihe.plaetze
        if platz.schueler is not None
    }
    ohne_platz = sorted(
        (s for s in klasse.schueler if s.ist_aktiv and s.id not in gesetzt),
        key=lambda s: namensschluessel(s.vorname, s.nachname, einstellungen.sortierung),
    )

    return Blatt(
        klasse=klasse,
        sitzplan=sitzplan,
        reihen=reihen,
        ohne_platz=tuple(ohne_platz),
        zahlen=klassenzahlen(session, klasse),
    )


def _sichtbarer_schueler(platz: Sitzplatz | None) -> Schueler | None:
    """An inactive pupil keeps the row but leaves the seat looking free (5.6)."""
    if platz is None or not platz.schueler.ist_aktiv:
        return None
    return platz.schueler


def schueler_auf_platz(
    session: Session, sitzplan: Sitzplan, reihe: int, position: int
) -> Schueler | None:
    """Who is sitting there now -- active pupils only, as the plan draws it.

    The caller of a seat action reads the pupil from here rather than from
    the form, so what is stored is who sits there now, not who sat there when
    the page was rendered.
    """
    platz = _belegung(session, sitzplan).get((reihe, position))
    return _sichtbarer_schueler(platz)


def setze_platz(
    session: Session, sitzplan: Sitzplan, reihe: int, position: int, schueler: Schueler
) -> Sitzplatz:
    """Seat a pupil, replacing whatever reservation was on that seat.

    Refused when an **active** pupil sits there: the interface offers a
    chooser only for free seats, so this is a page that no longer matches the
    database, and quietly moving someone out of their seat is the wrong
    answer to that.
    """
    _pruefe_im_raster(sitzplan, reihe, position)
    if schueler.klasse_id != sitzplan.klasse_id:
        raise Verwaltungsfehler(
            "Der Schüler gehört nicht zu der Klasse, zu der dieser Sitzplan gehört."
        )
    if not schueler.ist_aktiv:
        raise Verwaltungsfehler(
            "Ein inaktiver Schüler bekommt keinen Platz. Erst wieder aktiv setzen."
        )

    vorhanden = _belegung(session, sitzplan).get((reihe, position))
    if vorhanden is not None:
        if vorhanden.schueler_id == schueler.id:
            return vorhanden
        if vorhanden.schueler.ist_aktiv:
            raise Verwaltungsfehler(
                f"Auf diesem Platz sitzt bereits {vorhanden.schueler.vorname} "
                f"{vorhanden.schueler.nachname}. Bitte die Seite neu laden."
            )
        # Only the reservation of a pupil who left the class -- the seat is
        # shown as free, so taking it is what the display promised.
        session.delete(vorhanden)

    bisheriger = _platz_von(session, sitzplan, schueler)
    if bisheriger is not None:
        session.delete(bisheriger)
    session.flush()

    platz = Sitzplatz(
        sitzplan=sitzplan, schueler=schueler, reihe=reihe, position=position
    )
    session.add(platz)
    session.flush()
    return platz


def raeume_platz(
    session: Session, sitzplan: Sitzplan, reihe: int, position: int
) -> bool:
    """Free a seat. Returns whether there was anything to free."""
    vorhanden = _belegung(session, sitzplan).get((reihe, position))
    if vorhanden is None:
        return False
    session.delete(vorhanden)
    session.flush()
    return True


def tausche(
    session: Session,
    sitzplan: Sitzplan,
    von: tuple[int, int],
    nach: tuple[int, int],
) -> None:
    """Swap two seats, or move a pupil when the second one is free.

    Both rows are removed before the new ones are written: the unique
    constraint on (plan, row, position) would otherwise reject the first of
    two updates, and SQLite has no deferred constraints to get around that.
    """
    _pruefe_im_raster(sitzplan, *von)
    _pruefe_im_raster(sitzplan, *nach)
    if von == nach:
        return

    belegung = _belegung(session, sitzplan)
    quelle = belegung.get(von)
    ziel = belegung.get(nach)
    if quelle is None and ziel is None:
        raise Verwaltungsfehler("Beide Plätze sind frei; es gibt nichts zu tauschen.")

    schueler_quelle = quelle.schueler if quelle is not None else None
    schueler_ziel = ziel.schueler if ziel is not None else None
    for platz in (quelle, ziel):
        if platz is not None:
            session.delete(platz)
    session.flush()

    if schueler_quelle is not None:
        session.add(
            Sitzplatz(
                sitzplan=sitzplan,
                schueler=schueler_quelle,
                reihe=nach[0],
                position=nach[1],
            )
        )
    if schueler_ziel is not None:
        session.add(
            Sitzplatz(
                sitzplan=sitzplan,
                schueler=schueler_ziel,
                reihe=von[0],
                position=von[1],
            )
        )
    session.flush()


def setze_raster(
    session: Session, sitzplan: Sitzplan, reihen: int, sitze_je_reihe: int
) -> Sitzplan:
    """Change the grid; refuse a shrink that would drop an occupied seat.

    Only seats of **active** pupils block it. A row left behind by someone
    who has left the class holds a seat nobody can see; naming that person in
    a refusal would explain nothing. Their row stays where it is, and if they
    are ever reactivated they show up among the pupils without a seat.
    """
    for wert, was in ((reihen, "Die Reihenzahl"), (sitze_je_reihe, "Die Sitzzahl")):
        if not MIN_RASTER <= wert <= MAX_RASTER:
            raise Verwaltungsfehler(
                f"{was} muss zwischen {MIN_RASTER} und {MAX_RASTER} liegen."
            )

    betroffen = [
        platz
        for platz in _plaetze(session, sitzplan)
        if platz.schueler.ist_aktiv
        and (platz.reihe > reihen or platz.position > sitze_je_reihe)
    ]
    if betroffen:
        namen = ", ".join(
            f"{platz.schueler.vorname} {platz.schueler.nachname} "
            f"(Reihe {platz.reihe}, Platz {platz.position})"
            for platz in sorted(betroffen, key=lambda p: (p.reihe, p.position))
        )
        raise Verwaltungsfehler(
            "Das Raster lässt sich nicht verkleinern, solange dort jemand sitzt: "
            f"{namen}. Erst die Plätze räumen."
        )

    sitzplan.reihen = reihen
    sitzplan.sitze_je_reihe = sitze_je_reihe
    session.flush()
    return sitzplan


# ---------------------------------------------------------------------------
# The participation grade of the day (5.6)
#
# The only place the seating plan writes a grade. It is meant for the moment
# in a lesson when something stands out -- in either direction -- so the
# normal case is that on a given day nobody or only one or two pupils get one.
#
# Everything below builds on the ordinary grade entry: same Note row, same
# history, same rules. There is no second way of calculating anything.
# ---------------------------------------------------------------------------


def halbjahr_zum_datum(kurs: Kurs, datum: date) -> Halbjahr | None:
    """The term of the course's school year that contains this date."""
    for halbjahr in kurs.klasse.schuljahr.halbjahre:
        if halbjahr.beginn <= datum <= halbjahr.ende:
            return halbjahr
    return None


def _mitarbeitsgruppe(
    session: Session, kurs: Kurs, halbjahr: Halbjahr
) -> Notengruppe | None:
    """The group named "Mitarbeit" of this course and term.

    Found by name, not by a flag on the row. New courses get the group as a
    default (3.1); rename it and this stops finding it -- which is why the
    caller refuses loudly instead of creating a group whose weight would move
    a report grade.
    """
    gruppen = session.execute(
        select(Notengruppe).where(
            Notengruppe.kurs_id == kurs.id, Notengruppe.halbjahr_id == halbjahr.id
        )
    ).scalars()
    for gruppe in gruppen:
        if gruppe.bezeichnung.strip().casefold() == BEZEICHNUNG_MITARBEIT.casefold():
            return gruppe
    return None


def bezeichnung_der_tagesleistung(datum: date) -> str:
    return f"{BEZEICHNUNG_MITARBEIT} {datum.strftime('%d.%m.%Y')}"


def _tagesleistung(
    session: Session, gruppe: Notengruppe, datum: date
) -> Leistung | None:
    bezeichnung = bezeichnung_der_tagesleistung(datum)
    for leistung in gruppe.leistungen:
        if leistung.datum == datum and leistung.bezeichnung == bezeichnung:
            return leistung
    return None


def mitarbeitsnote(
    session: Session,
    kurs: Kurs,
    schueler: Schueler,
    notenwert: Decimal,
    notiz: str | None = None,
    datum: date | None = None,
) -> Note:
    """Award one participation grade for today. Caller commits.

    Always ``gewertet``: there is no performance somebody failed to deliver,
    so the other two statuses have no meaning here. A grade given by mistake
    is deleted, not reclassified.

    The assessment for the day is created on the first grade of that day, not
    in advance. A pupil who gets nothing has no row -- that is not a missing
    value, it is no performance, and it changes no calculation (4.4).
    """
    datum = datum or heute_lokal()
    if kurs.klasse_id != schueler.klasse_id:
        raise Verwaltungsfehler(
            "Der Kurs gehört nicht zu der Klasse, in der dieser Schüler ist."
        )

    halbjahr = halbjahr_zum_datum(kurs, datum)
    if halbjahr is None:
        raise Verwaltungsfehler(
            f"Der {datum.strftime('%d.%m.%Y')} liegt in keinem Halbjahr des "
            f"Schuljahres {kurs.klasse.schuljahr.bezeichnung}. In den Ferien lässt "
            "sich keine Mitarbeitsnote eintragen."
        )

    gruppe = _mitarbeitsgruppe(session, kurs, halbjahr)
    if gruppe is None:
        raise Verwaltungsfehler(
            f"Der Kurs {kurs.fach} hat im {halbjahr.nummer}. Halbjahr keine "
            f"Notengruppe „{BEZEICHNUNG_MITARBEIT}“. Bitte in der Verwaltung "
            "anlegen — die Anwendung legt sie nicht selbst an, weil ihr Gewicht "
            "die Note verändert."
        )

    leistung = _tagesleistung(session, gruppe, datum)
    if leistung is None:
        leistung = notendienst.lege_leistung_an(
            session,
            gruppe,
            bezeichnung_der_tagesleistung(datum),
            datum,
            Decimal("1.0"),
        )

    note = notendienst.setze_note(
        session, leistung, schueler, NoteStatus.GEWERTET, notenwert
    )
    # Set after the grade: setze_note returns early when value and status did
    # not change, and a note that only got a new remark still has to be saved.
    note.notiz = (notiz or "").strip() or None
    session.flush()
    logger.info(
        "Mitarbeitsnote für Schüler %s in Kurs %s am %s", schueler.id, kurs.id, datum
    )
    return note
