"""The seed script is the only data development ever runs against."""

import pytest

from app.db.models import Note, Notenschluessel, Schueler
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
    assert geseedete_session.query(Notenschluessel).count() == 2


def test_seed_enthaelt_beide_sonderstatus(geseedete_session):
    """The grading module needs both cases in the development data."""
    for status in (NoteStatus.NICHT_GEWERTET, NoteStatus.NICHT_ERBRACHT):
        noten = geseedete_session.query(Note).filter_by(status=status).all()
        assert noten, status
        for note in noten:
            assert note.notenwert is None


def test_platzhalterschluessel_ist_als_solcher_gekennzeichnet(geseedete_session):
    """Open point O-1: the RLP thresholds are guessed and must say so."""
    rlp = (
        geseedete_session.query(Notenschluessel)
        .filter(Notenschluessel.ist_platzhalter.is_(True))
        .one()
    )
    assert "Platzhalter" in rlp.bezeichnung

    ihk = (
        geseedete_session.query(Notenschluessel)
        .filter(Notenschluessel.ist_platzhalter.is_(False))
        .one()
    )
    assert ihk.bezeichnung == "IHK"


def test_seed_verweigert_eine_nicht_leere_datenbank(engine):
    seed(engine)
    with pytest.raises(DatenbankNichtLeerError):
        seed(engine)
