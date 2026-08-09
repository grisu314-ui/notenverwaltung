"""The seed script is the only data development ever runs against."""

from decimal import Decimal

import pytest

from app.db.models import Note, Schueler
from app.db.session import create_session_factory
from app.enums import NoteStatus
from scripts.seed_dev import DatenbankNichtLeerError, seed


@pytest.fixture
def geseedete_session(engine):
    seed(engine)
    session = create_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()


def test_seed_legt_daten_an(geseedete_session):
    assert geseedete_session.query(Schueler).count() == 12


def test_seed_enthaelt_beide_sonderstatus(geseedete_session):
    """The grading module needs both cases in the development data."""
    for status in (NoteStatus.NICHT_GEWERTET, NoteStatus.NICHT_ERBRACHT):
        noten = geseedete_session.query(Note).filter_by(status=status).all()
        assert noten, status
        for note in noten:
            assert note.notenwert is None


def test_seed_enthaelt_tendenznoten(geseedete_session):
    """Grades are entered as 1+ ... 6; the canonical value of "1+" is 0.7."""
    notenwerte = {
        note.notenwert for note in geseedete_session.query(Note).all() if note.notenwert
    }
    assert Decimal("0.7") in notenwerte
    assert Decimal("2.3") in notenwerte


def test_seed_verweigert_eine_nicht_leere_datenbank(engine):
    seed(engine)
    with pytest.raises(DatenbankNichtLeerError):
        seed(engine)
