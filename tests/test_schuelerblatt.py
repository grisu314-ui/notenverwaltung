"""The grade sheet of one pupil (specification 5.2), including test case T-9."""

from datetime import date
from decimal import Decimal

from app.db.models import Leistung, Note, Notengruppe, Notenueberschreibung
from app.enums import Bezugszeitraum, NoteStatus, UeberschreibungQuelle
from app.services.schuelerblatt import OHNE_WERT, blatt, notenanzeige
from app.services.verwaltung import setze_teilnahme


def _leistung(session, notengruppe, bezeichnung, datum):
    leistung = Leistung(
        notengruppe=notengruppe,
        bezeichnung=bezeichnung,
        datum=datum,
        gewicht=Decimal("1.0"),
    )
    session.add(leistung)
    return leistung


def _note(session, leistung, schueler, wert, status=NoteStatus.GEWERTET):
    note = Note(
        leistung=leistung,
        schueler=schueler,
        notenwert=None if wert is None else Decimal(wert),
        status=status,
    )
    session.add(note)
    return note


def test_blatt_gruppiert_nach_kurs_und_notengruppe(session, graph):
    ergebnis = blatt(session, graph.schueler_a)

    assert len(ergebnis.kurse) == 1
    kursblock = ergebnis.kurse[0]
    assert kursblock.kurs.fach == "Deutsch"
    assert [hj.halbjahr.nummer for hj in kursblock.halbjahre] == [1, 2]

    erstes = kursblock.halbjahre[0]
    assert [g.notengruppe.bezeichnung for g in erstes.gruppen] == ["Klassenarbeiten"]
    assert erstes.gruppen[0].eintraege[0].note is not None


def test_leistungen_stehen_chronologisch(session, graph):
    spaet = _leistung(session, graph.notengruppe, "3. Arbeit", date(2026, 12, 1))
    frueh = _leistung(session, graph.notengruppe, "0. Arbeit", date(2026, 8, 15))
    _note(session, spaet, graph.schueler_a, "3.0")
    _note(session, frueh, graph.schueler_a, "1.0")
    session.commit()

    gruppe = blatt(session, graph.schueler_a).kurse[0].halbjahre[0].gruppen[0]
    assert [e.leistung.bezeichnung for e in gruppe.eintraege] == [
        "0. Arbeit",
        "1. Klassenarbeit",
        "3. Arbeit",
    ]


def test_leistung_ohne_note_erscheint_ohne_wert(session, graph):
    _leistung(session, graph.notengruppe, "2. Arbeit", date(2026, 11, 1))
    session.commit()

    gruppe = blatt(session, graph.schueler_a).kurse[0].halbjahre[0].gruppen[0]
    ohne = [e for e in gruppe.eintraege if e.leistung.bezeichnung == "2. Arbeit"][0]
    assert ohne.note is None


def test_halbjahresnote_steht_am_kurs(session, graph):
    kursblock = blatt(session, graph.schueler_a).kurse[0]
    assert kursblock.halbjahre[0].ergebnis.wert == Decimal("2.0")
    assert kursblock.halbjahre[0].anzeige == "2 (berechnet 2,0)"


def test_halbjahr_ohne_note_zeigt_keinen_wert(session, graph):
    """Not a zero and not a six -- nothing (T-7)."""
    kursblock = blatt(session, graph.schueler_a).kurse[0]
    assert kursblock.halbjahre[1].ergebnis is None
    assert kursblock.halbjahre[1].anzeige == OHNE_WERT
    assert kursblock.jahresergebnis is None
    assert kursblock.jahresanzeige == OHNE_WERT


def test_t9_festsetzung_neben_dem_berechneten_wert(session, graph):
    """Display half of test case T-9; the calculation half is in section 4."""
    gruppe_hj2 = Notengruppe(
        kurs=graph.kurs,
        halbjahr=graph.halbjahr_2,
        bezeichnung="Klassenarbeiten",
        gewicht=Decimal("50"),
        reihenfolge=1,
    )
    session.add(gruppe_hj2)
    leistung = _leistung(session, gruppe_hj2, "1. Arbeit HJ2", date(2027, 3, 1))
    _note(session, leistung, graph.schueler_a, "3.0")
    graph.kurs.gewicht_halbjahr_1 = Decimal("40")
    graph.kurs.gewicht_halbjahr_2 = Decimal("60")
    session.add(
        Notenueberschreibung(
            schueler_id=graph.schueler_a.id,
            kurs_id=graph.kurs.id,
            bezugszeitraum=Bezugszeitraum.JAHR,
            notenwert=Decimal("2.0"),
            quelle=UeberschreibungQuelle.MANUELL,
            begruendung="Deutliche Steigerung im zweiten Halbjahr.",
        )
    )
    session.commit()

    kursblock = blatt(session, graph.schueler_a).kurse[0]
    assert kursblock.jahresergebnis.wert == Decimal("2.6")
    assert kursblock.jahresanzeige == "2 (berechnet 2,6)"
    assert kursblock.jahresfestsetzung.begruendung.startswith("Deutliche")


def test_anzeige_ohne_berechnung_aber_mit_festsetzung(session, graph):
    session.add(
        Notenueberschreibung(
            schueler_id=graph.schueler_a.id,
            kurs_id=graph.kurs.id,
            bezugszeitraum=Bezugszeitraum.HALBJAHR_2,
            notenwert=Decimal("3.0"),
            quelle=UeberschreibungQuelle.MANUELL,
        )
    )
    session.commit()

    kursblock = blatt(session, graph.schueler_a).kurse[0]
    assert kursblock.halbjahre[1].anzeige == "3 (festgesetzt)"


def test_anzeige_ohne_alles():
    assert notenanzeige(None, None) == OHNE_WERT


def test_kurs_ohne_teilnahme_aber_mit_noten_bleibt_sichtbar(session, graph):
    """Otherwise entered grades would vanish from the view without trace."""
    setze_teilnahme(session, graph.kurs, graph.schueler_a, False)
    session.commit()

    ergebnis = blatt(session, graph.schueler_a)
    assert len(ergebnis.kurse) == 1
    assert ergebnis.kurse[0].nimmt_teil is False


def test_kurs_ohne_teilnahme_und_ohne_noten_faellt_weg(session, graph):
    setze_teilnahme(session, graph.kurs, graph.schueler_b, False)
    session.commit()

    assert blatt(session, graph.schueler_b).kurse == ()


def test_schueler_ohne_jede_note_ergibt_ein_leeres_aber_fehlerfreies_blatt(
    session, graph
):
    ergebnis = blatt(session, graph.schueler_b)
    kursblock = ergebnis.kurse[0]
    assert kursblock.jahresanzeige == OHNE_WERT
    assert all(hj.ergebnis is None for hj in kursblock.halbjahre)
