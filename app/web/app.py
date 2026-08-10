"""FastAPI application.

Deliberately without authentication, sessions or identity handling. Access is
governed upstream: the container is reachable only over Tailscale, and no
route needs to know who is calling. Reading an identity header and doing
nothing with it would be exactly the kind of auth code this project avoids.

All user-visible text is German; identifiers and comments are English.
"""

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db.models import Klasse, Schuljahr
from app.services.settings import lies_einstellungen
from app.services.sorting import anzeigename, vereinfacht
from app.web.dependencies import datenbanksitzung

logger = logging.getLogger(__name__)

VERZEICHNIS = Path(__file__).resolve().parent

app = FastAPI(title="Notenverwaltung", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=VERZEICHNIS / "static"), name="static")

templates = Jinja2Templates(directory=VERZEICHNIS / "templates")
templates.env.filters["anzeigename"] = anzeigename


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
    klassen = (
        sorted(
            session.query(Klasse).filter_by(schuljahr_id=schuljahr.id).all(),
            key=lambda klasse: (vereinfacht(klasse.bezeichnung), klasse.bezeichnung),
        )
        if schuljahr is not None
        else []
    )
    return templates.TemplateResponse(
        request=request,
        name="start.html",
        context={
            "schuljahr": schuljahr,
            "klassen": klassen,
            "einstellungen": einstellungen,
        },
    )
