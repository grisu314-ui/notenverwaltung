"""Specification 6: German sorting. ASCII order is not acceptable."""

import pytest

from app.enums import Namensanzeige, Sortierung
from app.services.sorting import anzeigename, namensschluessel, vereinfacht


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("Äpfel", "apfel"),
        ("Öztürk", "ozturk"),
        ("Übelacker", "ubelacker"),
        ("Straßer", "strasser"),
        ("Aydın", "aydin"),
        ("MÜLLER", "muller"),
        ("Zäpfel", "zapfel"),
    ],
)
def test_sortierform_ordnet_umlaute_wie_grundbuchstaben_ein(text, erwartet):
    assert vereinfacht(text) == erwartet


def test_umlaute_landen_nicht_am_ende():
    """The failure ASCII sorting produces: Öztürk after Zäpfel."""
    namen = ["Zäpfel", "Öztürk", "Achenbach", "Übelacker", "Straßer"]
    sortiert = sorted(namen, key=vereinfacht)
    assert sortiert == ["Achenbach", "Öztürk", "Straßer", "Übelacker", "Zäpfel"]


def test_scharfes_s_sortiert_wie_ss():
    assert vereinfacht("Straßer") == vereinfacht("Strasser")


def test_sortierung_nach_nachname():
    schueler = [("Bernd", "Straßer"), ("Änne", "Öztürk"), ("Cem", "Aydın")]
    sortiert = sorted(
        schueler, key=lambda s: namensschluessel(s[0], s[1], Sortierung.NACHNAME)
    )
    assert [nachname for _, nachname in sortiert] == ["Aydın", "Öztürk", "Straßer"]


def test_sortierung_nach_vorname():
    schueler = [("Bernd", "Straßer"), ("Änne", "Öztürk"), ("Cem", "Aydın")]
    sortiert = sorted(
        schueler, key=lambda s: namensschluessel(s[0], s[1], Sortierung.VORNAME)
    )
    assert [vorname for vorname, _ in sortiert] == ["Änne", "Bernd", "Cem"]


def test_gleiche_sortierform_bleibt_stabil_geordnet():
    """Müller and Muller must not depend on the order they were read in."""
    a = namensschluessel("Anna", "Müller", Sortierung.NACHNAME)
    b = namensschluessel("Anna", "Muller", Sortierung.NACHNAME)
    assert a != b
    assert sorted([a, b])[0] == b  # "Muller" < "Müller" as a tiebreak


def test_namensanzeige():
    assert anzeigename("Änne", "Öztürk", Namensanzeige.VORNAME_NACHNAME) == "Änne Öztürk"
    assert (
        anzeigename("Änne", "Öztürk", Namensanzeige.NACHNAME_VORNAME) == "Öztürk, Änne"
    )
