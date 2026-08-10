"""The adapter between stored rows and the grading module."""

from datetime import date
from decimal import Decimal

from app.db.models import Leistung, Note, Notengruppe, Notenueberschreibung
from app.enums import Bezugszeitraum, NoteStatus, UeberschreibungQuelle
from app.services.calculation import (
    festsetzung,
    halbjahresergebnis,
    jahresergebnis,
)


def _leistung(session, notengruppe, bezeichnung, gewicht="1.0"):
    leistung = Leistung(
        notengruppe=notengruppe,
        bezeichnung=bezeichnung,
        datum=date(2026, 10, 1),
        gewicht=Decimal(gewicht),
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


def test_halbjahresergebnis_aus_gespeicherten_noten(session, graph):
    """The graph fixture holds one grade 2.0 in a group weighted 50."""
    ergebnis = halbjahresergebnis(graph.kurs, graph.schueler_a, graph.halbjahr_1)
    assert ergebnis.wert == Decimal("2.0")
    assert ergebnis.ganze_note == 2


def test_ohne_note_gibt_es_kein_ergebnis(session, graph):
    """T-7 through the adapter: the second pupil has no grade at all."""
    assert halbjahresergebnis(graph.kurs, graph.schueler_b, graph.halbjahr_1) is None


def test_noten_anderer_schueler_bleiben_unberuecksichtigt(session, graph):
    _note(session, graph.leistung, graph.schueler_b, "6.0")
    session.commit()

    ergebnis = halbjahresergebnis(graph.kurs, graph.schueler_a, graph.halbjahr_1)
    assert ergebnis.wert == Decimal("2.0")


def test_noten_des_anderen_halbjahrs_bleiben_unberuecksichtigt(session, graph):
    gruppe_hj2 = Notengruppe(
        kurs=graph.kurs,
        halbjahr=graph.halbjahr_2,
        bezeichnung="Klassenarbeiten",
        gewicht=Decimal("50"),
        reihenfolge=1,
    )
    session.add(gruppe_hj2)
    leistung = _leistung(session, gruppe_hj2, "1. Arbeit HJ2")
    _note(session, leistung, graph.schueler_a, "5.0")
    session.commit()

    assert halbjahresergebnis(
        graph.kurs, graph.schueler_a, graph.halbjahr_1
    ).wert == Decimal("2.0")
    assert halbjahresergebnis(
        graph.kurs, graph.schueler_a, graph.halbjahr_2
    ).wert == Decimal("5.0")


def test_gewichte_aus_der_datenbank_wirken(session, graph):
    """Second Leistung weighted twice as heavily inside the same group."""
    zweite = _leistung(session, graph.notengruppe, "2. Klassenarbeit", gewicht="2.0")
    _note(session, zweite, graph.schueler_a, "5.0")
    session.commit()

    # (1*2.0 + 2*5.0) / 3 = 4.0
    assert halbjahresergebnis(
        graph.kurs, graph.schueler_a, graph.halbjahr_1
    ).wert == Decimal("4.0")


def test_nicht_gewertete_note_aus_der_datenbank_zaehlt_nicht(session, graph):
    zweite = _leistung(session, graph.notengruppe, "2. Klassenarbeit")
    _note(session, zweite, graph.schueler_a, None, status=NoteStatus.NICHT_GEWERTET)
    session.commit()

    assert halbjahresergebnis(
        graph.kurs, graph.schueler_a, graph.halbjahr_1
    ).wert == Decimal("2.0")


def test_nicht_erbrachte_note_aus_der_datenbank_geht_als_sechs_ein(session, graph):
    zweite = _leistung(session, graph.notengruppe, "2. Klassenarbeit")
    _note(session, zweite, graph.schueler_a, None, status=NoteStatus.NICHT_ERBRACHT)
    session.commit()

    assert halbjahresergebnis(
        graph.kurs, graph.schueler_a, graph.halbjahr_1
    ).wert == Decimal("4.0")


def _fuelle_beide_halbjahre(session, graph, wert_hj1="2.0", wert_hj2="3.0"):
    graph.note.notenwert = Decimal(wert_hj1)
    gruppe_hj2 = Notengruppe(
        kurs=graph.kurs,
        halbjahr=graph.halbjahr_2,
        bezeichnung="Klassenarbeiten",
        gewicht=Decimal("50"),
        reihenfolge=1,
    )
    session.add(gruppe_hj2)
    leistung = _leistung(session, gruppe_hj2, "1. Arbeit HJ2")
    _note(session, leistung, graph.schueler_a, wert_hj2)
    session.commit()


def test_jahresergebnis_bei_fuenfzig_fuenfzig(session, graph):
    _fuelle_beide_halbjahre(session, graph)

    ergebnis = jahresergebnis(session, graph.kurs, graph.schueler_a)
    assert ergebnis.wert == Decimal("2.5")
    assert ergebnis.ganze_note == 2  # tie goes to the better grade


def test_keine_jahresnote_solange_ein_halbjahr_leer_ist(session, graph):
    """The practical case is January."""
    assert jahresergebnis(session, graph.kurs, graph.schueler_a) is None


def test_festgesetzte_halbjahresnote_schlaegt_die_berechnete(session, graph):
    _fuelle_beide_halbjahre(session, graph)
    session.add(
        Notenueberschreibung(
            schueler_id=graph.schueler_a.id,
            kurs_id=graph.kurs.id,
            bezugszeitraum=Bezugszeitraum.HALBJAHR_1,
            notenwert=Decimal("4.0"),
            quelle=UeberschreibungQuelle.MANUELL,
            begruendung="Testfall",
        )
    )
    session.commit()

    # 4.0 statt der berechneten 2.0, also (4.0 + 3.0) / 2 = 3.5
    ergebnis = jahresergebnis(session, graph.kurs, graph.schueler_a)
    assert ergebnis.wert == Decimal("3.5")
    assert ergebnis.ganze_note == 3  # tie goes to the better grade


def test_festsetzung_liefert_den_juengsten_eintrag(session, graph):
    for wert in ("3.0", "2.0"):
        session.add(
            Notenueberschreibung(
                schueler_id=graph.schueler_a.id,
                kurs_id=graph.kurs.id,
                bezugszeitraum=Bezugszeitraum.JAHR,
                notenwert=Decimal(wert),
                quelle=UeberschreibungQuelle.MANUELL,
            )
        )
        session.commit()

    aktuell = festsetzung(session, graph.kurs, graph.schueler_a, Bezugszeitraum.JAHR)
    assert aktuell.notenwert == Decimal("2.0")


def test_kurseigene_halbjahrsgewichtung_wirkt(session, graph):
    _fuelle_beide_halbjahre(session, graph)
    graph.kurs.gewicht_halbjahr_1 = Decimal("40")
    graph.kurs.gewicht_halbjahr_2 = Decimal("60")
    session.commit()

    # T-8: 0.4*2.0 + 0.6*3.0 = 2.6
    ergebnis = jahresergebnis(session, graph.kurs, graph.schueler_a)
    assert ergebnis.wert == Decimal("2.6")
    assert ergebnis.ganze_note == 3
