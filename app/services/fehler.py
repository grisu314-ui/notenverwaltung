"""Turn database constraint violations into readable German sentences.

SQLite reports these three ways, verified against the running database:

    UNIQUE constraint failed: klasse.schuljahr_id, klasse.bezeichnung
    CHECK constraint failed: ck_halbjahr_nummer_gueltig
    NOT NULL constraint failed: klasse.bezeichnung
    FOREIGN KEY constraint failed

So a UNIQUE violation is identified by its column list and a CHECK violation
by its constraint name -- the deterministic names from the naming convention
pay off for the second kind only. A foreign key violation carries no detail
at all.

An unknown constraint yields a general message **and** a log entry, so the gap
shows up instead of staying silent.
"""

import logging
from contextlib import contextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class Verwaltungsfehler(ValueError):
    """An input the application refuses, with a message meant for the user."""


ART_UNIQUE = "unique"
ART_CHECK = "check"
ART_NOT_NULL = "not_null"
ART_FREMDSCHLUESSEL = "fremdschluessel"

_PRAEFIXE = (
    ("UNIQUE constraint failed: ", ART_UNIQUE),
    ("CHECK constraint failed: ", ART_CHECK),
    ("NOT NULL constraint failed: ", ART_NOT_NULL),
    ("FOREIGN KEY constraint failed", ART_FREMDSCHLUESSEL),
)

MELDUNGEN: dict[tuple[str, str], str] = {
    (ART_UNIQUE, "schuljahr.bezeichnung"): (
        "Ein Schuljahr mit dieser Bezeichnung gibt es bereits."
    ),
    (ART_UNIQUE, "halbjahr.schuljahr_id, halbjahr.nummer"): (
        "Dieses Halbjahr ist für das Schuljahr bereits angelegt."
    ),
    (ART_UNIQUE, "klasse.schuljahr_id, klasse.bezeichnung"): (
        "Diese Klassenbezeichnung gibt es in diesem Schuljahr bereits."
    ),
    (ART_UNIQUE, "kurs.klasse_id, kurs.fach"): (
        "Dieses Fach ist in dieser Klasse bereits als Kurs angelegt."
    ),
    (
        ART_UNIQUE,
        "notengruppe.kurs_id, notengruppe.halbjahr_id, notengruppe.bezeichnung",
    ): "Diese Notengruppe gibt es in diesem Kurs und Halbjahr bereits.",
    (ART_UNIQUE, "note.leistung_id, note.schueler_id"): (
        "Für diesen Schüler ist zu dieser Leistung bereits eine Note eingetragen."
    ),
    (ART_UNIQUE, "kursteilnahme.kurs_id, kursteilnahme.schueler_id"): (
        "Dieser Schüler nimmt an diesem Kurs bereits teil."
    ),
    (ART_CHECK, "ck_schuljahr_ende_nach_beginn"): (
        "Das Ende des Schuljahres muss nach dem Beginn liegen."
    ),
    (ART_CHECK, "ck_halbjahr_ende_nach_beginn"): (
        "Das Ende des Halbjahres muss nach dem Beginn liegen."
    ),
    (ART_CHECK, "ck_halbjahr_nummer_gueltig"): "Ein Halbjahr hat die Nummer 1 oder 2.",
    (ART_CHECK, "ck_note_status_gueltig"): (
        "Der Status einer Note muss gewertet, nicht gewertet oder nicht erbracht sein."
    ),
    (ART_CHECK, "ck_note_notenwert_bei_gewertet"): (
        "Eine gewertete Note braucht einen Notenwert."
    ),
    (ART_CHECK, "ck_notenueberschreibung_bezugszeitraum_gueltig"): (
        "Eine Festsetzung gilt für Halbjahr 1, Halbjahr 2 oder das Jahr."
    ),
    (ART_CHECK, "ck_notenueberschreibung_quelle_gueltig"): (
        "Unbekannte Herkunft der Festsetzung."
    ),
    (ART_CHECK, "ck_note_historie_aktion_gueltig"): (
        "Unbekannte Aktion in der Änderungshistorie."
    ),
    (ART_CHECK, "ck_note_historie_alter_status_gueltig"): (
        "Unbekannter Status in der Änderungshistorie."
    ),
    (ART_CHECK, "ck_note_historie_neuer_status_gueltig"): (
        "Unbekannter Status in der Änderungshistorie."
    ),
    (ART_UNIQUE, "sitzplan.klasse_id"): (
        "Für diese Klasse gibt es bereits einen Sitzplan."
    ),
    (ART_UNIQUE, "sitzplatz.sitzplan_id, sitzplatz.reihe, sitzplatz.position"): (
        "Auf diesem Platz sitzt bereits ein Schüler."
    ),
    (ART_UNIQUE, "sitzplatz.sitzplan_id, sitzplatz.schueler_id"): (
        "Dieser Schüler sitzt im Sitzplan bereits auf einem anderen Platz."
    ),
    (ART_CHECK, "ck_sitzplan_reihen_gueltig"): (
        "Ein Sitzplan hat 1 bis 12 Reihen."
    ),
    (ART_CHECK, "ck_sitzplan_sitze_je_reihe_gueltig"): (
        "Eine Reihe hat 1 bis 12 Sitze."
    ),
    (ART_CHECK, "ck_sitzplatz_reihe_gueltig"): (
        "Die Reihe eines Sitzplatzes beginnt bei 1."
    ),
    (ART_CHECK, "ck_sitzplatz_position_gueltig"): (
        "Die Position eines Sitzplatzes beginnt bei 1."
    ),
}

ALLGEMEINE_MELDUNG = (
    "Die Eingabe verletzt eine Regel der Datenbank und wurde nicht gespeichert. "
    "Der genaue Grund steht im Anwendungsprotokoll."
)
MELDUNG_FREMDSCHLUESSEL = (
    "Der Eintrag verweist auf einen Datensatz, den es nicht mehr gibt."
)


def _zerlege(fehlertext: str) -> tuple[str, str] | None:
    for praefix, art in _PRAEFIXE:
        if praefix in fehlertext:
            _, _, rest = fehlertext.partition(praefix)
            return art, rest.strip()
    return None


def meldung_zu(fehler: IntegrityError) -> str:
    """German sentence for a constraint violation."""
    fehlertext = str(getattr(fehler, "orig", fehler))
    zerlegt = _zerlege(fehlertext)
    if zerlegt is None:
        logger.warning("Unbekannte Integritätsverletzung: %s", fehlertext)
        return ALLGEMEINE_MELDUNG

    art, schluessel = zerlegt
    if art == ART_FREMDSCHLUESSEL:
        return MELDUNG_FREMDSCHLUESSEL
    if art == ART_NOT_NULL:
        _, _, spalte = schluessel.rpartition(".")
        return f"Das Feld „{spalte}“ darf nicht leer sein."

    meldung = MELDUNGEN.get((art, schluessel))
    if meldung is None:
        logger.warning(
            "Für die Regel %s '%s' ist keine deutsche Meldung hinterlegt.",
            art,
            schluessel,
        )
        return ALLGEMEINE_MELDUNG
    return meldung


@contextmanager
def uebersetzte_datenbankfehler(session: Session):
    """Roll back and re-raise a constraint violation as a readable message."""
    try:
        yield
    except IntegrityError as fehler:
        session.rollback()
        logger.info("Eingabe abgewiesen: %s", getattr(fehler, "orig", fehler))
        raise Verwaltungsfehler(meldung_zu(fehler)) from fehler
