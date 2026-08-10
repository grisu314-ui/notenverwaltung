"""Classes (specification 5.5)."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import Klasse, Schuljahr
from app.services import verwaltung
from app.services.fehler import uebersetzte_datenbankfehler
from app.services.settings import lies_einstellungen
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import (
    bestaetigung,
    hole,
    sortiert_nach_bezeichnung,
    sortierte_schueler,
    templates,
)

router = APIRouter(prefix="/verwaltung/klassen", tags=["verwaltung"])
WEITERLEITUNG = 303


@router.post("/schuljahr/{schuljahr_id}")
def anlegen(
    schuljahr_id: int,
    bezeichnung: str = Form(...),
    notiz: str = Form(""),
    session: Session = Depends(datenbanksitzung),
):
    schuljahr = hole(session, Schuljahr, schuljahr_id)
    with uebersetzte_datenbankfehler(session):
        klasse = verwaltung.lege_klasse_an(session, schuljahr, bezeichnung, notiz)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/klassen/{klasse.id}?meldung=angelegt", WEITERLEITUNG
    )


@router.get("/{klasse_id}", response_class=HTMLResponse)
def einzeln(
    request: Request,
    klasse_id: int,
    meldung: str | None = None,
    session: Session = Depends(datenbanksitzung),
):
    klasse = hole(session, Klasse, klasse_id)
    einstellungen = lies_einstellungen(session)
    return templates.TemplateResponse(
        request=request,
        name="verwaltung/klasse.html",
        context={
            "klasse": klasse,
            "schueler": sortierte_schueler(klasse.schueler, einstellungen.sortierung),
            "kurse": sortiert_nach_bezeichnung(klasse.kurse, "fach"),
            "einstellungen": einstellungen,
            "bestaetigung": bestaetigung(meldung),
        },
    )


@router.post("/{klasse_id}")
def aendern(
    klasse_id: int,
    bezeichnung: str = Form(...),
    notiz: str = Form(""),
    session: Session = Depends(datenbanksitzung),
):
    klasse = hole(session, Klasse, klasse_id)
    with uebersetzte_datenbankfehler(session):
        klasse.bezeichnung = bezeichnung.strip()
        klasse.notiz = notiz or None
        session.commit()
    return RedirectResponse(
        f"/verwaltung/klassen/{klasse_id}?meldung=gespeichert", WEITERLEITUNG
    )


@router.post("/{klasse_id}/loeschen")
def loeschen(klasse_id: int, session: Session = Depends(datenbanksitzung)):
    klasse = hole(session, Klasse, klasse_id)
    schuljahr_id = klasse.schuljahr_id
    with uebersetzte_datenbankfehler(session):
        verwaltung.loesche_klasse(session, klasse)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/schuljahre/{schuljahr_id}?meldung=geloescht", WEITERLEITUNG
    )
