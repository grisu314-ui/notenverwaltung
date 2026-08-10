"""The course overview matrix and the Notenspiegel (specification 5.3)."""

from datetime import date
from decimal import Decimal

from app.db.models import Leistung, Note, Notengruppe
from app.enums import NoteStatus
from app.services.calculation import halbjahresergebnis
from app.services.kursblatt import (
    ANSICHT_HALBJAHR_1,
    ANSICHT_HALBJAHR_2,
    ANSICHT_JAHR,
    blatt,
    notenspiegel,
)
from app.services.verwaltung import setze_teilnahme


def _leistung(session, notengruppe, bezeichnung, datum, gewicht="1.0"):
    leistung = Leistung(
        notengruppe=notengruppe,
        bezeichnung=bezeichnung,
        datum=datum,
        gewicht=Decimal(gewicht),
    )
    session.add(leistung)
    return leistung


def _note(session, leistung, schueler, wert, status=NoteStatus.GEWERTET):
    session.add(
        Note(
            leistung=leistung,
            schueler=schueler,
            notenwert=None if wert is None else Decimal(wert),
            status=status,
        )
    )


def test_zeilen_sind_die_aktiven_teilnehmer(session, graph):
    ergebnis = blatt(session, graph.kurs)
    assert [z.schueler.nachname for z in ergebnis.zeilen] == ["Öztürk", "Straßer"]


def test_wer_nicht_teilnimmt_erscheint_nicht(session, graph):
    setze_teilnahme(session, graph.kurs, graph.schueler_b, False)
    session.commit()

    ergebnis = blatt(session, graph.kurs)
    assert [z.schueler.nachname for z in ergebnis.zeilen] == ["Öztürk"]


def test_spalten_stehen_in_ihrer_gruppe(session, graph):
    zweite = _leistung(session, graph.notengruppe, "2. Arbeit", date(2026, 11, 1))
    session.commit()

    ergebnis = blatt(session, graph.kurs)
    assert len(ergebnis.gruppen) == 1
    gruppe = ergebnis.gruppen[0]
    assert gruppe.notengruppe.bezeichnung == "Klassenarbeiten"
    assert [leistung.bezeichnung for leistung in gruppe.leistungen] == [
        "1. Klassenarbeit",
        "2. Arbeit",
    ]
    assert zweite.id in ergebnis.zeilen[0].noten


def test_das_gesamtmittel_stimmt_mit_der_schueleransicht_ueberein(session, graph):
    """The two pages must never contradict each other."""
    ergebnis = blatt(session, graph.kurs)
    zeile = ergebnis.zeilen[0]
    direkt = halbjahresergebnis(graph.kurs, graph.schueler_a, graph.halbjahr_1)
    assert zeile.ergebnis_halbjahr[1] == direkt


def test_schueler_ohne_note_hat_kein_gesamtmittel(session, graph):
    """Not a zero and not a six -- nothing."""
    zeile = blatt(session, graph.kurs).zeilen[1]
    assert zeile.schueler.nachname == "Straßer"
    assert zeile.ergebnis_halbjahr[1] is None
    assert zeile.jahresergebnis is None


def test_halbjahr_zwei_zeigt_nur_dessen_gruppen(session, graph):
    gruppe_hj2 = Notengruppe(
        kurs=graph.kurs,
        halbjahr=graph.halbjahr_2,
        bezeichnung="Klassenarbeiten",
        gewicht=Decimal("50"),
        reihenfolge=1,
    )
    session.add(gruppe_hj2)
    _leistung(session, gruppe_hj2, "1. Arbeit HJ2", date(2027, 3, 1))
    session.commit()

    erstes = blatt(session, graph.kurs, ANSICHT_HALBJAHR_1)
    zweites = blatt(session, graph.kurs, ANSICHT_HALBJAHR_2)
    assert [le.bezeichnung for le in erstes.leistungen] == ["1. Klassenarbeit"]
    assert [le.bezeichnung for le in zweites.leistungen] == ["1. Arbeit HJ2"]


def test_jahresansicht_zeigt_alle_leistungen_beider_halbjahre(session, graph):
    """The operator's decision: everything, not a summary."""
    gruppe_hj2 = Notengruppe(
        kurs=graph.kurs,
        halbjahr=graph.halbjahr_2,
        bezeichnung="Klassenarbeiten",
        gewicht=Decimal("50"),
        reihenfolge=1,
    )
    session.add(gruppe_hj2)
    _leistung(session, gruppe_hj2, "1. Arbeit HJ2", date(2027, 3, 1))
    session.commit()

    jahr = blatt(session, graph.kurs, ANSICHT_JAHR)
    assert [le.bezeichnung for le in jahr.leistungen] == [
        "1. Klassenarbeit",
        "1. Arbeit HJ2",
    ]
    assert [h.nummer for h in jahr.halbjahre] == [1, 2]


def test_unbekannte_ansicht_faellt_auf_halbjahr_eins_zurueck(session, graph):
    assert blatt(session, graph.kurs, "quartal").ansicht == ANSICHT_HALBJAHR_1


def test_kurs_ohne_notengruppen_ergibt_ein_leeres_blatt(session, graph):
    ergebnis = blatt(session, graph.kurs, ANSICHT_HALBJAHR_2)
    assert ergebnis.gruppen == ()
    assert ergebnis.spiegel == ()
    assert len(ergebnis.zeilen) == 2


# --------------------------------------------------------------------------
# Notenspiegel
# --------------------------------------------------------------------------


def test_durchschnitt_und_verteilung(session, graph):
    """Änne already has 2.0; Bernd gets a 4-."""
    _note(session, graph.leistung, graph.schueler_b, "4.3")
    session.commit()

    spiegel = notenspiegel(graph.leistung, [graph.schueler_a, graph.schueler_b])
    assert spiegel.durchschnitt == Decimal("3.1")  # (2.0 + 4.3) / 2 = 3.15 -> 3.1
    assert spiegel.verteilung[2] == 1
    assert spiegel.verteilung[4] == 1
    assert spiegel.anzahl == 2


def test_tendenzen_zaehlen_zur_ganzen_note(session, graph):
    """2+ and 2- both land on 2."""
    graph.note.notenwert = Decimal("1.7")  # 2+
    _note(session, graph.leistung, graph.schueler_b, "2.3")  # 2-
    session.commit()

    spiegel = notenspiegel(graph.leistung, [graph.schueler_a, graph.schueler_b])
    assert spiegel.verteilung[2] == 2
    assert spiegel.verteilung[1] == 0
    assert spiegel.verteilung[3] == 0


def test_nicht_erbracht_zaehlt_als_sechs(session, graph):
    _note(session, graph.leistung, graph.schueler_b, None, NoteStatus.NICHT_ERBRACHT)
    session.commit()

    spiegel = notenspiegel(graph.leistung, [graph.schueler_a, graph.schueler_b])
    assert spiegel.verteilung[6] == 1
    assert spiegel.durchschnitt == Decimal("4.0")  # (2.0 + 6.0) / 2


def test_nicht_gewertet_faellt_aus_durchschnitt_und_verteilung(session, graph):
    """Otherwise a test with many excused pupils would look better than it was."""
    _note(session, graph.leistung, graph.schueler_b, None, NoteStatus.NICHT_GEWERTET)
    session.commit()

    spiegel = notenspiegel(graph.leistung, [graph.schueler_a, graph.schueler_b])
    assert spiegel.nicht_gewertet == 1
    assert spiegel.anzahl == 1
    assert spiegel.durchschnitt == Decimal("2.0")


def test_leistung_ohne_jede_note_hat_keinen_durchschnitt(session, graph):
    leer = _leistung(session, graph.notengruppe, "2. Arbeit", date(2026, 11, 1))
    session.commit()

    spiegel = notenspiegel(leer, [graph.schueler_a, graph.schueler_b])
    assert spiegel.durchschnitt is None
    assert spiegel.anzahl == 0
    assert all(anzahl == 0 for anzahl in spiegel.verteilung.values())


def test_spiegel_deckt_alle_spalten_ab(session, graph):
    _leistung(session, graph.notengruppe, "2. Arbeit", date(2026, 11, 1))
    session.commit()

    ergebnis = blatt(session, graph.kurs)
    assert len(ergebnis.spiegel) == len(ergebnis.leistungen)
