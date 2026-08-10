"""The grade table of 4.1 and the rounding rules."""

from decimal import Decimal

import pytest

from app.grading.notenwert import (
    NOTENWERTE,
    UngueltigeNoteError,
    als_anzeige,
    als_dezimalanzeige,
    aus_anzeige,
    ganze_notenstufe,
    ist_gueltiger_notenwert,
    runde_auf_anzeige,
)


def test_die_tabelle_hat_sechzehn_werte():
    """1+ to 5- with tendencies, plus the 6, which has none."""
    assert len(NOTENWERTE) == 16
    assert NOTENWERTE[0] == Decimal("0.7")
    assert NOTENWERTE[-1] == Decimal("6.0")


@pytest.mark.parametrize("wert", NOTENWERTE)
def test_hin_und_rueckweg_sind_verlustfrei(wert):
    assert aus_anzeige(als_anzeige(wert)) == wert


def test_null_komma_sieben_wird_als_eins_plus_angezeigt():
    """Explicitly required by 4.1: never "0,7"."""
    assert als_anzeige(Decimal("0.7")) == "1+"


def test_anzeige_ist_unabhaengig_von_der_stellenzahl():
    assert als_anzeige(Decimal("1.00")) == "1"


def test_bindestrich_wird_als_minuszeichen_akzeptiert():
    """That is what a keyboard produces."""
    assert aus_anzeige("1-") == aus_anzeige("1−") == Decimal("1.3")


def test_leerzeichen_stoeren_nicht():
    assert aus_anzeige(" 2+ ") == Decimal("1.7")


@pytest.mark.parametrize("text", ["7", "0", "6+", "6−", "zwei", ""])
def test_ungueltige_anzeige_wird_abgewiesen(text):
    """The 6 has no tendencies, and there is no 0 and no 7."""
    with pytest.raises(UngueltigeNoteError):
        aus_anzeige(text)


def test_zwischenwerte_sind_keine_gueltigen_noten():
    assert ist_gueltiger_notenwert(Decimal("2.0")) is True
    assert ist_gueltiger_notenwert(Decimal("2.5")) is False


def test_ungueltiger_wert_kann_nicht_angezeigt_werden():
    with pytest.raises(UngueltigeNoteError):
        als_anzeige(Decimal("2.5"))


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        ("2.44", "2.4"),
        ("2.46", "2.5"),
        ("2.2352941", "2.2"),
        ("1.75", "1.7"),  # tie -> better grade
        ("2.25", "2.2"),  # tie -> better grade
        ("2.0", "2.0"),
    ],
)
def test_rundung_auf_eine_stelle(roh, erwartet):
    assert runde_auf_anzeige(Decimal(roh)) == Decimal(erwartet)


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        ("2.49", 2),
        ("2.50", 2),  # tie -> better grade; 4.4 would give 3 here
        ("2.54", 2),
        ("2.56", 3),
        ("1.5", 1),
        ("0.7", 1),  # all grades 1+ must not produce a 0
        ("6.0", 6),
        ("5.9", 6),
    ],
)
def test_ganze_notenstufe(roh, erwartet):
    assert ganze_notenstufe(Decimal(roh)) == erwartet


@pytest.mark.parametrize("roh", ["0.6", "6.1", "0"])
def test_werte_ausserhalb_des_notenbereichs_werden_abgewiesen(roh):
    """A mean of valid grades can never leave the range; such a value is a defect."""
    with pytest.raises(UngueltigeNoteError):
        ganze_notenstufe(Decimal(roh))


def test_dezimalanzeige_verwendet_komma():
    assert als_dezimalanzeige(Decimal("2.6")) == "2,6"
    assert als_dezimalanzeige(Decimal("2.2352941")) == "2,2"
    assert als_dezimalanzeige(Decimal("2")) == "2,0"
