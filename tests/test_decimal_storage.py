"""Decimal values must survive storage unchanged.

A rounding error here would not be noticed until a wrong grade is on a report.
"""

from decimal import Decimal

import pytest

from app.db.models import Kurs, Note
from app.db.types import DecimalText


@pytest.mark.parametrize(
    "wert",
    [Decimal("0.7"), Decimal("2.30"), Decimal("2.5"), Decimal("100"), Decimal("33.33")],
)
def test_werte_bleiben_beim_binden_exakt(wert):
    assert DecimalText().process_bind_param(wert, None) == str(wert)


def test_none_bleibt_none():
    assert DecimalText().process_bind_param(None, None) is None
    assert DecimalText().process_result_value(None, None) is None


def test_ganze_zahlen_werden_angenommen():
    assert DecimalText().process_bind_param(50, None) == "50"


def test_fliesskomma_wird_abgewiesen():
    """float must not enter the database unnoticed."""
    with pytest.raises(TypeError):
        DecimalText().process_bind_param(2.3, None)


def test_wahrheitswert_wird_abgewiesen():
    with pytest.raises(TypeError):
        DecimalText().process_bind_param(True, None)


def test_zeichenkette_wird_abgewiesen():
    """'2,3' with a comma would silently become an invalid value."""
    with pytest.raises(TypeError):
        DecimalText().process_bind_param("2.3", None)


def test_rundreise_durch_die_datenbank_ist_verlustfrei(session, graph):
    kurs_id = graph.kurs.id
    graph.kurs.gewicht_halbjahr_1 = Decimal("40.00")
    graph.kurs.gewicht_halbjahr_2 = Decimal("60.00")
    session.commit()
    session.expunge_all()

    kurs = session.get(Kurs, kurs_id)
    assert kurs.gewicht_halbjahr_1 == Decimal("40.00")
    # Not just numerically equal: the scale as entered is preserved.
    assert str(kurs.gewicht_halbjahr_1) == "40.00"
    assert isinstance(kurs.gewicht_halbjahr_1, Decimal)


def test_notenwert_mit_tendenz_bleibt_erhalten(session, graph):
    note_id = graph.note.id
    graph.note.notenwert = Decimal("0.7")
    session.commit()
    session.expunge_all()

    note = session.get(Note, note_id)
    assert note.notenwert == Decimal("0.7")
    assert str(note.notenwert) == "0.7"
