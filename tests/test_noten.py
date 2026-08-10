"""Entering grades and the change history (specification 5.4, 3.2)."""

from datetime import date
from decimal import Decimal

import pytest

from app.db.models import Leistung, Note, NoteHistorie
from app.enums import HistorieAktion, NoteStatus
from app.services.fehler import Verwaltungsfehler
from app.services.noten import (
    lege_leistung_an,
    loesche_leistung,
    loesche_note,
    setze_note,
)
from app.services.verwaltung import setze_teilnahme


def historie(session) -> list[NoteHistorie]:
    return session.query(NoteHistorie).order_by(NoteHistorie.id).all()


def test_neue_note_wird_protokolliert(session, graph):
    setze_note(
        session, graph.leistung, graph.schueler_b, NoteStatus.GEWERTET, Decimal("3.0")
    )
    session.commit()

    eintraege = historie(session)
    assert len(eintraege) == 1
    assert eintraege[0].aktion == HistorieAktion.ANGELEGT
    assert eintraege[0].alter_notenwert is None
    assert eintraege[0].neuer_notenwert == Decimal("3.0")
    assert eintraege[0].schueler_id == graph.schueler_b.id


def test_aenderung_haelt_alten_und_neuen_wert_fest(session, graph):
    setze_note(
        session, graph.leistung, graph.schueler_a, NoteStatus.GEWERTET, Decimal("1.0")
    )
    session.commit()

    eintrag = historie(session)[-1]
    assert eintrag.aktion == HistorieAktion.GEAENDERT
    assert eintrag.alter_notenwert == Decimal("2.0")
    assert eintrag.neuer_notenwert == Decimal("1.0")


def test_statuswechsel_ohne_wertaenderung_wird_protokolliert(session, graph):
    """The result changes without the value changing."""
    setze_note(session, graph.leistung, graph.schueler_a, NoteStatus.NICHT_ERBRACHT)
    session.commit()

    eintrag = historie(session)[-1]
    assert eintrag.alter_status == NoteStatus.GEWERTET
    assert eintrag.neuer_status == NoteStatus.NICHT_ERBRACHT
    assert eintrag.alter_notenwert == Decimal("2.0")
    assert eintrag.neuer_notenwert is None


def test_unveraenderte_eingabe_erzeugt_keinen_eintrag(session, graph):
    setze_note(
        session, graph.leistung, graph.schueler_a, NoteStatus.GEWERTET, Decimal("2.0")
    )
    session.commit()

    assert historie(session) == []


def test_loeschen_wird_protokolliert_und_die_historie_ueberlebt(session, graph):
    note_id = graph.note.id
    loesche_note(session, graph.leistung, graph.schueler_a)
    session.commit()

    eintraege = historie(session)
    assert len(eintraege) == 1
    assert eintraege[0].aktion == HistorieAktion.GELOESCHT
    assert eintraege[0].alter_notenwert == Decimal("2.0")
    assert eintraege[0].neuer_notenwert is None
    assert eintraege[0].note_id == note_id
    assert session.get(Note, note_id) is None


def test_loeschen_ohne_note_tut_nichts(session, graph):
    loesche_note(session, graph.leistung, graph.schueler_b)
    session.commit()
    assert historie(session) == []


def test_ohne_aktive_teilnahme_keine_note(session, graph):
    """The last of the service rules the schema cannot enforce."""
    setze_teilnahme(session, graph.kurs, graph.schueler_b, False)
    session.commit()

    with pytest.raises(Verwaltungsfehler) as fehler:
        setze_note(
            session,
            graph.leistung,
            graph.schueler_b,
            NoteStatus.GEWERTET,
            Decimal("2.0"),
        )
    assert "nicht (mehr) teil" in str(fehler.value)


def test_wert_ausserhalb_der_notentabelle_wird_abgewiesen(session, graph):
    with pytest.raises(Verwaltungsfehler):
        setze_note(
            session,
            graph.leistung,
            graph.schueler_b,
            NoteStatus.GEWERTET,
            Decimal("2.5"),
        )
    session.rollback()
    assert session.query(Note).count() == 1


def test_gewertet_ohne_wert_wird_abgewiesen(session, graph):
    with pytest.raises(Verwaltungsfehler):
        setze_note(session, graph.leistung, graph.schueler_b, NoteStatus.GEWERTET, None)


def test_nicht_erbracht_speichert_keinen_wert(session, graph):
    """The 6.0 comes from the status in the grading module, never from the row."""
    note = setze_note(
        session,
        graph.leistung,
        graph.schueler_b,
        NoteStatus.NICHT_ERBRACHT,
        Decimal("2.0"),
    )
    session.commit()

    assert note.notenwert is None
    assert note.status == NoteStatus.NICHT_ERBRACHT


# --------------------------------------------------------------------------
# Leistungen
# --------------------------------------------------------------------------


def test_leistung_anlegen(session, graph):
    leistung = lege_leistung_an(
        session, graph.notengruppe, "2. Klassenarbeit", date(2026, 11, 4), Decimal("2")
    )
    session.commit()

    assert leistung.id is not None
    assert session.query(Leistung).count() == 2


@pytest.mark.parametrize("gewicht", ["0", "-1"])
def test_leistung_mit_unzulaessigem_gewicht(session, graph, gewicht):
    with pytest.raises(Verwaltungsfehler):
        lege_leistung_an(
            session,
            graph.notengruppe,
            "2. Klassenarbeit",
            date(2026, 11, 4),
            Decimal(gewicht),
        )


def test_leistung_ohne_bezeichnung(session, graph):
    with pytest.raises(Verwaltungsfehler):
        lege_leistung_an(
            session, graph.notengruppe, "   ", date(2026, 11, 4), Decimal("1")
        )


def test_leistung_mit_noten_laesst_sich_nicht_loeschen(session, graph):
    with pytest.raises(Verwaltungsfehler) as fehler:
        loesche_leistung(session, graph.leistung)
    assert "Noten daran hängen" in str(fehler.value)


def test_leere_leistung_laesst_sich_loeschen(session, graph):
    leer = lege_leistung_an(
        session, graph.notengruppe, "Kurztest", date(2026, 10, 1), Decimal("1")
    )
    session.commit()

    loesche_leistung(session, leer)
    session.commit()
    assert session.query(Leistung).count() == 1
