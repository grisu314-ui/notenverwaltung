"""Rules the database cannot enforce (specification 5.5, 3.1).

Every function here refuses bad input with a German message rather than
letting it reach the database, where the error would be less specific or --
worse -- would not appear at all.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import (
    VORGABE_NOTENGRUPPEN,
    Halbjahr,
    Klasse,
    Kurs,
    Kursteilnahme,
    Notengruppe,
    Schueler,
    Schuljahr,
)
from app.services.fehler import Verwaltungsfehler


def _pruefe_zeitraum(beginn: date, ende: date, was: str) -> None:
    if ende <= beginn:
        raise Verwaltungsfehler(f"Das Ende {was} muss nach dem Beginn liegen.")


def _pruefe_gewicht(gewicht: Decimal, was: str) -> None:
    if gewicht <= 0:
        raise Verwaltungsfehler(f"{was} muss größer als 0 sein.")


def halbjahresgrenzen(beginn: date, ende: date) -> tuple[date, date]:
    """Proposed end of the first and start of the second term.

    Split at 31 January of the year the school year ends in. If that date does
    not fall inside the school year -- an unusual range -- the midpoint is
    used, so the created terms can never violate the "end after start" rule.
    """
    wechsel = date(ende.year, 1, 31)
    if not beginn < wechsel < ende:
        wechsel = beginn + (ende - beginn) / 2
    return wechsel, wechsel + timedelta(days=1)


def lege_schuljahr_an(
    session: Session,
    bezeichnung: str,
    beginn: date,
    ende: date,
    ist_aktiv: bool = False,
) -> Schuljahr:
    """Create a school year together with both of its terms.

    Both terms are created here on purpose: a school year with only one term
    makes the year grade uncomputable, and nothing in the interface would
    show why.
    """
    _pruefe_zeitraum(beginn, ende, "des Schuljahres")
    ende_hj1, beginn_hj2 = halbjahresgrenzen(beginn, ende)

    schuljahr = Schuljahr(
        bezeichnung=bezeichnung.strip(), beginn=beginn, ende=ende, ist_aktiv=False
    )
    Halbjahr(schuljahr=schuljahr, nummer=1, beginn=beginn, ende=ende_hj1)
    Halbjahr(schuljahr=schuljahr, nummer=2, beginn=beginn_hj2, ende=ende)
    session.add(schuljahr)
    session.flush()

    if ist_aktiv:
        setze_aktives_schuljahr(session, schuljahr)
    return schuljahr


def setze_aktives_schuljahr(session: Session, schuljahr: Schuljahr) -> None:
    """Exactly one school year is active; the start page depends on it."""
    for anderes in session.query(Schuljahr).filter(Schuljahr.ist_aktiv.is_(True)).all():
        anderes.ist_aktiv = False
    schuljahr.ist_aktiv = True
    session.flush()


def aendere_schuljahr(
    session: Session,
    schuljahr: Schuljahr,
    bezeichnung: str,
    beginn: date,
    ende: date,
) -> Schuljahr:
    _pruefe_zeitraum(beginn, ende, "des Schuljahres")
    schuljahr.bezeichnung = bezeichnung.strip()
    schuljahr.beginn = beginn
    schuljahr.ende = ende
    session.flush()
    return schuljahr


def aendere_halbjahr(
    session: Session, halbjahr: Halbjahr, beginn: date, ende: date
) -> Halbjahr:
    _pruefe_zeitraum(beginn, ende, "des Halbjahres")
    schuljahr = halbjahr.schuljahr
    if beginn < schuljahr.beginn or ende > schuljahr.ende:
        raise Verwaltungsfehler(
            "Ein Halbjahr muss innerhalb seines Schuljahres liegen "
            f"({schuljahr.beginn:%d.%m.%Y} bis {schuljahr.ende:%d.%m.%Y})."
        )
    halbjahr.beginn = beginn
    halbjahr.ende = ende
    session.flush()
    return halbjahr


def lege_klasse_an(
    session: Session, schuljahr: Schuljahr, bezeichnung: str, notiz: str | None = None
) -> Klasse:
    klasse = Klasse(
        schuljahr=schuljahr, bezeichnung=bezeichnung.strip(), notiz=notiz or None
    )
    session.add(klasse)
    session.flush()
    return klasse


def lege_schueler_an(
    session: Session,
    klasse: Klasse,
    vorname: str,
    nachname: str,
    listennummer: int | None = None,
    notiz: str | None = None,
) -> Schueler:
    if not vorname.strip() or not nachname.strip():
        raise Verwaltungsfehler("Vor- und Nachname dürfen nicht leer sein.")
    schueler = Schueler(
        klasse=klasse,
        vorname=vorname.strip(),
        nachname=nachname.strip(),
        listennummer=listennummer,
        notiz=notiz or None,
        ist_aktiv=True,
    )
    session.add(schueler)
    session.flush()
    # A pupil joining later takes part in the courses that already exist.
    for kurs in klasse.kurse:
        session.add(Kursteilnahme(kurs=kurs, schueler=schueler, ist_aktiv=True))
    session.flush()
    return schueler


def lege_kurs_an(
    session: Session,
    klasse: Klasse,
    fach: str,
    notiz: str | None = None,
    gewicht_halbjahr_1: Decimal | None = None,
    gewicht_halbjahr_2: Decimal | None = None,
) -> Kurs:
    """Create a course; all active pupils join it, with the default groups (3.1).

    The three default Notengruppen are created per term, so six rows. They are
    a starting point: name, weight and number are editable afterwards, and an
    empty one can be deleted. Existing courses are never given them
    retroactively -- that would reach into grades already calculated.
    """
    kurs = Kurs(klasse=klasse, fach=fach.strip(), notiz=notiz or None)
    if gewicht_halbjahr_1 is not None:
        _pruefe_gewicht(gewicht_halbjahr_1, "Das Gewicht von Halbjahr 1")
        kurs.gewicht_halbjahr_1 = gewicht_halbjahr_1
    if gewicht_halbjahr_2 is not None:
        _pruefe_gewicht(gewicht_halbjahr_2, "Das Gewicht von Halbjahr 2")
        kurs.gewicht_halbjahr_2 = gewicht_halbjahr_2
    session.add(kurs)
    session.flush()

    for schueler in klasse.schueler:
        if schueler.ist_aktiv:
            session.add(Kursteilnahme(kurs=kurs, schueler=schueler, ist_aktiv=True))

    for halbjahr in klasse.schuljahr.halbjahre:
        for bezeichnung, gewicht, reihenfolge in VORGABE_NOTENGRUPPEN:
            session.add(
                Notengruppe(
                    kurs=kurs,
                    halbjahr=halbjahr,
                    bezeichnung=bezeichnung,
                    gewicht=gewicht,
                    reihenfolge=reihenfolge,
                )
            )
    session.flush()
    return kurs


def aendere_kurs(
    session: Session,
    kurs: Kurs,
    fach: str,
    notiz: str | None,
    gewicht_halbjahr_1: Decimal,
    gewicht_halbjahr_2: Decimal,
) -> Kurs:
    _pruefe_gewicht(gewicht_halbjahr_1, "Das Gewicht von Halbjahr 1")
    _pruefe_gewicht(gewicht_halbjahr_2, "Das Gewicht von Halbjahr 2")
    kurs.fach = fach.strip()
    kurs.notiz = notiz or None
    kurs.gewicht_halbjahr_1 = gewicht_halbjahr_1
    kurs.gewicht_halbjahr_2 = gewicht_halbjahr_2
    session.flush()
    return kurs


def aendere_notengruppe(
    session: Session,
    notengruppe: Notengruppe,
    bezeichnung: str,
    gewicht: Decimal,
    reihenfolge: int,
) -> Notengruppe:
    _pruefe_gewicht(gewicht, "Das Gewicht einer Notengruppe")
    notengruppe.bezeichnung = bezeichnung.strip()
    notengruppe.gewicht = gewicht
    notengruppe.reihenfolge = reihenfolge
    session.flush()
    return notengruppe


def lege_notengruppe_an(
    session: Session,
    kurs: Kurs,
    halbjahr: Halbjahr,
    bezeichnung: str,
    gewicht: Decimal,
    reihenfolge: int = 0,
) -> Notengruppe:
    """Create a grade group; the term has to belong to the course's year.

    No foreign key can express that. A group hung on the wrong school year
    would quietly falsify the term grade.
    """
    _pruefe_gewicht(gewicht, "Das Gewicht einer Notengruppe")
    if halbjahr.schuljahr_id != kurs.klasse.schuljahr_id:
        raise Verwaltungsfehler(
            "Das Halbjahr gehört zu einem anderen Schuljahr als der Kurs."
        )
    notengruppe = Notengruppe(
        kurs=kurs,
        halbjahr=halbjahr,
        bezeichnung=bezeichnung.strip(),
        gewicht=gewicht,
        reihenfolge=reihenfolge,
    )
    session.add(notengruppe)
    session.flush()
    return notengruppe


def setze_teilnahme(
    session: Session, kurs: Kurs, schueler: Schueler, ist_aktiv: bool
) -> Kursteilnahme:
    if schueler.klasse_id != kurs.klasse_id:
        raise Verwaltungsfehler(
            "Der Schüler gehört nicht zu der Klasse, zu der dieser Kurs gehört."
        )
    teilnahme = session.get(Kursteilnahme, (kurs.id, schueler.id))
    if teilnahme is None:
        teilnahme = Kursteilnahme(kurs=kurs, schueler=schueler, ist_aktiv=ist_aktiv)
        session.add(teilnahme)
    else:
        teilnahme.ist_aktiv = ist_aktiv
    session.flush()
    return teilnahme


# ---------------------------------------------------------------------------
# Deletion: only what is empty. Pupils and school years are the exception --
# section 11 demands a complete removal for those, and it lives in
# app/services/loeschen.py behind its own confirmation page.
#
# The cascades in the schema are sharp. Deleting a grade group that holds
# assessments would take thirty grades with it behind a single button. The
# deliberate, confirmed deletion belongs in the delete function of section 11.
# ---------------------------------------------------------------------------


def _verweigere(was: str, inhalt: str) -> None:
    raise Verwaltungsfehler(
        f"{was} lässt sich nicht löschen, solange {inhalt} daran hängen. "
        "Zum endgültigen Entfernen samt Inhalt gibt es die Löschfunktion."
    )


def loesche_notengruppe(session: Session, notengruppe: Notengruppe) -> None:
    if notengruppe.leistungen:
        _verweigere("Die Notengruppe", "Leistungen")
    session.delete(notengruppe)
    session.flush()


def loesche_kurs(session: Session, kurs: Kurs) -> None:
    if kurs.notengruppen:
        _verweigere("Der Kurs", "Notengruppen")
    session.delete(kurs)
    session.flush()


def loesche_klasse(session: Session, klasse: Klasse) -> None:
    if klasse.schueler:
        _verweigere("Die Klasse", "Schüler")
    if klasse.kurse:
        _verweigere("Die Klasse", "Kurse")
    session.delete(klasse)
    session.flush()


