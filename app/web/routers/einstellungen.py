"""Switching sort order and name display (specification 5.1, 6).

Both settings are persisted, so the choice survives a reload and applies on
every device.
"""

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.enums import Namensanzeige, Sortierung
from app.services.fehler import Verwaltungsfehler, uebersetzte_datenbankfehler
from app.services.settings import setze_namensanzeige, setze_sortierung
from app.web.dependencies import datenbanksitzung

router = APIRouter(prefix="/einstellungen", tags=["einstellungen"])
WEITERLEITUNG = 303


def sicheres_ziel(ziel: str) -> str:
    """Only ever redirect within this application.

    The target comes from a form field. Without this check it could point at
    another host, which would turn a harmless toggle into an open redirect.
    """
    if ziel.startswith("/") and not ziel.startswith("//"):
        return ziel
    return "/"


def _gewaehlt(typ, wert: str, was: str):
    try:
        return typ(wert)
    except ValueError:
        raise Verwaltungsfehler(f"Unbekannte {was}: „{wert}“.") from None


@router.post("/sortierung")
def sortierung(
    sortierung: str = Form(...),
    ziel: str = Form("/"),
    session: Session = Depends(datenbanksitzung),
):
    with uebersetzte_datenbankfehler(session):
        setze_sortierung(session, _gewaehlt(Sortierung, sortierung, "Sortierung"))
        session.commit()
    return RedirectResponse(sicheres_ziel(ziel), WEITERLEITUNG)


@router.post("/namensanzeige")
def namensanzeige(
    namensanzeige: str = Form(...),
    ziel: str = Form("/"),
    session: Session = Depends(datenbanksitzung),
):
    with uebersetzte_datenbankfehler(session):
        setze_namensanzeige(
            session, _gewaehlt(Namensanzeige, namensanzeige, "Namensanzeige")
        )
        session.commit()
    return RedirectResponse(sicheres_ziel(ziel), WEITERLEITUNG)
