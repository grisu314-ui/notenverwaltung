"""Seed a development database with invented data.

Local development, tests and migration rehearsals run against this and never
against the productive file, which holds real names and photographs.

All names here are invented and the photos are generated placeholders -- a
coloured square with the initials, never a real portrait.

Usage:

    NOTENVERWALTUNG_DB=data/dev.db .venv/bin/python scripts/seed_dev.py
"""

import sys
from datetime import date
from io import BytesIO
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import database_path, database_url  # noqa: E402
from app.db.models import (  # noqa: E402
    Halbjahr,
    Klasse,
    Kurs,
    Kursteilnahme,
    Leistung,
    Note,
    Notengruppe,
    Schueler,
    Schuljahr,
)
from app.clock import utc_now  # noqa: E402
from app.db.session import create_app_engine, create_session_factory  # noqa: E402
from app.services.foto import verarbeite  # noqa: E402
from app.enums import NoteStatus  # noqa: E402

NAMEN_BFS = [
    ("Änne", "Öztürk"),
    ("Bernd", "Straßer"),
    ("Cem", "Aydın"),
    ("Dorothea", "Zäpfel"),
    ("Emil", "Übelacker"),
    ("Fatima", "Achenbach"),
]
NAMEN_BS = [
    ("Gregor", "Wiesinger"),
    ("Hanna", "Ärtel"),
    ("Ismail", "Kowalczyk"),
    ("Jorinde", "Osterloh"),
    ("Kai", "Schnürle"),
    ("Lea", "Amrhein"),
]

# Canonical values of specification 4.1, including tendencies.
NOTENWERTE_KLASSENARBEIT = [
    Decimal("0.7"),  # 1+
    Decimal("2.0"),  # 2
    Decimal("2.3"),  # 2-
    Decimal("3.0"),  # 3
    Decimal("4.3"),  # 4-
    Decimal("5.0"),  # 5
]

TABELLEN_DIE_LEER_SEIN_MUESSEN = ("schuljahr", "schueler", "note")

# Placeholder tints, cycled through. Invented data must be recognisable as
# invented at a glance.
FARBEN = [
    (206, 221, 240),
    (214, 235, 214),
    (243, 226, 205),
    (233, 213, 236),
    (208, 234, 236),
    (240, 226, 210),
]


def platzhalterbild(vorname: str, nachname: str, nummer: int) -> bytes:
    """A tinted square with the initials -- never a real photograph."""
    bild = Image.new("RGB", (512, 512), FARBEN[nummer % len(FARBEN)])
    stift = ImageDraw.Draw(bild)
    stift.text(
        (256, 256),
        f"{vorname[:1]}{nachname[:1]}".upper(),
        font=ImageFont.load_default(size=200),
        fill=(60, 70, 90),
        anchor="mm",
    )
    puffer = BytesIO()
    bild.save(puffer, format="PNG")
    # Through the same path as an upload, so the seed exercises it too.
    return verarbeite(puffer.getvalue())


class DatenbankNichtLeerError(RuntimeError):
    """Raised instead of touching a database that already holds data."""


def _pruefe_leer(session: Session) -> None:
    for tabelle in TABELLEN_DIE_LEER_SEIN_MUESSEN:
        anzahl = session.connection().exec_driver_sql(
            f"SELECT count(*) FROM {tabelle}"
        ).scalar()
        if anzahl:
            datensaetze = "1 Datensatz" if anzahl == 1 else f"{anzahl} Datensätze"
            raise DatenbankNichtLeerError(
                f"Die Datenbank enthält bereits Daten (Tabelle '{tabelle}': "
                f"{datensaetze}). Das Seed-Skript arbeitet ausschließlich gegen eine "
                "leere Entwicklungsdatenbank."
            )


def seed(engine: Engine) -> None:
    """Fill an empty, migrated database with development data."""
    session = create_session_factory(engine)()
    try:
        _pruefe_leer(session)

        schuljahr = Schuljahr(
            bezeichnung="2026/27",
            beginn=date(2026, 8, 1),
            ende=date(2027, 7, 31),
            ist_aktiv=True,
        )
        halbjahr_1 = Halbjahr(
            schuljahr=schuljahr, nummer=1, beginn=date(2026, 8, 1), ende=date(2027, 1, 31)
        )
        Halbjahr(
            schuljahr=schuljahr, nummer=2, beginn=date(2027, 2, 1), ende=date(2027, 7, 31)
        )

        for klassenbezeichnung, namen, faecher in (
            ("BFS 26a", NAMEN_BFS, ("Deutsch", "Wirtschaftslehre")),
            ("BS EHK 26", NAMEN_BS, ("Deutsch",)),
        ):
            klasse = Klasse(schuljahr=schuljahr, bezeichnung=klassenbezeichnung)
            schuelerliste = [
                Schueler(
                    klasse=klasse,
                    vorname=vorname,
                    nachname=nachname,
                    listennummer=nummer,
                    ist_aktiv=True,
                    foto=platzhalterbild(vorname, nachname, nummer),
                    foto_geaendert_am=utc_now(),
                )
                for nummer, (vorname, nachname) in enumerate(namen, start=1)
            ]

            for fach in faecher:
                kurs = Kurs(klasse=klasse, fach=fach)
                # All active pupils of the class join a new course by default.
                for schueler in schuelerliste:
                    Kursteilnahme(kurs=kurs, schueler=schueler, ist_aktiv=True)

                _seed_notengruppen(kurs, halbjahr_1, schuelerliste)

        # Added last, once the whole graph exists: everything else is reachable
        # from the school year and is cascaded in from there.
        session.add(schuljahr)
        session.commit()
    finally:
        session.close()


def _seed_notengruppen(kurs: Kurs, halbjahr: Halbjahr, schuelerliste: list[Schueler]) -> None:
    """Three groups weighted 50/30/20; the 'Tests' group stays empty on purpose.

    An empty group is the case the normalisation in 4.4 exists for, so the
    development data has to contain one.
    """
    klassenarbeiten = Notengruppe(
        kurs=kurs,
        halbjahr=halbjahr,
        bezeichnung="Klassenarbeiten",
        gewicht=Decimal("50"),
        reihenfolge=1,
    )
    Notengruppe(
        kurs=kurs,
        halbjahr=halbjahr,
        bezeichnung="Tests",
        gewicht=Decimal("30"),
        reihenfolge=2,
    )
    mitarbeit = Notengruppe(
        kurs=kurs,
        halbjahr=halbjahr,
        bezeichnung="Mitarbeit",
        gewicht=Decimal("20"),
        reihenfolge=3,
    )

    klassenarbeit = Leistung(
        notengruppe=klassenarbeiten,
        bezeichnung="1. Klassenarbeit",
        datum=date(2026, 9, 24),
        gewicht=Decimal("1.0"),
    )
    mitarbeitsnote = Leistung(
        notengruppe=mitarbeit,
        bezeichnung="Mitarbeit September",
        datum=date(2026, 9, 30),
        gewicht=Decimal("1.0"),
    )

    for schueler, notenwert in zip(schuelerliste, NOTENWERTE_KLASSENARBEIT):
        Note(
            leistung=klassenarbeit,
            schueler=schueler,
            notenwert=notenwert,
            status=NoteStatus.GEWERTET,
        )

    # Both non-standard statuses are present. A missing value is never stored
    # as 0 or 6; the 6.0 for nicht_erbracht comes from the grading module.
    for index, schueler in enumerate(schuelerliste):
        if index == 1:
            status, notenwert = NoteStatus.NICHT_GEWERTET, None
        elif index == 2:
            status, notenwert = NoteStatus.NICHT_ERBRACHT, None
        else:
            status, notenwert = NoteStatus.GEWERTET, Decimal("2.3")
        Note(
            leistung=mitarbeitsnote,
            schueler=schueler,
            notenwert=notenwert,
            status=status,
        )


def main() -> int:
    ziel = database_path()
    print(f"Seed-Daten werden geschrieben nach: {ziel}")
    engine = create_app_engine(database_url(ziel))
    try:
        seed(engine)
    except DatenbankNichtLeerError as fehler:
        print(f"Abgebrochen: {fehler}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print("Fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
