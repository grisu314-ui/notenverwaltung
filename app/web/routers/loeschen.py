"""The delete function of specification 11.

Two steps on purpose. The first page counts what will disappear and asks for
the name to be typed; only the second request removes anything. Deleting a
school year destroys a year of work, and a mistap on a phone must not be able
to do that.
"""

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Schueler, Schuljahr
from app.services import loeschen as loeschdienst
from app.services.fehler import Verwaltungsfehler, uebersetzte_datenbankfehler
from app.services.sorting import vereinfacht
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import hole, templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verwaltung/loeschen", tags=["loeschen"])
WEITERLEITUNG = 303


def _pruefe_bestaetigung(eingabe: str, erwartet: str) -> None:
    """Forgiving about spelling, strict about deliberateness.

    Compared in the same simplified form the sorting uses, so an umlaut typed
    without its dots still counts. The point is that the name was typed at
    all, not that it was typed perfectly on a phone keyboard.
    """
    if vereinfacht(eingabe) != vereinfacht(erwartet):
        raise Verwaltungsfehler(
            f"Zur Bestätigung muss „{erwartet}“ eingetippt werden. "
            "Es wurde nichts gelöscht."
        )


def _verdichte(session: Session) -> str:
    """Compact the file and report which confirmation the user should see.

    The deletion is already committed when this runs. If VACUUM cannot get
    its lock -- the backup script is the realistic case -- the rows are gone
    but their bytes are not, and that has to be said rather than reported as
    a plain success.

    Uses the session's engine, not the configured one: otherwise a test would
    compact the productive file.
    """
    try:
        loeschdienst.verdichte(session.get_bind())
    except SQLAlchemyError:
        logger.exception("Verdichten nach dem Löschen fehlgeschlagen")
        return "geloescht_ohne_verdichten"
    return "geloescht"


def _seite(request: Request, **kontext) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name="verwaltung/loeschen.html", context=kontext
    )


@router.get("/schueler/{schueler_id}", response_class=HTMLResponse)
def schueler_bestaetigen(
    request: Request, schueler_id: int, session: Session = Depends(datenbanksitzung)
):
    schueler = hole(session, Schueler, schueler_id)
    return _seite(
        request,
        titel=f"Schüler {schueler.vorname} {schueler.nachname} endgültig löschen?",
        erwartet=f"{schueler.vorname} {schueler.nachname}",
        umfang=loeschdienst.umfang_schueler(session, schueler),
        ziel=f"/verwaltung/loeschen/schueler/{schueler_id}",
        zurueck=f"/verwaltung/schueler/{schueler_id}",
    )


@router.post("/schueler/{schueler_id}")
def schueler_loeschen(
    schueler_id: int,
    bestaetigung: str = Form(""),
    session: Session = Depends(datenbanksitzung),
):
    schueler = hole(session, Schueler, schueler_id)
    klasse_id = schueler.klasse_id
    _pruefe_bestaetigung(bestaetigung, f"{schueler.vorname} {schueler.nachname}")

    with uebersetzte_datenbankfehler(session):
        loeschdienst.loesche_schueler(session, schueler)
        session.commit()
    meldung = _verdichte(session)
    return RedirectResponse(
        f"/verwaltung/klassen/{klasse_id}?meldung={meldung}", WEITERLEITUNG
    )


@router.get("/schuljahre/{schuljahr_id}", response_class=HTMLResponse)
def schuljahr_bestaetigen(
    request: Request, schuljahr_id: int, session: Session = Depends(datenbanksitzung)
):
    schuljahr = hole(session, Schuljahr, schuljahr_id)
    return _seite(
        request,
        titel=f"Schuljahr {schuljahr.bezeichnung} endgültig löschen?",
        erwartet=schuljahr.bezeichnung,
        umfang=loeschdienst.umfang_schuljahr(session, schuljahr),
        ziel=f"/verwaltung/loeschen/schuljahre/{schuljahr_id}",
        zurueck=f"/verwaltung/schuljahre/{schuljahr_id}",
    )


@router.post("/schuljahre/{schuljahr_id}")
def schuljahr_loeschen(
    schuljahr_id: int,
    bestaetigung: str = Form(""),
    session: Session = Depends(datenbanksitzung),
):
    schuljahr = hole(session, Schuljahr, schuljahr_id)
    _pruefe_bestaetigung(bestaetigung, schuljahr.bezeichnung)

    with uebersetzte_datenbankfehler(session):
        loeschdienst.loesche_schuljahr(session, schuljahr)
        session.commit()
    meldung = _verdichte(session)
    return RedirectResponse(f"/verwaltung/schuljahre?meldung={meldung}", WEITERLEITUNG)
