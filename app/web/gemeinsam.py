"""Shared pieces of the web layer: templates, confirmations, small helpers."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.grading.notenwert import als_anzeige, als_dezimalanzeige
from app.services.sorting import anzeigename, namensschluessel, vereinfacht

VERZEICHNIS = Path(__file__).resolve().parent


def _statikversion() -> str:
    """Cache-busting token, from the newest file under ``static/``.

    Without it a browser keeps the stylesheet it already has. Observed on a
    phone that had used the application for weeks: after the seating plan was
    deployed it rendered as a bare nested list, because a free seat is an
    empty element whose whole visible form comes from CSS that the browser
    never re-fetched.

    Computed once at import; the files do not change while the process runs.
    """
    dateien = (VERZEICHNIS / "static").glob("*")
    neueste = max((d.stat().st_mtime for d in dateien if d.is_file()), default=0.0)
    return str(int(neueste))


STATIKVERSION = _statikversion()

templates = Jinja2Templates(directory=VERZEICHNIS / "templates")
templates.env.globals["statikversion"] = STATIKVERSION
templates.env.filters["anzeigename"] = anzeigename
# 0.7 is shown as "1+", never as "0,7" (specification 4.1).
templates.env.filters["note_anzeige"] = als_anzeige
templates.env.filters["uhrzeit"] = lambda wert: uhrzeit(wert)
# Calculated values in German notation: "2,6".
templates.env.filters["dezimal"] = als_dezimalanzeige

ANZEIGEZONE = ZoneInfo("Europe/Berlin")


def uhrzeit(wert: datetime | None) -> str:
    """Stored timestamps are naive UTC; the user sees local time."""
    if wert is None:
        return ""
    return wert.replace(tzinfo=ZoneInfo("UTC")).astimezone(ANZEIGEZONE).strftime("%H:%M")


# Confirmations travel as a key in the URL, never as free text: without
# sessions there is no flash message, and echoing text from a query string
# back into a page is not something this application will do.
BESTAETIGUNGEN = {
    "angelegt": "Angelegt.",
    "gespeichert": "Gespeichert.",
    "geloescht": "Gelöscht.",
    # The rows are gone, only the compaction afterwards failed. Saying just
    # "Gelöscht." would hide that the bytes are still in the file.
    "geloescht_ohne_verdichten": (
        "Gelöscht — die Datenbank ließ sich danach aber nicht verdichten. "
        "Die Daten sind aus der Anwendung entfernt, ihre Bytes stehen noch in "
        "der Datei. Der Grund steht im Anwendungsprotokoll."
    ),
    "aktiviert": "Als aktives Schuljahr gesetzt.",
}


def bestaetigung(schluessel: str | None) -> str | None:
    return BESTAETIGUNGEN.get(schluessel) if schluessel else None


def hole(session: Session, modell, kennung: int):
    """Load a record or answer with a German 404 page."""
    datensatz = session.get(modell, kennung)
    if datensatz is None:
        raise HTTPException(status_code=404, detail="Der Datensatz wurde nicht gefunden.")
    return datensatz


def sortierte_schueler(schueler, sortierung):
    return sorted(
        schueler,
        key=lambda s: namensschluessel(s.vorname, s.nachname, sortierung),
    )


def sortiert_nach_bezeichnung(eintraege, feld: str = "bezeichnung"):
    return sorted(
        eintraege,
        key=lambda eintrag: (
            vereinfacht(getattr(eintrag, feld)),
            getattr(eintrag, feld),
        ),
    )
