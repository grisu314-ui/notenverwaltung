"""Course participation (specification 3.1, 5.5).

Not every pupil of a class attends every course of that class. Without this
the class averages would be wrong, which is why it is a record of its own and
not a flag on the pupil.
"""

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import Kurs, Schueler
from app.services import verwaltung
from app.services.fehler import uebersetzte_datenbankfehler
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import hole

router = APIRouter(prefix="/verwaltung/teilnahmen", tags=["verwaltung"])
WEITERLEITUNG = 303


@router.post("/kurs/{kurs_id}/schueler/{schueler_id}")
def umschalten(
    kurs_id: int,
    schueler_id: int,
    ist_aktiv: bool = Form(False),
    session: Session = Depends(datenbanksitzung),
):
    kurs = hole(session, Kurs, kurs_id)
    schueler = hole(session, Schueler, schueler_id)
    with uebersetzte_datenbankfehler(session):
        verwaltung.setze_teilnahme(session, kurs, schueler, ist_aktiv)
        session.commit()
    return RedirectResponse(
        f"/verwaltung/kurse/{kurs_id}?meldung=gespeichert", WEITERLEITUNG
    )
