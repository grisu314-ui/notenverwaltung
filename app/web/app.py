"""FastAPI application.

Deliberately without authentication, sessions or identity handling. Access is
governed upstream: the container is reachable only over Tailscale, and no
route needs to know who is calling. Reading an identity header and doing
nothing with it would be exactly the kind of auth code this project avoids.

All user-visible text is German; identifiers and comments are English.
"""

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db.models import Klasse, Schuljahr
from app.services.fehler import Verwaltungsfehler
from app.services.settings import lies_einstellungen
from app.web.dependencies import datenbanksitzung
from app.web.gemeinsam import VERZEICHNIS, sortiert_nach_bezeichnung, templates
from app.web.routers import (
    ansicht,
    einstellungen,
    export,
    klassen,
    loeschen,
    noten,
    kurse,
    notengruppen,
    schueler,
    schuljahre,
    sitzplan,
    teilnahmen,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Notenverwaltung", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=VERZEICHNIS / "static"), name="static")

for modul in (
    ansicht,
    einstellungen,
    export,
    loeschen,
    noten,
    schuljahre,
    klassen,
    schueler,
    kurse,
    notengruppen,
    sitzplan,
    teilnahmen,
):
    app.include_router(modul.router)
app.include_router(schuljahre.halbjahr_router)


def _ist_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _fehlerantwort(request: Request, titel: str, meldung: str, status: int):
    """Every error is visible to the user, never swallowed."""
    vorlage = "fehler_block.html" if _ist_htmx(request) else "fehler.html"
    return templates.TemplateResponse(
        request=request,
        name=vorlage,
        context={"titel": titel, "meldung": meldung},
        status_code=status,
    )


@app.exception_handler(Verwaltungsfehler)
async def verwaltungsfehler(request: Request, exc: Verwaltungsfehler):
    """Refused input: the message is meant for the user and is shown as is."""
    logger.info("Eingabe abgewiesen bei %s: %s", request.url, exc)
    return _fehlerantwort(request, "Eingabe nicht möglich", str(exc), 400)


@app.exception_handler(RequestValidationError)
async def eingabefehler(request: Request, exc: RequestValidationError):
    """A malformed form must not answer with raw JSON.

    FastAPI's default handler returns a 422 with a JSON body describing the
    fields. In a server-rendered German interface that is neither readable nor
    expected.
    """
    logger.info("Unvollständige Anfrage bei %s: %s", request.url, exc.errors())
    return _fehlerantwort(
        request,
        "Eingabe unvollständig",
        "Die Anfrage enthielt nicht alle erwarteten Felder, oder ein Feld hatte "
        "ein unerwartetes Format — etwa ein unvollständiges Datum.",
        400,
    )


@app.exception_handler(StarletteHTTPException)
async def http_fehler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return _fehlerantwort(
            request,
            "Seite nicht gefunden",
            "Die aufgerufene Adresse gibt es nicht.",
            404,
        )
    logger.warning("HTTP-Fehler %s bei %s: %s", exc.status_code, request.url, exc.detail)
    return _fehlerantwort(request, "Fehler", str(exc.detail), exc.status_code)


@app.exception_handler(Exception)
async def unerwarteter_fehler(request: Request, exc: Exception):
    """Log with traceback and tell the user; never fail silently."""
    logger.exception("Unerwarteter Fehler bei %s", request.url)
    return _fehlerantwort(
        request,
        "Unerwarteter Fehler",
        "Die Aktion konnte nicht ausgeführt werden. Bitte erneut versuchen. "
        "Falls der Fehler bleibt, steht der Grund im Anwendungsprotokoll.",
        500,
    )


@app.get("/", response_class=HTMLResponse)
def startseite(request: Request, session: Session = Depends(datenbanksitzung)):
    einstellungen = lies_einstellungen(session)
    schuljahr = session.query(Schuljahr).filter_by(ist_aktiv=True).first()
    klassen_des_jahres = (
        sortiert_nach_bezeichnung(
            session.query(Klasse).filter_by(schuljahr_id=schuljahr.id).all()
        )
        if schuljahr is not None
        else []
    )
    return templates.TemplateResponse(
        request=request,
        name="start.html",
        context={
            "schuljahr": schuljahr,
            "klassen": klassen_des_jahres,
            "einstellungen": einstellungen,
        },
    )


@app.get("/verwaltung", response_class=HTMLResponse)
def verwaltung_start(request: Request):
    return templates.TemplateResponse(
        request=request, name="verwaltung/start.html", context={}
    )
