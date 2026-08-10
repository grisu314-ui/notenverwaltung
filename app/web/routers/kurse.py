"""Courses: a subject taught in one class (specification 5.5)."""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import Klasse, Kurs
from app.services import verwaltung
from app.services.fehler import Verwaltungsfehler, uebersetzte_datenbankfehler
from app.services.settings import lies_einstellungen
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import bestaetigung, hole, sortierte_schueler, templates

router = APIRouter(prefix="/verwaltung/kurse", tags=["verwaltung"])
WEITERLEITUNG = 303


def als_dezimal(text: str, was: str) -> Decimal:
    """Accept a German decimal comma; never let a float near a weight."""
    try:
        return Decimal(text.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise Verwaltungsfehler(f"{was} ist keine gültige Zahl: „{text}“.") from None


@router.post("/klasse/{klasse_id}")
def anlegen(
    klasse_id: int,
    fach: str = Form(...),
    notiz: str = Form(""),
    session: Session = Depends(datenbanksitzung),
):
    klasse = hole(session, Klasse, klasse_id)
    with uebersetzte_datenbankfehler(session):
        kurs = verwaltung.lege_kurs_an(session, klasse, fach, notiz)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/kurse/{kurs.id}?meldung=angelegt", WEITERLEITUNG
    )


@router.get("/{kurs_id}", response_class=HTMLResponse)
def einzeln(
    request: Request,
    kurs_id: int,
    meldung: str | None = None,
    session: Session = Depends(datenbanksitzung),
):
    kurs = hole(session, Kurs, kurs_id)
    einstellungen = lies_einstellungen(session)
    teilnahme_je_schueler = {
        teilnahme.schueler_id: teilnahme for teilnahme in kurs.teilnahmen
    }
    halbjahre = sorted(kurs.klasse.schuljahr.halbjahre, key=lambda h: h.nummer)
    notengruppen = sorted(
        kurs.notengruppen,
        key=lambda gruppe: (gruppe.halbjahr.nummer, gruppe.reihenfolge, gruppe.id),
    )
    return templates.TemplateResponse(
        request=request,
        name="verwaltung/kurs.html",
        context={
            "kurs": kurs,
            "halbjahre": halbjahre,
            "notengruppen": notengruppen,
            "schueler": sortierte_schueler(
                kurs.klasse.schueler, einstellungen.sortierung
            ),
            "teilnahme_je_schueler": teilnahme_je_schueler,
            "einstellungen": einstellungen,
            "bestaetigung": bestaetigung(meldung),
        },
    )


@router.post("/{kurs_id}")
def aendern(
    kurs_id: int,
    fach: str = Form(...),
    notiz: str = Form(""),
    gewicht_halbjahr_1: str = Form(...),
    gewicht_halbjahr_2: str = Form(...),
    session: Session = Depends(datenbanksitzung),
):
    kurs = hole(session, Kurs, kurs_id)
    with uebersetzte_datenbankfehler(session):
        verwaltung.aendere_kurs(
            session,
            kurs,
            fach,
            notiz,
            als_dezimal(gewicht_halbjahr_1, "Das Gewicht von Halbjahr 1"),
            als_dezimal(gewicht_halbjahr_2, "Das Gewicht von Halbjahr 2"),
        )
        session.commit()
    return RedirectResponse(
        f"/verwaltung/kurse/{kurs_id}?meldung=gespeichert", WEITERLEITUNG
    )


@router.post("/{kurs_id}/loeschen")
def loeschen(kurs_id: int, session: Session = Depends(datenbanksitzung)):
    kurs = hole(session, Kurs, kurs_id)
    klasse_id = kurs.klasse_id
    with uebersetzte_datenbankfehler(session):
        verwaltung.loesche_kurs(session, kurs)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/klassen/{klasse_id}?meldung=geloescht", WEITERLEITUNG
    )
