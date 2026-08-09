"""Seed a development database with invented data.

Local development, tests and migration rehearsals run against this and never
against the productive file, which holds real names and photographs.

All names here are invented. Photos are not seeded: re-encoding images needs
Pillow, which arrives with the photo capture step (specification section 7);
``schueler.foto`` stays NULL until then.

Usage:

    NOTENVERWALTUNG_DB=data/dev.db .venv/bin/python scripts/seed_dev.py
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
    Notenschluessel,
    Schueler,
    Schuljahr,
)
from app.db.session import create_app_engine, create_session_factory  # noqa: E402
from app.enums import Eingabeart, NotenschluesselTyp, NoteStatus  # noqa: E402

# Specification 4.2, binding nationwide values.
IHK_SCHWELLEN = [
    {"ab_prozent": "92", "notenwert": "1.0"},
    {"ab_prozent": "81", "notenwert": "2.0"},
    {"ab_prozent": "67", "notenwert": "3.0"},
    {"ab_prozent": "50", "notenwert": "4.0"},
    {"ab_prozent": "30", "notenwert": "5.0"},
    {"ab_prozent": "0", "notenwert": "6.0"},
]

# Open point O-1: the real thresholds are unknown. This is the placeholder from
# 4.2 -- linear, pass mark at 50 %, whole grades only, no invented tendency
# boundaries. Flagged with ist_platzhalter so the interface can say so. Do not
# copy these numbers into the productive database.
RLP_PLATZHALTER_SCHWELLEN = [
    {"ab_prozent": "87.5", "notenwert": "1.0"},
    {"ab_prozent": "75", "notenwert": "2.0"},
    {"ab_prozent": "62.5", "notenwert": "3.0"},
    {"ab_prozent": "50", "notenwert": "4.0"},
    {"ab_prozent": "25", "notenwert": "5.0"},
    {"ab_prozent": "0", "notenwert": "6.0"},
]

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

TABELLEN_DIE_LEER_SEIN_MUESSEN = ("schuljahr", "schueler", "note", "notenschluessel")


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

        ihk = Notenschluessel(
            bezeichnung="IHK",
            typ=NotenschluesselTyp.IHK,
            schwellen=IHK_SCHWELLEN,
            ist_platzhalter=False,
        )
        rlp = Notenschluessel(
            bezeichnung="RLP-Standard (Platzhalter)",
            typ=NotenschluesselTyp.RLP_STANDARD,
            schwellen=RLP_PLATZHALTER_SCHWELLEN,
            ist_platzhalter=True,
        )

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
                )
                for nummer, (vorname, nachname) in enumerate(namen, start=1)
            ]

            for fach in faecher:
                kurs = Kurs(
                    klasse=klasse,
                    fach=fach,
                    notenschluessel=ihk if fach == "Wirtschaftslehre" else rlp,
                )
                # All active pupils of the class join a new course by default.
                for schueler in schuelerliste:
                    Kursteilnahme(kurs=kurs, schueler=schueler, ist_aktiv=True)

                _seed_notengruppen(kurs, halbjahr_1, schuelerliste)

        # Added last, once the whole graph exists: everything else is reachable
        # from the school year and is cascaded in from there.
        session.add_all([ihk, rlp, schuljahr])
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
        max_punkte=Decimal("50"),
        gewicht=Decimal("1.0"),
    )
    mitarbeitsnote = Leistung(
        notengruppe=mitarbeit,
        bezeichnung="Mitarbeit September",
        datum=date(2026, 9, 30),
        gewicht=Decimal("1.0"),
    )

    # Point entry: points and the resulting grade value are both stored (4.3).
    punkte_je_schueler = [
        Decimal("46"),  # 92 % -- exactly on the IHK threshold
        Decimal("45"),  # 90 %
        Decimal("38"),
        Decimal("31"),
        Decimal("24"),
        Decimal("12"),
    ]
    notenwerte = [
        Decimal("1.0"),
        Decimal("2.0"),
        Decimal("2.0"),
        Decimal("3.0"),
        Decimal("4.0"),
        Decimal("5.0"),
    ]
    for schueler, punkte, notenwert in zip(schuelerliste, punkte_je_schueler, notenwerte):
        Note(
            leistung=klassenarbeit,
            schueler=schueler,
            eingabeart=Eingabeart.PUNKTE,
            punkte=punkte,
            notenwert=notenwert,
            status=NoteStatus.GEWERTET,
        )

    # Direct grade entry, including both non-standard statuses. A missing value
    # is never stored as 0 or 6.
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
            eingabeart=Eingabeart.NOTE,
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
