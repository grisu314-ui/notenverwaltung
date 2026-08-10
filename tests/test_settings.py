"""Persisted settings: default in the code, row only where it was changed."""

import logging

from app.db.models import Einstellung
from app.enums import Namensanzeige, Sortierung
from app.services.settings import (
    SCHLUESSEL_SORTIERUNG,
    VORGABE,
    lies_einstellungen,
    setze_namensanzeige,
    setze_sortierung,
)


def test_ohne_zeile_gilt_die_vorgabe(session):
    assert lies_einstellungen(session) == VORGABE
    assert session.query(Einstellung).count() == 0


def test_sortierung_laesst_sich_umschalten_und_bleibt_erhalten(session):
    setze_sortierung(session, Sortierung.VORNAME)
    session.commit()
    session.expunge_all()

    assert lies_einstellungen(session).sortierung is Sortierung.VORNAME


def test_umschalten_legt_genau_eine_zeile_an(session):
    setze_sortierung(session, Sortierung.VORNAME)
    setze_sortierung(session, Sortierung.NACHNAME)
    session.commit()

    zeilen = session.query(Einstellung).filter_by(schluessel=SCHLUESSEL_SORTIERUNG).all()
    assert len(zeilen) == 1
    assert zeilen[0].wert == "nachname"


def test_namensanzeige_laesst_sich_umschalten(session):
    setze_namensanzeige(session, Namensanzeige.VORNAME_NACHNAME)
    session.commit()

    einstellungen = lies_einstellungen(session)
    assert einstellungen.namensanzeige is Namensanzeige.VORNAME_NACHNAME
    # The other setting keeps its value.
    assert einstellungen.sortierung is VORGABE.sortierung


def test_unbekannter_gespeicherter_wert_faellt_auf_die_vorgabe_zurueck(session, caplog):
    """Must not take the application down, but must not pass unnoticed either."""
    session.add(Einstellung(schluessel=SCHLUESSEL_SORTIERUNG, wert="geburtsdatum"))
    session.commit()

    with caplog.at_level(logging.WARNING):
        einstellungen = lies_einstellungen(session)

    assert einstellungen.sortierung is VORGABE.sortierung
    assert "geburtsdatum" in caplog.text
