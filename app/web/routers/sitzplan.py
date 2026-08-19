"""The seating plan of a class (specification 5.6).

Read-only until the edit mode is switched on: a stray touch during a lesson
must not reseat anyone. Assigning takes two taps and never a drag -- the
yardstick is a phone held in one hand (10).

Every state of the interface is a mode in the URL, and every mode renders the
same fragment. There is no client-side state to get out of step with the
database, and each of the four modes works without JavaScript as well: the
seats carry an ``href`` next to their ``hx-get``.
"""

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import Klasse, Schueler
from app.services import sitzplan as dienst
from app.services.fehler import uebersetzte_datenbankfehler
from app.services.settings import lies_einstellungen
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import hole, templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/klassen/{klasse_id}/sitzplan", tags=["sitzplan"])
WEITERLEITUNG = 303

MODUS_ANSICHT = "ansicht"
MODUS_BEARBEITEN = "bearbeiten"
MODUS_ZUWEISEN = "zuweisen"
MODUS_MENU = "menu"
MODUS_TAUSCHEN = "tauschen"
MODI = (MODUS_ANSICHT, MODUS_BEARBEITEN, MODUS_ZUWEISEN, MODUS_MENU, MODUS_TAUSCHEN)

# The modes that need a selected seat. Without one they fall back to the plain
# edit mode instead of rendering a panel about nothing.
MODI_MIT_AUSWAHL = (MODUS_ZUWEISEN, MODUS_MENU, MODUS_TAUSCHEN)


def _umfeld(
    session: Session,
    klasse: Klasse,
    modus: str,
    reihe: int | None,
    position: int | None,
    gerade_gespeichert: bool = False,
) -> dict:
    """Context for the fragment; the page template uses the same keys."""
    if modus not in MODI:
        modus = MODUS_ANSICHT
    if modus in MODI_MIT_AUSWAHL and (reihe is None or position is None):
        modus = MODUS_BEARBEITEN
        reihe = position = None

    blatt = dienst.blatt(session, klasse)
    gewaehlt = _gewaehlter_platz(blatt, reihe, position)
    if modus in MODI_MIT_AUSWAHL and gewaehlt is None:
        # The grid shrank under a link that is still open somewhere.
        modus = MODUS_BEARBEITEN

    return {
        "klasse": klasse,
        "blatt": blatt,
        "modus": modus,
        "auswahl": gewaehlt,
        "einstellungen": lies_einstellungen(session),
        "gerade_gespeichert": gerade_gespeichert,
    }


def _gewaehlter_platz(
    blatt: dienst.Blatt, reihe: int | None, position: int | None
) -> dienst.Platz | None:
    if reihe is None or position is None:
        return None
    if not 1 <= reihe <= len(blatt.reihen):
        return None
    plaetze = blatt.reihen[reihe - 1].plaetze
    if not 1 <= position <= len(plaetze):
        return None
    return plaetze[position - 1]


def _fragment(request: Request, umfeld: dict) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name="_sitzplan_raster.html", context=umfeld
    )


@router.get("", response_class=HTMLResponse)
def seite(
    request: Request,
    klasse_id: int,
    modus: str = MODUS_ANSICHT,
    reihe: int | None = None,
    position: int | None = None,
    session: Session = Depends(datenbanksitzung),
):
    """The whole page. Also the fallback for a browser without JavaScript."""
    klasse = hole(session, Klasse, klasse_id)
    umfeld = _umfeld(session, klasse, modus, reihe, position)
    session.commit()  # the plan may have been created by this very request
    return templates.TemplateResponse(
        request=request, name="sitzplan.html", context=umfeld
    )


@router.get("/raster", response_class=HTMLResponse)
def raster(
    request: Request,
    klasse_id: int,
    modus: str = MODUS_BEARBEITEN,
    reihe: int | None = None,
    position: int | None = None,
    session: Session = Depends(datenbanksitzung),
):
    """Just the grid and its panel -- the answer to every tap on a seat."""
    klasse = hole(session, Klasse, klasse_id)
    umfeld = _umfeld(session, klasse, modus, reihe, position)
    session.commit()
    return _fragment(request, umfeld)


@router.post("/platz/{reihe}/{position}", response_class=HTMLResponse)
def zuweisen(
    request: Request,
    klasse_id: int,
    reihe: int,
    position: int,
    schueler_id: int = Form(...),
    session: Session = Depends(datenbanksitzung),
):
    klasse = hole(session, Klasse, klasse_id)
    schueler = hole(session, Schueler, schueler_id)
    with uebersetzte_datenbankfehler(session):
        sitzplan = dienst.hole_oder_lege_an(session, klasse)
        dienst.setze_platz(session, sitzplan, reihe, position, schueler)
        session.commit()
    return _fragment(
        request, _umfeld(session, klasse, MODUS_BEARBEITEN, None, None, True)
    )


@router.post("/platz/{reihe}/{position}/raeumen", response_class=HTMLResponse)
def raeumen(
    request: Request,
    klasse_id: int,
    reihe: int,
    position: int,
    session: Session = Depends(datenbanksitzung),
):
    klasse = hole(session, Klasse, klasse_id)
    with uebersetzte_datenbankfehler(session):
        sitzplan = dienst.hole_oder_lege_an(session, klasse)
        dienst.raeume_platz(session, sitzplan, reihe, position)
        session.commit()
    return _fragment(
        request, _umfeld(session, klasse, MODUS_BEARBEITEN, None, None, True)
    )


@router.post("/tauschen", response_class=HTMLResponse)
def tauschen(
    request: Request,
    klasse_id: int,
    von_reihe: int = Form(...),
    von_position: int = Form(...),
    nach_reihe: int = Form(...),
    nach_position: int = Form(...),
    session: Session = Depends(datenbanksitzung),
):
    klasse = hole(session, Klasse, klasse_id)
    with uebersetzte_datenbankfehler(session):
        sitzplan = dienst.hole_oder_lege_an(session, klasse)
        dienst.tausche(
            session, sitzplan, (von_reihe, von_position), (nach_reihe, nach_position)
        )
        session.commit()
    return _fragment(
        request, _umfeld(session, klasse, MODUS_BEARBEITEN, None, None, True)
    )


@router.post("/raster")
def raster_aendern(
    klasse_id: int,
    reihen: int = Form(...),
    sitze_je_reihe: int = Form(...),
    session: Session = Depends(datenbanksitzung),
):
    """Change the grid. A full form, not htmx: the whole page changes shape."""
    klasse = hole(session, Klasse, klasse_id)
    with uebersetzte_datenbankfehler(session):
        sitzplan = dienst.hole_oder_lege_an(session, klasse)
        dienst.setze_raster(session, sitzplan, reihen, sitze_je_reihe)
        session.commit()
    return RedirectResponse(
        f"/klassen/{klasse_id}/sitzplan?modus={MODUS_BEARBEITEN}", WEITERLEITUNG
    )

