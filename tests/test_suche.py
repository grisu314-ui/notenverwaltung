"""Search across the whole database (specification 5.2)."""

from datetime import date

import pytest

from app.db.models import Klasse, Schueler, Schuljahr
from app.services.suche import suche_schueler


@pytest.fixture
def bestand(session, graph):
    """A second school year with a former pupil, to search across years."""
    altes_jahr = Schuljahr(
        bezeichnung="2025/26",
        beginn=date(2025, 8, 1),
        ende=date(2026, 7, 31),
        ist_aktiv=False,
    )
    alte_klasse = Klasse(schuljahr=altes_jahr, bezeichnung="BFS 25a")
    ehemalig = Schueler(
        klasse=alte_klasse, vorname="Jorinde", nachname="Osterloh", ist_aktiv=False
    )
    session.add(altes_jahr)
    session.commit()
    return ehemalig


def namen(treffer) -> set[str]:
    return {schueler.nachname for schueler in treffer}


def test_findet_ueber_den_nachnamen(session, graph):
    assert namen(suche_schueler(session, "Öztürk")) == {"Öztürk"}


def test_findet_ueber_den_vornamen(session, graph):
    assert namen(suche_schueler(session, "Bernd")) == {"Straßer"}


def test_findet_ueber_einen_teilstring(session, graph):
    assert namen(suche_schueler(session, "traß")) == {"Straßer"}


def test_umlaute_muessen_nicht_getippt_werden(session, graph):
    """LIKE could not do this: SQLite ignores case for ASCII only."""
    assert namen(suche_schueler(session, "ozturk")) == {"Öztürk"}


def test_scharfes_s_darf_als_ss_getippt_werden(session, graph):
    assert namen(suche_schueler(session, "strasser")) == {"Straßer"}


def test_grossschreibung_egal(session, graph):
    assert namen(suche_schueler(session, "ÄNNE")) == {"Öztürk"}


def test_findet_ueber_vor_und_nachname_zusammen(session, graph):
    assert namen(suche_schueler(session, "änne öz")) == {"Öztürk"}
    assert namen(suche_schueler(session, "öztürk änne")) == {"Öztürk"}


def test_sucht_ueber_schuljahre_hinweg_und_findet_ehemalige(session, bestand):
    treffer = suche_schueler(session, "osterloh")
    assert namen(treffer) == {"Osterloh"}
    assert treffer[0].ist_aktiv is False
    assert treffer[0].klasse.schuljahr.bezeichnung == "2025/26"


@pytest.mark.parametrize("begriff", ["", "   "])
def test_leere_eingabe_liefert_nichts_statt_allem(session, graph, begriff):
    assert suche_schueler(session, begriff) == []


def test_ohne_treffer_kommt_eine_leere_liste(session, graph):
    assert suche_schueler(session, "Xylophon") == []
