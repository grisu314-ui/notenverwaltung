"""Test fixtures.

Every test gets its own database, built by running the Alembic migration.
``create_all()`` is never used, not even here: the schema under test is the
schema the migration produces, otherwise the two can drift apart unnoticed.
"""

import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from pathlib import Path

from app.db.models import (
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
from app.db.session import create_app_engine, create_session_factory
from app.enums import NoteStatus

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def pytest_configure(config):
    if os.environ.get("NOTENVERWALTUNG_DB"):
        raise pytest.UsageError(
            "NOTENVERWALTUNG_DB ist gesetzt. Tests laufen ausschließlich gegen eine "
            "temporäre Datenbank, nie gegen einen konfigurierten Datenbestand."
        )


def _alembic_config(url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture
def db_url(tmp_path) -> str:
    """URL of a fresh database migrated to head."""
    url = f"sqlite+pysqlite:///{tmp_path / 'notenverwaltung-test.db'}"
    command.upgrade(_alembic_config(url), "head")
    return url


@pytest.fixture
def alembic_cfg(db_url) -> Config:
    return _alembic_config(db_url)


@pytest.fixture
def engine(db_url):
    engine = create_app_engine(db_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(engine):
    session = create_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(session):
    """Test client bound to the temporary database of the session fixture."""
    from fastapi.testclient import TestClient

    from app.web.app import app
    from app.web.dependencies import datenbanksitzung

    app.dependency_overrides[datenbanksitzung] = lambda: session
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def graph(session) -> SimpleNamespace:
    """A minimal but complete object graph: school year down to a single grade."""
    schuljahr = Schuljahr(
        bezeichnung="2026/27",
        beginn=date(2026, 8, 1),
        ende=date(2027, 7, 31),
        ist_aktiv=True,
    )
    halbjahr_1 = Halbjahr(
        schuljahr=schuljahr, nummer=1, beginn=date(2026, 8, 1), ende=date(2027, 1, 31)
    )
    halbjahr_2 = Halbjahr(
        schuljahr=schuljahr, nummer=2, beginn=date(2027, 2, 1), ende=date(2027, 7, 31)
    )
    klasse = Klasse(schuljahr=schuljahr, bezeichnung="BFS 26a")
    schueler_a = Schueler(klasse=klasse, vorname="Änne", nachname="Öztürk")
    schueler_b = Schueler(klasse=klasse, vorname="Bernd", nachname="Straßer")
    kurs = Kurs(klasse=klasse, fach="Deutsch")
    teilnahme_a = Kursteilnahme(kurs=kurs, schueler=schueler_a)
    teilnahme_b = Kursteilnahme(kurs=kurs, schueler=schueler_b)
    notengruppe = Notengruppe(
        kurs=kurs,
        halbjahr=halbjahr_1,
        bezeichnung="Klassenarbeiten",
        gewicht=Decimal("50"),
        reihenfolge=1,
    )
    leistung = Leistung(
        notengruppe=notengruppe,
        bezeichnung="1. Klassenarbeit",
        datum=date(2026, 9, 15),
        gewicht=Decimal("1.0"),
    )
    note = Note(
        leistung=leistung,
        schueler=schueler_a,
        notenwert=Decimal("2.0"),
        status=NoteStatus.GEWERTET,
    )

    session.add(schuljahr)
    session.commit()

    return SimpleNamespace(
        schuljahr=schuljahr,
        halbjahr_1=halbjahr_1,
        halbjahr_2=halbjahr_2,
        klasse=klasse,
        schueler_a=schueler_a,
        schueler_b=schueler_b,
        kurs=kurs,
        teilnahme_a=teilnahme_a,
        teilnahme_b=teilnahme_b,
        notengruppe=notengruppe,
        leistung=leistung,
        note=note,
    )
