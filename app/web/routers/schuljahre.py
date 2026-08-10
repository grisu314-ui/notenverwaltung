"""School years and their two terms (specification 5.5)."""

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import Halbjahr, Schuljahr
from app.services import verwaltung
from app.services.fehler import uebersetzte_datenbankfehler
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import bestaetigung, hole, templates

router = APIRouter(prefix="/verwaltung/schuljahre", tags=["verwaltung"])
halbjahr_router = APIRouter(prefix="/verwaltung/halbjahre", tags=["verwaltung"])

WEITERLEITUNG = 303


@router.get("", response_class=HTMLResponse)
def liste(
    request: Request,
    meldung: str | None = None,
    session: Session = Depends(datenbanksitzung),
):
    schuljahre = session.query(Schuljahr).order_by(Schuljahr.beginn.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="verwaltung/schuljahre.html",
        context={"schuljahre": schuljahre, "bestaetigung": bestaetigung(meldung)},
    )


@router.post("")
def anlegen(
    bezeichnung: str = Form(...),
    beginn: date = Form(...),
    ende: date = Form(...),
    ist_aktiv: bool = Form(False),
    session: Session = Depends(datenbanksitzung),
):
    with uebersetzte_datenbankfehler(session):
        schuljahr = verwaltung.lege_schuljahr_an(
            session, bezeichnung, beginn, ende, ist_aktiv
        )
        session.commit()
    return RedirectResponse(
        f"/verwaltung/schuljahre/{schuljahr.id}?meldung=angelegt", WEITERLEITUNG
    )


@router.get("/{schuljahr_id}", response_class=HTMLResponse)
def einzeln(
    request: Request,
    schuljahr_id: int,
    meldung: str | None = None,
    session: Session = Depends(datenbanksitzung),
):
    schuljahr = hole(session, Schuljahr, schuljahr_id)
    return templates.TemplateResponse(
        request=request,
        name="verwaltung/schuljahr.html",
        context={"schuljahr": schuljahr, "bestaetigung": bestaetigung(meldung)},
    )


@router.post("/{schuljahr_id}")
def aendern(
    schuljahr_id: int,
    bezeichnung: str = Form(...),
    beginn: date = Form(...),
    ende: date = Form(...),
    session: Session = Depends(datenbanksitzung),
):
    schuljahr = hole(session, Schuljahr, schuljahr_id)
    with uebersetzte_datenbankfehler(session):
        verwaltung.aendere_schuljahr(session, schuljahr, bezeichnung, beginn, ende)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/schuljahre/{schuljahr_id}?meldung=gespeichert", WEITERLEITUNG
    )


@router.post("/{schuljahr_id}/aktiv")
def aktiv_setzen(schuljahr_id: int, session: Session = Depends(datenbanksitzung)):
    schuljahr = hole(session, Schuljahr, schuljahr_id)
    with uebersetzte_datenbankfehler(session):
        verwaltung.setze_aktives_schuljahr(session, schuljahr)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/schuljahre/{schuljahr_id}?meldung=aktiviert", WEITERLEITUNG
    )


@router.post("/{schuljahr_id}/loeschen")
def loeschen(schuljahr_id: int, session: Session = Depends(datenbanksitzung)):
    schuljahr = hole(session, Schuljahr, schuljahr_id)
    with uebersetzte_datenbankfehler(session):
        verwaltung.loesche_schuljahr(session, schuljahr)
        session.commit()
    return RedirectResponse("/verwaltung/schuljahre?meldung=geloescht", WEITERLEITUNG)


@halbjahr_router.post("/{halbjahr_id}")
def halbjahr_aendern(
    halbjahr_id: int,
    beginn: date = Form(...),
    ende: date = Form(...),
    session: Session = Depends(datenbanksitzung),
):
    halbjahr = hole(session, Halbjahr, halbjahr_id)
    with uebersetzte_datenbankfehler(session):
        verwaltung.aendere_halbjahr(session, halbjahr, beginn, ende)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/schuljahre/{halbjahr.schuljahr_id}?meldung=gespeichert",
        WEITERLEITUNG,
    )
