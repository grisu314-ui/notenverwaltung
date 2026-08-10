"""Pupils: name, list number, note, active flag.

Creating a pupil belongs to 5.1 in the specification, but without pupils
neither course participation nor anything after it can be used, so the plain
form lives here. Tiles with photos come with the class view, photo capture
with section 7.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import Klasse, Schueler
from app.services import verwaltung
from app.services.fehler import Verwaltungsfehler, uebersetzte_datenbankfehler
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import bestaetigung, hole, templates

router = APIRouter(prefix="/verwaltung/schueler", tags=["verwaltung"])
WEITERLEITUNG = 303


@router.post("/klasse/{klasse_id}")
def anlegen(
    klasse_id: int,
    vorname: str = Form(...),
    nachname: str = Form(...),
    listennummer: str = Form(""),
    notiz: str = Form(""),
    session: Session = Depends(datenbanksitzung),
):
    klasse = hole(session, Klasse, klasse_id)
    with uebersetzte_datenbankfehler(session):
        verwaltung.lege_schueler_an(
            session,
            klasse,
            vorname,
            nachname,
            int(listennummer) if listennummer.strip() else None,
            notiz,
        )
        session.commit()
    return RedirectResponse(
        f"/verwaltung/klassen/{klasse_id}?meldung=angelegt", WEITERLEITUNG
    )


@router.get("/{schueler_id}", response_class=HTMLResponse)
def einzeln(
    request: Request,
    schueler_id: int,
    meldung: str | None = None,
    session: Session = Depends(datenbanksitzung),
):
    schueler = hole(session, Schueler, schueler_id)
    return templates.TemplateResponse(
        request=request,
        name="verwaltung/schueler.html",
        context={"schueler": schueler, "bestaetigung": bestaetigung(meldung)},
    )


@router.post("/{schueler_id}")
def aendern(
    schueler_id: int,
    vorname: str = Form(...),
    nachname: str = Form(...),
    listennummer: str = Form(""),
    notiz: str = Form(""),
    ist_aktiv: bool = Form(False),
    session: Session = Depends(datenbanksitzung),
):
    schueler = hole(session, Schueler, schueler_id)
    with uebersetzte_datenbankfehler(session):
        if not vorname.strip() or not nachname.strip():
            raise Verwaltungsfehler("Vor- und Nachname dürfen nicht leer sein.")
        schueler.vorname = vorname.strip()
        schueler.nachname = nachname.strip()
        schueler.listennummer = int(listennummer) if listennummer.strip() else None
        schueler.notiz = notiz or None
        # ist_aktiv = False replaces deletion when a pupil leaves; the grades
        # stay (3.1).
        schueler.ist_aktiv = ist_aktiv
        session.commit()
    return RedirectResponse(
        f"/verwaltung/schueler/{schueler_id}?meldung=gespeichert", WEITERLEITUNG
    )


@router.post("/{schueler_id}/loeschen")
def loeschen(schueler_id: int, session: Session = Depends(datenbanksitzung)):
    schueler = hole(session, Schueler, schueler_id)
    klasse_id = schueler.klasse_id
    with uebersetzte_datenbankfehler(session):
        verwaltung.loesche_schueler(session, schueler)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/klassen/{klasse_id}?meldung=geloescht", WEITERLEITUNG
    )
