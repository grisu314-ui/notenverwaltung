"""Specification 4.6 -- the binding test cases, plus the edge cases it omits.

T-5, T-6 and T-10 are absent: they test point entry and a change of grading
key, neither of which is built (see README.md).
"""

from decimal import Decimal

import pytest

from app.enums import NoteStatus
from app.grading.berechnung import (
    Einzelnote,
    FehlenderNotenwertError,
    Notengruppe,
    UngueltigeGewichtungError,
    halbjahresnote,
    jahresnote,
)
from app.grading.notenwert import UngueltigeNoteError, als_dezimalanzeige


def note(wert: str, gewicht: str = "1.0") -> Einzelnote:
    return Einzelnote(
        status=NoteStatus.GEWERTET, notenwert=Decimal(wert), gewicht=Decimal(gewicht)
    )


# --------------------------------------------------------------------------
# Binding test cases of 4.6
# --------------------------------------------------------------------------


def test_t1_zwei_gruppen_mit_gleichem_gewicht():
    """(50*2 + 50*3 + 50*1) / 150 = 2.0 -> Note 2."""
    ergebnis = halbjahresnote(
        [
            Notengruppe(gewicht=Decimal("50"), noten=(note("2.0"), note("3.0"))),
            Notengruppe(gewicht=Decimal("50"), noten=(note("1.0"),)),
        ]
    )
    assert ergebnis.wert == Decimal("2.0")
    assert ergebnis.ganze_note == 2


def test_t2_leere_notengruppe_aendert_das_ergebnis_nicht():
    """The empty group holds no grade, so it never reaches the denominator."""
    ohne = halbjahresnote(
        [
            Notengruppe(gewicht=Decimal("50"), noten=(note("2.0"), note("3.0"))),
            Notengruppe(gewicht=Decimal("50"), noten=(note("1.0"),)),
        ]
    )
    mit = halbjahresnote(
        [
            Notengruppe(gewicht=Decimal("50"), noten=(note("2.0"), note("3.0"))),
            Notengruppe(gewicht=Decimal("30")),
            Notengruppe(gewicht=Decimal("50"), noten=(note("1.0"),)),
        ]
    )
    assert mit == ohne


def test_t3_nicht_gewertete_note_aendert_das_ergebnis_nicht():
    ohne = halbjahresnote([Notengruppe(gewicht=Decimal("50"), noten=(note("2.0"),))])
    mit = halbjahresnote(
        [
            Notengruppe(
                gewicht=Decimal("50"),
                noten=(
                    note("2.0"),
                    Einzelnote(status=NoteStatus.NICHT_GEWERTET, gewicht=Decimal("1.0")),
                ),
            )
        ]
    )
    assert mit == ohne
    assert mit.wert == Decimal("2.0")


def test_t4_nicht_erbrachte_note_geht_als_sechs_ein():
    ergebnis = halbjahresnote(
        [
            Notengruppe(
                gewicht=Decimal("50"),
                noten=(
                    note("2.0"),
                    Einzelnote(status=NoteStatus.NICHT_ERBRACHT, gewicht=Decimal("1.0")),
                ),
            )
        ]
    )
    assert ergebnis.wert == Decimal("4.0")  # (2.0 + 6.0) / 2
    assert ergebnis.ganze_note == 4


def test_t7_kurs_ohne_jede_note_liefert_kein_ergebnis():
    """No calculation, no division by zero, empty display."""
    assert halbjahresnote([]) is None
    assert halbjahresnote([Notengruppe(gewicht=Decimal("50"))]) is None


def test_t8_jahresnote_mit_gewichtung_vierzig_sechzig():
    ergebnis = jahresnote(
        Decimal("2.0"), Decimal("3.0"), Decimal("40"), Decimal("60")
    )
    assert ergebnis.wert == Decimal("2.6")
    assert ergebnis.ganze_note == 3


def test_t9_ueberschreibung_laesst_den_berechneten_wert_unberuehrt():
    """The calculated value is never overwritten, only overlaid (3.1).

    The display "2 (berechnet 2,6)" is assembled in the view layer; here the
    two parts it needs are checked.
    """
    berechnet = jahresnote(Decimal("2.0"), Decimal("3.0"), Decimal("40"), Decimal("60"))
    festgesetzt = 2

    assert als_dezimalanzeige(berechnet.wert) == "2,6"
    assert berechnet.ganze_note == 3
    assert festgesetzt != berechnet.ganze_note  # the override differs and wins


# --------------------------------------------------------------------------
# Edge cases 4.6 does not cover
# --------------------------------------------------------------------------


def test_gruppengewichte_wirken_weiterhin():
    """Same grades as T-1 but 70/30 -- the result has to move."""
    ergebnis = halbjahresnote(
        [
            Notengruppe(gewicht=Decimal("70"), noten=(note("2.0"), note("3.0"))),
            Notengruppe(gewicht=Decimal("30"), noten=(note("1.0"),)),
        ]
    )
    # (70*2 + 70*3 + 30*1) / 170 = 380/170 = 2.2352...
    assert ergebnis.wert == Decimal("2.2")
    assert ergebnis.ganze_note == 2


def test_mehr_noten_in_einer_gruppe_wiegen_schwerer():
    """The operator's decision against the two-stage rule of 4.4.

    Under 4.4 both variants would give the same result, because the group
    weight would be independent of the number of grades.
    """
    eine = halbjahresnote(
        [
            Notengruppe(gewicht=Decimal("50"), noten=(note("1.0"),)),
            Notengruppe(gewicht=Decimal("50"), noten=(note("4.0"),)),
        ]
    )
    drei = halbjahresnote(
        [
            Notengruppe(
                gewicht=Decimal("50"), noten=(note("1.0"), note("1.0"), note("1.0"))
            ),
            Notengruppe(gewicht=Decimal("50"), noten=(note("4.0"),)),
        ]
    )
    assert eine.wert == Decimal("2.5")
    # (3*1.0 + 4.0) / 4 = 1.75, a tie, and a tie goes to the better grade
    assert drei.wert == Decimal("1.7")


def test_leistungsgewicht_wirkt_innerhalb_der_gruppe():
    """A Klassenarbeit weighted twice as heavily as a test in the same group."""
    ergebnis = halbjahresnote(
        [
            Notengruppe(
                gewicht=Decimal("50"),
                noten=(note("1.0", gewicht="2.0"), note("4.0", gewicht="1.0")),
            )
        ]
    )
    assert ergebnis.wert == Decimal("2.0")  # (2*1 + 1*4) / 3 = 2.0


def test_gruppe_nur_mit_nicht_erbracht_geht_mit_sechs_ein():
    ergebnis = halbjahresnote(
        [
            Notengruppe(gewicht=Decimal("50"), noten=(note("2.0"),)),
            Notengruppe(
                gewicht=Decimal("50"),
                noten=(Einzelnote(status=NoteStatus.NICHT_ERBRACHT),),
            ),
        ]
    )
    assert ergebnis.wert == Decimal("4.0")


def test_gruppe_nur_mit_nicht_gewertet_faellt_weg():
    ergebnis = halbjahresnote(
        [
            Notengruppe(gewicht=Decimal("50"), noten=(note("2.0"),)),
            Notengruppe(
                gewicht=Decimal("30"),
                noten=(Einzelnote(status=NoteStatus.NICHT_GEWERTET),),
            ),
        ]
    )
    assert ergebnis.wert == Decimal("2.0")


def test_ausschliesslich_nicht_gewertete_noten_liefern_kein_ergebnis():
    assert (
        halbjahresnote(
            [
                Notengruppe(
                    gewicht=Decimal("50"),
                    noten=(Einzelnote(status=NoteStatus.NICHT_GEWERTET),),
                )
            ]
        )
        is None
    )


def test_lauter_bestnoten_ergeben_die_note_eins():
    """0.7 must never round down to a 0."""
    ergebnis = halbjahresnote(
        [Notengruppe(gewicht=Decimal("50"), noten=(note("0.7"), note("0.7")))]
    )
    assert ergebnis.wert == Decimal("0.7")
    assert ergebnis.ganze_note == 1


def test_lauter_sechsen_ergeben_die_note_sechs():
    ergebnis = halbjahresnote(
        [Notengruppe(gewicht=Decimal("50"), noten=(note("6.0"), note("6.0")))]
    )
    assert ergebnis.ganze_note == 6


def test_gewertete_note_ohne_wert_wird_abgewiesen():
    """Never silently treated as 0 or 6."""
    with pytest.raises(FehlenderNotenwertError):
        Einzelnote(status=NoteStatus.GEWERTET, notenwert=None)


def test_wert_ausserhalb_der_notentabelle_wird_abgewiesen():
    with pytest.raises(UngueltigeNoteError):
        Einzelnote(status=NoteStatus.GEWERTET, notenwert=Decimal("2.5"))


@pytest.mark.parametrize("gewicht", ["0", "-1"])
def test_unzulaessige_gewichte_werden_abgewiesen(gewicht):
    with pytest.raises(UngueltigeGewichtungError):
        Notengruppe(gewicht=Decimal(gewicht), noten=(note("2.0"),))
    with pytest.raises(UngueltigeGewichtungError):
        note("2.0", gewicht=gewicht)


# --------------------------------------------------------------------------
# Jahresnote
# --------------------------------------------------------------------------


def test_jahresnote_fuenfzig_fuenfzig_rundet_zugunsten_des_schuelers():
    """2.5 gives a 2, not a 3 -- the operator's rounding rule."""
    ergebnis = jahresnote(Decimal("2.0"), Decimal("3.0"), Decimal("50"), Decimal("50"))
    assert ergebnis.wert == Decimal("2.5")
    assert ergebnis.ganze_note == 2


@pytest.mark.parametrize(
    ("halbjahr_1", "halbjahr_2"),
    [(Decimal("2.0"), None), (None, Decimal("3.0")), (None, None)],
)
def test_keine_jahresnote_solange_ein_halbjahr_fehlt(halbjahr_1, halbjahr_2):
    """The practical case is January: the second term is still empty."""
    assert (
        jahresnote(halbjahr_1, halbjahr_2, Decimal("50"), Decimal("50")) is None
    )


def test_jahresnote_nimmt_auch_berechnete_zwischenwerte():
    """A term that has not been fixed contributes its calculated value."""
    ergebnis = jahresnote(
        Decimal("2.4"), Decimal("3.0"), Decimal("50"), Decimal("50")
    )
    assert ergebnis.wert == Decimal("2.7")  # 2.7 exactly
    assert ergebnis.ganze_note == 3
