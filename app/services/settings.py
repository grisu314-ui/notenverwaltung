"""Access to the persisted settings (specification 5.1, 6).

There is one operator and no user table, so a single key/value row per
setting is enough. Defaults live here in the code; a row exists only where
the default was changed.
"""

import logging
from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from app.db.models import Einstellung
from app.enums import Namensanzeige, Sortierung

logger = logging.getLogger(__name__)

SCHLUESSEL_SORTIERUNG = "sortierung"
SCHLUESSEL_NAMENSANZEIGE = "namensanzeige"


@dataclass(frozen=True)
class Einstellungen:
    sortierung: Sortierung = Sortierung.NACHNAME
    namensanzeige: Namensanzeige = Namensanzeige.NACHNAME_VORNAME


VORGABE = Einstellungen()


def _gelesen(rohwerte: dict[str, str], schluessel: str, typ, vorgabe):
    """Convert a stored value, falling back to the default on anything odd.

    A stored value that no longer matches the vocabulary must not take the
    application down, but it must not pass unnoticed either.
    """
    roh = rohwerte.get(schluessel)
    if roh is None:
        return vorgabe
    try:
        return typ(roh)
    except ValueError:
        logger.warning(
            "Einstellung '%s' hat den unbekannten Wert '%s'; es gilt die Vorgabe '%s'.",
            schluessel,
            roh,
            vorgabe,
        )
        return vorgabe


def lies_einstellungen(session: Session) -> Einstellungen:
    rohwerte = {
        eintrag.schluessel: eintrag.wert for eintrag in session.query(Einstellung).all()
    }
    return Einstellungen(
        sortierung=_gelesen(
            rohwerte, SCHLUESSEL_SORTIERUNG, Sortierung, VORGABE.sortierung
        ),
        namensanzeige=_gelesen(
            rohwerte, SCHLUESSEL_NAMENSANZEIGE, Namensanzeige, VORGABE.namensanzeige
        ),
    )


def schreibe_einstellungen(session: Session, einstellungen: Einstellungen) -> None:
    """Store the settings, one row per setting, added or updated as needed."""
    for schluessel, wert in (
        (SCHLUESSEL_SORTIERUNG, einstellungen.sortierung),
        (SCHLUESSEL_NAMENSANZEIGE, einstellungen.namensanzeige),
    ):
        eintrag = session.get(Einstellung, schluessel)
        if eintrag is None:
            session.add(Einstellung(schluessel=schluessel, wert=str(wert)))
        else:
            eintrag.wert = str(wert)


def setze_sortierung(session: Session, sortierung: Sortierung) -> Einstellungen:
    neu = replace(lies_einstellungen(session), sortierung=sortierung)
    schreibe_einstellungen(session, neu)
    return neu


def setze_namensanzeige(session: Session, anzeige: Namensanzeige) -> Einstellungen:
    neu = replace(lies_einstellungen(session), namensanzeige=anzeige)
    schreibe_einstellungen(session, neu)
    return neu
