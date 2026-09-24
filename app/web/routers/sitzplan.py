"""The seating plan of a class (specification 5.6).

Read-only until the edit mode is switched on: a stray touch during a lesson
must not reseat anyone. Assigning takes two taps and never a drag -- the
yardstick is a phone held in one hand (10).

Every state of the interface is a mode in the URL, and every mode renders the
same fragment. There is no client-side state to get out of step with the
database, and every mode works without JavaScript as well: the seats carry an
``href`` next to their ``hx-get``.

The course travels in the URL for the same reason. The plan belongs to a
class, a grade belongs to a course, and the chosen course is what bridges the
two for the participation grade of the day (5.6). Without one the plan simply
does not offer it.

Two ways to that grade: the seat menu, one pupil with a remark, and the quick
entry (mode ``noten``), a select under every pupil that saves on change.
"""

import logging
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.clock import heute_lokal
from app.db.models import Klasse, Kurs, Schueler
from app.grading.notenwert import (
    NOTENWERTE,
    UngueltigeNoteError,
    als_anzeige,
    pruefe_notenwert,
)
from app.services import sitzplan as dienst
from app.services.fehler import Verwaltungsfehler, uebersetzte_datenbankfehler
from app.services.settings import lies_einstellungen
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import hole, sortiert_nach_bezeichnung, templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/klassen/{klasse_id}/sitzplan", tags=["sitzplan"])
WEITERLEITUNG = 303

MODUS_ANSICHT = "ansicht"
MODUS_BEARBEITEN = "bearbeiten"
MODUS_ZUWEISEN = "zuweisen"
MODUS_MENU = "menu"
MODUS_TAUSCHEN = "tauschen"
MODUS_MITARBEIT = "mitarbeit"
# The quick entry: a participation grade select under every pupil.
MODUS_NOTEN = "noten"
MODI = (
    MODUS_ANSICHT,
    MODUS_BEARBEITEN,
    MODUS_ZUWEISEN,
    MODUS_MENU,
    MODUS_TAUSCHEN,
    MODUS_MITARBEIT,
    MODUS_NOTEN,
)

# The modes that need a selected seat. Without one they fall back to the plain
# edit mode instead of rendering a panel about nothing.
MODI_MIT_AUSWAHL = (MODUS_ZUWEISEN, MODUS_MENU, MODUS_TAUSCHEN, MODUS_MITARBEIT)


def als_notenwert(wert: str) -> Decimal:
    """One select value as a grade, or a refusal. Never a guess."""
    try:
        return pruefe_notenwert(Decimal(wert.strip()))
    except (InvalidOperation, UngueltigeNoteError) as fehler:
        raise Verwaltungsfehler(
            f"\u201e{wert}\u201c ist keine g\u00fcltige Note."
        ) from fehler


GANZE_NOTEN = tuple(wert for wert in NOTENWERTE if wert == wert.to_integral_value())


def mitarbeitsauswahl(vorhanden: Decimal | None = None) -> list[tuple[str, str]]:
    """What the plan offers for a participation grade: 1 to 6, no Tendenz (5.6).

    No "nicht gewertet" and no "nicht erbracht" either: a participation grade
    is always counted, because there is no performance somebody failed to
    deliver.

    The restriction is on the offer, not on the data. A grade stored with a
    Tendenz -- entered in the serial entry, or before this rule -- is added
    to the list, so the select shows what is stored instead of falling back
    to "–" and suggesting there is no grade.
    """
    werte = list(GANZE_NOTEN)
    if vorhanden is not None and vorhanden not in werte:
        werte = sorted([*werte, vorhanden])
    return [(str(wert), als_anzeige(wert)) for wert in werte]


def _gewaehlter_kurs(session: Session, klasse: Klasse, kurs_id: int | None) -> Kurs | None:
    """The course of the current lesson, or None while none is chosen."""
    if kurs_id is None:
        return None
    kurs = session.get(Kurs, kurs_id)
    if kurs is None or kurs.klasse_id != klasse.id:
        # A link from another class, or a course that has since been deleted.
        return None
    return kurs


def _umfeld(
    session: Session,
    klasse: Klasse,
    modus: str,
    reihe: int | None,
    position: int | None,
    gerade_gespeichert: bool = False,
    kurs_id: int | None = None,
    meldung: str | None = None,
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

    kurs = _gewaehlter_kurs(session, klasse, kurs_id)
    if modus == MODUS_MITARBEIT and (kurs is None or gewaehlt is None or gewaehlt.ist_frei):
        modus = MODUS_BEARBEITEN

    heute = heute_lokal()
    # Today's grades are read only where a grade is being entered. The plan
    # shows no grades otherwise (5.6), and the print never.
    tagesstand = None
    if kurs is not None and modus in (MODUS_NOTEN, MODUS_MITARBEIT):
        tagesstand = dienst.tagesstand(session, kurs, heute)

    return {
        "klasse": klasse,
        "blatt": blatt,
        "modus": modus,
        "auswahl": gewaehlt,
        "kurs": kurs,
        "kurse": sortiert_nach_bezeichnung(klasse.kurse, "fach"),
        "mitarbeitsauswahl": mitarbeitsauswahl,
        "heute": heute,
        "tagesstand": tagesstand,
        "einstellungen": lies_einstellungen(session),
        "gerade_gespeichert": gerade_gespeichert,
        "meldung": meldung,
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
    kurs: int | None = None,
    session: Session = Depends(datenbanksitzung),
):
    """The whole page. Also the fallback for a browser without JavaScript."""
    klasse = hole(session, Klasse, klasse_id)
    umfeld = _umfeld(session, klasse, modus, reihe, position, kurs_id=kurs)
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
    kurs: int | None = None,
    session: Session = Depends(datenbanksitzung),
):
    """Just the grid and its panel -- the answer to every tap on a seat."""
    klasse = hole(session, Klasse, klasse_id)
    umfeld = _umfeld(session, klasse, modus, reihe, position, kurs_id=kurs)
    session.commit()
    return _fragment(request, umfeld)


@router.post("/platz/{reihe}/{position}", response_class=HTMLResponse)
def zuweisen(
    request: Request,
    klasse_id: int,
    reihe: int,
    position: int,
    schueler_id: int = Form(...),
    kurs: int | None = Form(None),
    session: Session = Depends(datenbanksitzung),
):
    klasse = hole(session, Klasse, klasse_id)
    schueler = hole(session, Schueler, schueler_id)
    with uebersetzte_datenbankfehler(session):
        sitzplan = dienst.hole_oder_lege_an(session, klasse)
        dienst.setze_platz(session, sitzplan, reihe, position, schueler)
        session.commit()
    return _fragment(
        request,
        _umfeld(session, klasse, MODUS_BEARBEITEN, None, None, True, kurs_id=kurs),
    )


@router.post("/platz/{reihe}/{position}/raeumen", response_class=HTMLResponse)
def raeumen(
    request: Request,
    klasse_id: int,
    reihe: int,
    position: int,
    kurs: int | None = Form(None),
    session: Session = Depends(datenbanksitzung),
):
    klasse = hole(session, Klasse, klasse_id)
    with uebersetzte_datenbankfehler(session):
        sitzplan = dienst.hole_oder_lege_an(session, klasse)
        dienst.raeume_platz(session, sitzplan, reihe, position)
        session.commit()
    return _fragment(
        request,
        _umfeld(session, klasse, MODUS_BEARBEITEN, None, None, True, kurs_id=kurs),
    )


@router.post("/tauschen", response_class=HTMLResponse)
def tauschen(
    request: Request,
    klasse_id: int,
    von_reihe: int = Form(...),
    von_position: int = Form(...),
    nach_reihe: int = Form(...),
    nach_position: int = Form(...),
    kurs: int | None = Form(None),
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
        request,
        _umfeld(session, klasse, MODUS_BEARBEITEN, None, None, True, kurs_id=kurs),
    )


@router.post("/platz/{reihe}/{position}/mitarbeit", response_class=HTMLResponse)
def mitarbeitsnote(
    request: Request,
    klasse_id: int,
    reihe: int,
    position: int,
    kurs: int = Form(...),
    notenwert: str = Form(...),
    notiz: str = Form(""),
    session: Session = Depends(datenbanksitzung),
):
    """The one grade the seating plan writes (5.6).

    The pupil comes from the seat, not from the form: what is stored has to be
    who is sitting there now, not who was there when the page was rendered.
    """
    klasse = hole(session, Klasse, klasse_id)
    gewaehlter_kurs = _gewaehlter_kurs(session, klasse, kurs)
    if gewaehlter_kurs is None:
        raise Verwaltungsfehler(
            "Für diese Klasse ist kein Kurs gewählt. Bitte oben den Kurs "
            "auswählen, in dem gerade unterrichtet wird."
        )

    with uebersetzte_datenbankfehler(session):
        sitzplan = dienst.hole_oder_lege_an(session, klasse)
        schueler = dienst.schueler_auf_platz(session, sitzplan, reihe, position)
        if schueler is None:
            raise Verwaltungsfehler(
                f"Auf Reihe {reihe}, Platz {position} sitzt niemand. "
                "Bitte die Seite neu laden."
            )
        note = dienst.mitarbeitsnote(
            session, gewaehlter_kurs, schueler, als_notenwert(notenwert), notiz
        )
        session.commit()

    meldung = (
        f"Mitarbeitsnote {als_anzeige(note.notenwert)} für "
        f"{schueler.vorname} {schueler.nachname} in {gewaehlter_kurs.fach}"
    )
    return _fragment(
        request,
        _umfeld(
            session,
            klasse,
            MODUS_BEARBEITEN,
            None,
            None,
            True,
            kurs_id=kurs,
            meldung=meldung,
        ),
    )


@router.post("/mitarbeit/{schueler_id}")
def schnelle_mitarbeitsnote(
    request: Request,
    klasse_id: int,
    schueler_id: int,
    kurs: int = Form(...),
    notenwert: str = Form(""),
    session: Session = Depends(datenbanksitzung),
):
    """One select of the quick entry: set, change or take back today's grade.

    Keyed by pupil, not by seat, unlike the seat menu. The select sits right
    under a photo and a name; if the seating changed in the meantime, the
    grade still has to go to the person whose name was next to it.

    "–" deletes today's grade, as "keine Note" does in the serial entry. The
    remark is left alone either way -- this form has no field for it.
    """
    klasse = hole(session, Klasse, klasse_id)
    gewaehlter_kurs = _gewaehlter_kurs(session, klasse, kurs)
    if gewaehlter_kurs is None:
        raise Verwaltungsfehler(
            "Für diese Klasse ist kein Kurs gewählt. Bitte oben den Kurs "
            "auswählen, in dem gerade unterrichtet wird."
        )
    schueler = hole(session, Schueler, schueler_id)
    if schueler.klasse_id != klasse.id or not schueler.ist_aktiv:
        raise Verwaltungsfehler(
            f"{schueler.vorname} {schueler.nachname} ist kein aktiver Schüler "
            "dieser Klasse. Bitte die Seite neu laden."
        )

    heute = heute_lokal()
    with uebersetzte_datenbankfehler(session):
        if notenwert.strip() == "":
            dienst.loesche_mitarbeitsnote(session, gewaehlter_kurs, schueler, heute)
        else:
            dienst.mitarbeitsnote(
                session,
                gewaehlter_kurs,
                schueler,
                als_notenwert(notenwert),
                notiz=None,
                datum=heute,
            )
        session.commit()

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            f"/klassen/{klasse_id}/sitzplan?modus={MODUS_NOTEN}&kurs={gewaehlter_kurs.id}",
            WEITERLEITUNG,
        )
    # Rendered after the commit, from what was stored: the select shows the
    # grade in the database, not the one that was sent (10).
    return templates.TemplateResponse(
        request=request,
        name="_mitarbeitsfeld.html",
        context={
            "klasse": klasse,
            "kurs": gewaehlter_kurs,
            "s": schueler,
            "tagesstand": dienst.tagesstand(session, gewaehlter_kurs, heute),
            "mitarbeitsauswahl": mitarbeitsauswahl,
            "feld_gespeichert": True,
        },
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

