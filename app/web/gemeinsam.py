"""Shared pieces of the web layer: templates, confirmations, small helpers."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.services.sorting import anzeigename, namensschluessel, vereinfacht

VERZEICHNIS = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=VERZEICHNIS / "templates")
templates.env.filters["anzeigename"] = anzeigename

# Confirmations travel as a key in the URL, never as free text: without
# sessions there is no flash message, and echoing text from a query string
# back into a page is not something this application will do.
BESTAETIGUNGEN = {
    "angelegt": "Angelegt.",
    "gespeichert": "Gespeichert.",
    "geloescht": "Gelöscht.",
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
