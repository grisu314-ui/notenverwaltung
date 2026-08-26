"""Class view, pupil view and search (specification 5.1, 5.2)."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.models import Klasse, Kurs, Schueler
from app.services import kursblatt as kursblattdienst
from app.services.klasse import zahlen as klassenzahlen
from app.services import suche as suchdienst
from app.services.schuelerblatt import blatt
from app.services.settings import lies_einstellungen
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import (
    hole,
    sortiert_nach_bezeichnung,
    sortierte_schueler,
    templates,
)

router = APIRouter(tags=["ansicht"])

# Photos are re-encoded to JPEG on upload (section 7), so this is the only
# type the column ever holds.
FOTO_TYP = "image/jpeg"


@router.get("/klassen/{klasse_id}", response_class=HTMLResponse)
def klassenansicht(
    request: Request, klasse_id: int, session: Session = Depends(datenbanksitzung)
):
    """Tiles of the active pupils of a class (5.1).

    Inactive pupils stay reachable through the search and the management view.
    """
    klasse = hole(session, Klasse, klasse_id)
    einstellungen = lies_einstellungen(session)
    aktive = [schueler for schueler in klasse.schueler if schueler.ist_aktiv]
    return templates.TemplateResponse(
        request=request,
        name="klasse.html",
        context={
            "klasse": klasse,
            "kurse": sortiert_nach_bezeichnung(klasse.kurse, "fach"),
            "schueler": sortierte_schueler(aktive, einstellungen.sortierung),
            "zahlen": klassenzahlen(session, klasse),
            "einstellungen": einstellungen,
            "ziel": f"/klassen/{klasse_id}",
        },
    )


@router.get("/kurse/{kurs_id}", response_class=HTMLResponse)
def kursuebersicht(
    request: Request,
    kurs_id: int,
    ansicht: str = kursblattdienst.ANSICHT_HALBJAHR_1,
    session: Session = Depends(datenbanksitzung),
):
    """Matrix of all grades of all participants (5.3), read-only."""
    kurs = hole(session, Kurs, kurs_id)
    return templates.TemplateResponse(
        request=request,
        name="kursuebersicht.html",
        context={
            "blatt": kursblattdienst.blatt(session, kurs, ansicht),
            "einstellungen": lies_einstellungen(session),
            "ansichten": (
                (kursblattdienst.ANSICHT_HALBJAHR_1, "Halbjahr 1"),
                (kursblattdienst.ANSICHT_HALBJAHR_2, "Halbjahr 2"),
                (kursblattdienst.ANSICHT_JAHR, "Jahr"),
            ),
        },
    )


@router.get("/schueler/{schueler_id}", response_class=HTMLResponse)
def schueleransicht(
    request: Request, schueler_id: int, session: Session = Depends(datenbanksitzung)
):
    schueler = hole(session, Schueler, schueler_id)
    einstellungen = lies_einstellungen(session)
    return templates.TemplateResponse(
        request=request,
        name="schueler.html",
        context={
            "blatt": blatt(session, schueler),
            "einstellungen": einstellungen,
            "ziel": f"/schueler/{schueler_id}",
        },
    )


@router.get("/schueler/{schueler_id}/foto")
def foto(schueler_id: int, session: Session = Depends(datenbanksitzung)):
    """Serve the stored image, or answer 404 when there is none.

    Until the photo capture exists, every pupil is without one; returning the
    empty column would be a server error on every single tile.
    """
    schueler = hole(session, Schueler, schueler_id)
    if schueler.foto is None:
        raise HTTPException(
            status_code=404, detail="Für diesen Schüler ist kein Foto hinterlegt."
        )
    return Response(content=schueler.foto, media_type=FOTO_TYP)


@router.get("/suche", response_class=HTMLResponse)
def suche(
    request: Request, q: str = "", session: Session = Depends(datenbanksitzung)
):
    """Search across all classes and all school years (5.2)."""
    einstellungen = lies_einstellungen(session)
    treffer = sortierte_schueler(
        suchdienst.suche_schueler(session, q), einstellungen.sortierung
    )
    return templates.TemplateResponse(
        request=request,
        name="suche.html",
        context={
            "begriff": q,
            "treffer": treffer,
            "einstellungen": einstellungen,
            "ziel": f"/suche?q={q}" if q else "/suche",
        },
    )
