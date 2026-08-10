"""Constraint violations have to arrive as readable German sentences."""

import logging
from datetime import date

import pytest
from sqlalchemy import CheckConstraint, PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.models import Halbjahr, Klasse, Schueler
from app.services.fehler import (
    ALLGEMEINE_MELDUNG,
    ART_CHECK,
    ART_UNIQUE,
    MELDUNGEN,
    MELDUNG_FREMDSCHLUESSEL,
    Verwaltungsfehler,
    meldung_zu,
    uebersetzte_datenbankfehler,
)


def _ausgeloest(session, machen) -> IntegrityError:
    with pytest.raises(IntegrityError) as fehler:
        machen()
        session.flush()
    session.rollback()
    return fehler.value


def test_mehrspaltige_eindeutigkeit(session, graph):
    fehler = _ausgeloest(
        session,
        lambda: session.add(
            Klasse(schuljahr_id=graph.schuljahr.id, bezeichnung="BFS 26a")
        ),
    )
    assert meldung_zu(fehler) == (
        "Diese Klassenbezeichnung gibt es in diesem Schuljahr bereits."
    )


def test_benannter_check(session, graph):
    fehler = _ausgeloest(
        session,
        lambda: session.add(
            Halbjahr(
                schuljahr_id=graph.schuljahr.id,
                nummer=3,
                beginn=date(2026, 8, 1),
                ende=date(2027, 1, 31),
            )
        ),
    )
    assert meldung_zu(fehler) == "Ein Halbjahr hat die Nummer 1 oder 2."


def test_fremdschluessel(session, graph):
    fehler = _ausgeloest(
        session,
        lambda: session.add(Schueler(vorname="A", nachname="B", klasse_id=999999)),
    )
    assert meldung_zu(fehler) == MELDUNG_FREMDSCHLUESSEL


def test_nicht_null_nennt_das_feld(session, graph):
    fehler = _ausgeloest(
        session,
        lambda: session.add(Klasse(schuljahr_id=graph.schuljahr.id, bezeichnung=None)),
    )
    assert "bezeichnung" in meldung_zu(fehler)


def test_unbekannte_regel_wird_protokolliert(caplog):
    class Erfunden(Exception):
        pass

    fehler = IntegrityError("stmt", {}, Erfunden("etwas ganz anderes"))
    with caplog.at_level(logging.WARNING):
        assert meldung_zu(fehler) == ALLGEMEINE_MELDUNG
    assert "Unbekannte Integritätsverletzung" in caplog.text


def test_kontextmanager_setzt_zurueck_und_uebersetzt(session, graph):
    with pytest.raises(Verwaltungsfehler) as fehler:
        with uebersetzte_datenbankfehler(session):
            session.add(
                Klasse(schuljahr_id=graph.schuljahr.id, bezeichnung="BFS 26a")
            )
            session.commit()

    assert "bereits" in str(fehler.value)
    # The session is usable again after the rollback.
    assert session.query(Klasse).count() == 1


def test_fuer_jede_regel_gibt_es_eine_meldung():
    """Guards against drift: a new constraint without a message fails here."""
    fehlend = []
    for tabelle in Base.metadata.tables.values():
        for constraint in tabelle.constraints:
            if isinstance(constraint, PrimaryKeyConstraint):
                continue
            if isinstance(constraint, UniqueConstraint):
                schluessel = ", ".join(
                    f"{tabelle.name}.{spalte.name}" for spalte in constraint.columns
                )
                if (ART_UNIQUE, schluessel) not in MELDUNGEN:
                    fehlend.append((ART_UNIQUE, schluessel))
            elif isinstance(constraint, CheckConstraint):
                if (ART_CHECK, constraint.name) not in MELDUNGEN:
                    fehlend.append((ART_CHECK, constraint.name))
    assert fehlend == []
