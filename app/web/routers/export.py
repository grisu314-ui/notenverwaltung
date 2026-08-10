"""Downloads of the whole dataset (specification 8, 11).

The file is produced in memory when it is asked for and handed straight to
the browser. Nothing is written to disk, and nothing leaves the application
except through a download somebody triggered.
"""

from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.services import export as exportdienst
from app.web.dependencies import datenbanksitzung

router = APIRouter(prefix="/export", tags=["export"])

TYP_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TYP_MARKDOWN = "text/markdown; charset=utf-8"


def _dateiname(endung: str) -> str:
    """Plain ASCII, built here and never from stored data.

    Nothing from the database reaches the header, so no name from an Excel
    import can break it.
    """
    return f"notenverwaltung-export-{date.today():%Y-%m-%d}.{endung}"


def _als_download(inhalt: bytes, typ: str, endung: str) -> Response:
    return Response(
        content=inhalt,
        media_type=typ,
        headers={
            "Content-Disposition": f'attachment; filename="{_dateiname(endung)}"'
        },
    )


@router.get("/markdown")
def markdown(session: Session = Depends(datenbanksitzung)) -> Response:
    text = exportdienst.als_markdown(session)
    return _als_download(text.encode("utf-8"), TYP_MARKDOWN, "md")


@router.get("/xlsx")
def xlsx(session: Session = Depends(datenbanksitzung)) -> Response:
    return _als_download(exportdienst.als_xlsx(session), TYP_XLSX, "xlsx")
