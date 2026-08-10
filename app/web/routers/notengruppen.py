"""Grade groups with their weights, per course and term (specification 5.5)."""

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import Halbjahr, Kurs, Notengruppe
from app.services import verwaltung
from app.services.fehler import uebersetzte_datenbankfehler
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import hole
from app.web.routers.kurse import als_dezimal

router = APIRouter(prefix="/verwaltung/notengruppen", tags=["verwaltung"])
WEITERLEITUNG = 303


@router.post("/kurs/{kurs_id}")
def anlegen(
    kurs_id: int,
    halbjahr_id: int = Form(...),
    bezeichnung: str = Form(...),
    gewicht: str = Form(...),
    reihenfolge: int = Form(0),
    session: Session = Depends(datenbanksitzung),
):
    kurs = hole(session, Kurs, kurs_id)
    halbjahr = hole(session, Halbjahr, halbjahr_id)
    with uebersetzte_datenbankfehler(session):
        verwaltung.lege_notengruppe_an(
            session,
            kurs,
            halbjahr,
            bezeichnung,
            als_dezimal(gewicht, "Das Gewicht"),
            reihenfolge,
        )
        session.commit()
    return RedirectResponse(
        f"/verwaltung/kurse/{kurs_id}?meldung=angelegt", WEITERLEITUNG
    )


@router.post("/{notengruppe_id}")
def aendern(
    notengruppe_id: int,
    bezeichnung: str = Form(...),
    gewicht: str = Form(...),
    reihenfolge: int = Form(0),
    session: Session = Depends(datenbanksitzung),
):
    notengruppe = hole(session, Notengruppe, notengruppe_id)
    kurs_id = notengruppe.kurs_id
    with uebersetzte_datenbankfehler(session):
        verwaltung.aendere_notengruppe(
            session,
            notengruppe,
            bezeichnung,
            als_dezimal(gewicht, "Das Gewicht"),
            reihenfolge,
        )
        session.commit()
    return RedirectResponse(
        f"/verwaltung/kurse/{kurs_id}?meldung=gespeichert", WEITERLEITUNG
    )


@router.post("/{notengruppe_id}/loeschen")
def loeschen(notengruppe_id: int, session: Session = Depends(datenbanksitzung)):
    notengruppe = hole(session, Notengruppe, notengruppe_id)
    kurs_id = notengruppe.kurs_id
    with uebersetzte_datenbankfehler(session):
        verwaltung.loesche_notengruppe(session, notengruppe)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/kurse/{kurs_id}?meldung=geloescht", WEITERLEITUNG
    )
