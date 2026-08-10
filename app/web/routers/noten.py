"""Assessments and the serial grade entry (specification 5.4)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import Kurs, Leistung, Notengruppe
from app.enums import NoteStatus
from app.grading.notenwert import NOTENWERTE, als_anzeige
from app.services import noten as notendienst
from app.services.fehler import Verwaltungsfehler, uebersetzte_datenbankfehler
from app.services.settings import lies_einstellungen
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import bestaetigung, hole, sortierte_schueler, templates
from app.web.routers.kurse import als_dezimal

router = APIRouter(tags=["noten"])
WEITERLEITUNG = 303

LEEREN = ""


def auswahlmoeglichkeiten() -> list[tuple[str, str]]:
    """Value and label of every entry in the grade select (4.1, 4.3)."""
    eintraege = [(LEEREN, "— keine Note —")]
    eintraege += [(str(wert), als_anzeige(wert)) for wert in NOTENWERTE]
    eintraege += [
        (str(NoteStatus.NICHT_GEWERTET), "nicht gewertet"),
        (str(NoteStatus.NICHT_ERBRACHT), "nicht erbracht"),
    ]
    return eintraege


def _gewaehlt(wert: str) -> tuple[NoteStatus | None, Decimal | None]:
    """Translate one select value into status and grade value."""
    wert = wert.strip()
    if wert == LEEREN:
        return None, None
    if wert == NoteStatus.NICHT_GEWERTET:
        return NoteStatus.NICHT_GEWERTET, None
    if wert == NoteStatus.NICHT_ERBRACHT:
        return NoteStatus.NICHT_ERBRACHT, None
    try:
        return NoteStatus.GEWERTET, Decimal(wert)
    except ArithmeticError:
        raise Verwaltungsfehler(f"„{wert}“ ist keine gültige Auswahl.") from None


def _teilnehmer(kurs: Kurs, session: Session):
    einstellungen = lies_einstellungen(session)
    aktive = [
        teilnahme.schueler
        for teilnahme in kurs.teilnahmen
        if teilnahme.ist_aktiv and teilnahme.schueler.ist_aktiv
    ]
    return sortierte_schueler(aktive, einstellungen.sortierung), einstellungen


def _eingabekontext(session: Session, leistung: Leistung) -> dict:
    kurs = leistung.notengruppe.kurs
    schueler, einstellungen = _teilnehmer(kurs, session)
    noten = {s.id: notendienst.note_von(leistung, s) for s in schueler}
    return {
        "leistung": leistung,
        "kurs": kurs,
        "schueler": schueler,
        "noten": noten,
        "einstellungen": einstellungen,
        "auswahl": auswahlmoeglichkeiten(),
        "eingetragen": sum(1 for note in noten.values() if note is not None),
        "gesamt": len(schueler),
    }


@router.get("/kurse/{kurs_id}/leistungen", response_class=HTMLResponse)
def leistungen(
    request: Request,
    kurs_id: int,
    meldung: str | None = None,
    session: Session = Depends(datenbanksitzung),
):
    kurs = hole(session, Kurs, kurs_id)
    notengruppen = sorted(
        kurs.notengruppen,
        key=lambda gruppe: (gruppe.halbjahr.nummer, gruppe.reihenfolge, gruppe.id),
    )
    return templates.TemplateResponse(
        request=request,
        name="leistungen.html",
        context={
            "kurs": kurs,
            "notengruppen": notengruppen,
            "heute": date.today(),
            "bestaetigung": bestaetigung(meldung),
        },
    )


@router.post("/notengruppen/{notengruppe_id}/leistungen")
def leistung_anlegen(
    notengruppe_id: int,
    bezeichnung: str = Form(...),
    datum: date = Form(...),
    gewicht: str = Form("1.0"),
    session: Session = Depends(datenbanksitzung),
):
    notengruppe = hole(session, Notengruppe, notengruppe_id)
    with uebersetzte_datenbankfehler(session):
        leistung = notendienst.lege_leistung_an(
            session,
            notengruppe,
            bezeichnung,
            datum,
            als_dezimal(gewicht, "Das Gewicht der Leistung"),
        )
        session.commit()
    return RedirectResponse(f"/leistungen/{leistung.id}", WEITERLEITUNG)


@router.get("/leistungen/{leistung_id}", response_class=HTMLResponse)
def eingabe(
    request: Request,
    leistung_id: int,
    session: Session = Depends(datenbanksitzung),
):
    """Serial entry: one assessment, all participants, no page change (5.4)."""
    leistung = hole(session, Leistung, leistung_id)
    return templates.TemplateResponse(
        request=request,
        name="eingabe.html",
        context=_eingabekontext(session, leistung),
    )


@router.post("/leistungen/{leistung_id}")
def leistung_aendern(
    leistung_id: int,
    bezeichnung: str = Form(...),
    datum: date = Form(...),
    gewicht: str = Form(...),
    session: Session = Depends(datenbanksitzung),
):
    leistung = hole(session, Leistung, leistung_id)
    with uebersetzte_datenbankfehler(session):
        notendienst.aendere_leistung(
            session,
            leistung,
            bezeichnung,
            datum,
            als_dezimal(gewicht, "Das Gewicht der Leistung"),
        )
        session.commit()
    return RedirectResponse(f"/leistungen/{leistung_id}", WEITERLEITUNG)


@router.post("/leistungen/{leistung_id}/loeschen")
def leistung_loeschen(
    leistung_id: int, session: Session = Depends(datenbanksitzung)
):
    leistung = hole(session, Leistung, leistung_id)
    kurs_id = leistung.notengruppe.kurs_id
    with uebersetzte_datenbankfehler(session):
        notendienst.loesche_leistung(session, leistung)
        session.commit()
    return RedirectResponse(
        f"/kurse/{kurs_id}/leistungen?meldung=geloescht", WEITERLEITUNG
    )


@router.post("/leistungen/{leistung_id}/schueler/{schueler_id}")
def note_eintragen(
    request: Request,
    leistung_id: int,
    schueler_id: int,
    wert: str = Form(LEEREN),
    session: Session = Depends(datenbanksitzung),
):
    """Store one grade and answer with the row as it now stands in the database.

    The confirmation the user sees is rendered **after** the commit, from the
    stored row. A row can therefore never look saved when it is not.
    """
    leistung = hole(session, Leistung, leistung_id)
    schueler = next(
        (s for s in _teilnehmer(leistung.notengruppe.kurs, session)[0]
         if s.id == schueler_id),
        None,
    )
    if schueler is None:
        raise Verwaltungsfehler(
            "Dieser Schüler nimmt an dem Kurs nicht (mehr) teil."
        )

    status, notenwert = _gewaehlt(wert)
    with uebersetzte_datenbankfehler(session):
        if status is None:
            notendienst.loesche_note(session, leistung, schueler)
        else:
            notendienst.setze_note(session, leistung, schueler, status, notenwert)
        session.commit()

    if request.headers.get("HX-Request") == "true":
        kontext = _eingabekontext(session, leistung)
        kontext["s"] = schueler
        kontext["gerade_gespeichert"] = True
        return templates.TemplateResponse(
            request=request, name="_notenzeile.html", context=kontext
        )
    return RedirectResponse(f"/leistungen/{leistung_id}", WEITERLEITUNG)
