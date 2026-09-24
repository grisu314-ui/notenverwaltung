"""The participation grade of the day (specification 5.6, 3.1).

This one writes a grade, so it is checked harder than the rest of the seating
plan: what lands in the database, what the history records, and -- the point
of the weight 3 -- that a term of participation grades does not outweigh the
written work.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.db.models import (
    VORGABE_NOTENGRUPPEN,
    Klasse,
    Kurs,
    Leistung,
    Note,
    NoteHistorie,
    Notengruppe,
    Schueler,
)
from app.enums import NoteStatus
from app.services import noten as notendienst
from app.services import sitzplan as dienst
from app.services import verwaltung
from app.services.calculation import halbjahresergebnis
from app.services.fehler import Verwaltungsfehler

# Inside the first term of the graph fixture (01.08.2026 - 31.01.2027), and
# deliberately not the day of its Klassenarbeit -- these tests count rows.
SCHULTAG = date(2026, 12, 1)
ZWEITER_TAG = date(2026, 12, 2)


def _gruppen(session, kurs, halbjahr=None):
    frage = session.query(Notengruppe).filter_by(kurs_id=kurs.id)
    if halbjahr is not None:
        frage = frage.filter_by(halbjahr_id=halbjahr.id)
    return {g.bezeichnung: g for g in frage.all()}


# ---------------------------------------------------------------------------
# The default groups (3.1)
# ---------------------------------------------------------------------------


def test_ein_neuer_kurs_bekommt_drei_gruppen_je_halbjahr(session, graph):
    kurs = verwaltung.lege_kurs_an(session, graph.klasse, "Politik")

    for halbjahr in (graph.halbjahr_1, graph.halbjahr_2):
        gruppen = _gruppen(session, kurs, halbjahr)
        assert set(gruppen) == {"Klassenarbeit", "Kleiner Nachweis", "Mitarbeit"}
        assert gruppen["Klassenarbeit"].gewicht == Decimal("70")
        assert gruppen["Kleiner Nachweis"].gewicht == Decimal("30")
        assert gruppen["Mitarbeit"].gewicht == Decimal("3")

    assert session.query(Notengruppe).filter_by(kurs_id=kurs.id).count() == 6


def test_die_vorgabegruppen_bleiben_aenderbar(session, graph):
    """A starting point, not a rule (3.1)."""
    kurs = verwaltung.lege_kurs_an(session, graph.klasse, "Politik")
    gruppe = _gruppen(session, kurs, graph.halbjahr_1)["Mitarbeit"]

    verwaltung.aendere_notengruppe(
        session, gruppe, "Mündliche Mitarbeit", Decimal("8"), gruppe.reihenfolge
    )

    assert gruppe.bezeichnung == "Mündliche Mitarbeit"
    assert gruppe.gewicht == Decimal("8")


def test_bestehende_kurse_bekommen_nichts_nachtraeglich(session, graph):
    """The course of the fixture was created without the defaults."""
    assert _gruppen(session, graph.kurs) == {"Klassenarbeiten": graph.notengruppe}


def test_die_reihenfolge_steht_fest(session, graph):
    kurs = verwaltung.lege_kurs_an(session, graph.klasse, "Politik")
    gruppen = sorted(
        session.query(Notengruppe)
        .filter_by(kurs_id=kurs.id, halbjahr_id=graph.halbjahr_1.id)
        .all(),
        key=lambda g: g.reihenfolge,
    )

    assert [g.bezeichnung for g in gruppen] == [
        bezeichnung for bezeichnung, _, _ in VORGABE_NOTENGRUPPEN
    ]


# ---------------------------------------------------------------------------
# Awarding one
# ---------------------------------------------------------------------------


@pytest.fixture
def kurs(session, graph):
    """A course with the default groups, both pupils taking part."""
    return verwaltung.lege_kurs_an(session, graph.klasse, "Politik")


def test_die_erste_note_des_tages_legt_die_leistung_an(session, graph, kurs):
    note = dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), datum=SCHULTAG
    )

    leistung = note.leistung
    assert leistung.bezeichnung == "Mitarbeit 01.12.2026"
    assert leistung.datum == SCHULTAG
    assert leistung.gewicht == Decimal("1.0")
    assert leistung.notengruppe.bezeichnung == "Mitarbeit"
    assert leistung.notengruppe.halbjahr_id == graph.halbjahr_1.id
    assert note.status == NoteStatus.GEWERTET
    assert note.notenwert == Decimal("1.0")


def test_die_zweite_note_desselben_tages_nutzt_dieselbe_leistung(session, graph, kurs):
    erste = dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), datum=SCHULTAG
    )
    zweite = dienst.mitarbeitsnote(
        session, kurs, graph.schueler_b, Decimal("5.0"), datum=SCHULTAG
    )

    assert erste.leistung_id == zweite.leistung_id
    assert session.query(Leistung).filter_by(datum=SCHULTAG).count() == 1


def test_ein_anderer_tag_bekommt_eine_eigene_leistung(session, graph, kurs):
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), datum=SCHULTAG
    )
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("2.0"), datum=ZWEITER_TAG
    )

    bezeichnungen = {le.bezeichnung for le in session.query(Leistung).all()}
    assert "Mitarbeit 01.12.2026" in bezeichnungen
    assert "Mitarbeit 02.12.2026" in bezeichnungen


def test_wer_nichts_bekommt_hat_keinen_datensatz(session, graph, kurs):
    """Not a missing value -- no performance. It changes no calculation."""
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), datum=SCHULTAG
    )

    noten = session.query(Note).join(Leistung).filter(Leistung.datum == SCHULTAG).all()
    assert [n.schueler_id for n in noten] == [graph.schueler_a.id]


def test_die_notiz_wird_gespeichert(session, graph, kurs):
    note = dienst.mitarbeitsnote(
        session,
        kurs,
        graph.schueler_a,
        Decimal("1.0"),
        notiz="Hat die Diskussion getragen.",
        datum=SCHULTAG,
    )

    assert note.notiz == "Hat die Diskussion getragen."


def test_eine_leere_notiz_wird_nicht_als_leerer_text_gespeichert(session, graph, kurs):
    note = dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), notiz="   ", datum=SCHULTAG
    )

    assert note.notiz is None


def test_eine_nachgereichte_notiz_geht_nicht_verloren(session, graph, kurs):
    """The grade did not change, only the remark -- and it still has to save."""
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), datum=SCHULTAG
    )

    note = dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), notiz="Nachgetragen.", datum=SCHULTAG
    )

    assert note.notiz == "Nachgetragen."
    assert session.query(Note).count() == 2  # the fixture's grade plus this one


def test_die_aenderung_steht_in_der_historie(session, graph, kurs):
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), datum=SCHULTAG
    )
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("2.0"), datum=SCHULTAG
    )

    eintraege = (
        session.query(NoteHistorie)
        .filter_by(schueler_id=graph.schueler_a.id)
        .order_by(NoteHistorie.id)
        .all()
    )
    # The fixture writes none, so these two are ours: created, then changed.
    assert [e.aktion for e in eintraege] == ["angelegt", "geaendert"]
    assert eintraege[1].alter_notenwert == Decimal("1.0")
    assert eintraege[1].neuer_notenwert == Decimal("2.0")


def test_eine_falsche_note_wird_geloescht_nicht_umgewidmet(session, graph, kurs):
    note = dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), datum=SCHULTAG
    )
    leistung = note.leistung

    notendienst.loesche_note(session, leistung, graph.schueler_a)
    session.flush()

    assert (
        session.query(Note)
        .filter_by(leistung_id=leistung.id, schueler_id=graph.schueler_a.id)
        .count()
        == 0
    )
    assert (
        session.query(NoteHistorie)
        .filter_by(schueler_id=graph.schueler_a.id, aktion="geloescht")
        .count()
        == 1
    )


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_ein_kurs_einer_anderen_klasse_wird_abgewiesen(session, graph, kurs):
    andere = Klasse(schuljahr=graph.schuljahr, bezeichnung="BFS 26b")
    fremder = Schueler(klasse=andere, vorname="Carla", nachname="Fremd")
    session.add(andere)
    session.flush()

    with pytest.raises(Verwaltungsfehler, match="nicht zu der Klasse"):
        dienst.mitarbeitsnote(
            session, kurs, fremder, Decimal("1.0"), datum=SCHULTAG
        )


def test_ein_nichtteilnehmer_wird_abgewiesen(session, graph, kurs):
    verwaltung.setze_teilnahme(session, kurs, graph.schueler_b, ist_aktiv=False)

    with pytest.raises(Verwaltungsfehler, match="nimmt an diesem Kurs nicht"):
        dienst.mitarbeitsnote(
            session, kurs, graph.schueler_b, Decimal("1.0"), datum=SCHULTAG
        )


def test_ein_datum_in_den_ferien_wird_abgewiesen(session, graph, kurs):
    with pytest.raises(Verwaltungsfehler, match="keinem Halbjahr"):
        dienst.mitarbeitsnote(
            session, kurs, graph.schueler_a, Decimal("1.0"), datum=date(2026, 7, 15)
        )


def test_ohne_gruppe_mitarbeit_wird_abgewiesen(session, graph):
    """The old courses of the operator have no such group until they do."""
    with pytest.raises(Verwaltungsfehler, match="Notengruppe"):
        dienst.mitarbeitsnote(
            session, graph.kurs, graph.schueler_a, Decimal("1.0"), datum=SCHULTAG
        )


def test_eine_umbenannte_gruppe_wird_nicht_mehr_gefunden(session, graph, kurs):
    """Documented consequence of finding the group by its name -- and it is
    loud: nothing is created behind the operator's back."""
    gruppe = _gruppen(session, kurs, graph.halbjahr_1)["Mitarbeit"]
    verwaltung.aendere_notengruppe(
        session, gruppe, "Mündliches", Decimal("3"), gruppe.reihenfolge
    )

    with pytest.raises(Verwaltungsfehler, match="Notengruppe"):
        dienst.mitarbeitsnote(
            session, kurs, graph.schueler_a, Decimal("1.0"), datum=SCHULTAG
        )


def test_ein_ungueltiger_notenwert_wird_abgewiesen(session, graph, kurs):
    with pytest.raises(Verwaltungsfehler):
        dienst.mitarbeitsnote(
            session, kurs, graph.schueler_a, Decimal("2.5"), datum=SCHULTAG
        )


# ---------------------------------------------------------------------------
# The quick entry: remark, taking back, today's state
# ---------------------------------------------------------------------------


def test_ohne_notiz_bleibt_eine_vorhandene_notiz_stehen(session, graph, kurs):
    """The quick entry has no remark field and passes none."""
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), notiz="Gute Frage.", datum=SCHULTAG
    )

    note = dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.3"), datum=SCHULTAG
    )

    assert note.notenwert == Decimal("1.3")
    assert note.notiz == "Gute Frage."


def test_eine_leere_notiz_entfernt_die_vorhandene(session, graph, kurs):
    """The seat menu sends its field, empty or not; emptying it is a decision."""
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), notiz="Gute Frage.", datum=SCHULTAG
    )

    note = dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.0"), notiz="", datum=SCHULTAG
    )

    assert note.notiz is None


def test_loeschen_nimmt_die_note_des_tages_zurueck(session, graph, kurs):
    note = dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("5.0"), datum=SCHULTAG
    )
    leistung_id = note.leistung_id

    geloescht = dienst.loesche_mitarbeitsnote(
        session, kurs, graph.schueler_a, datum=SCHULTAG
    )

    assert geloescht is True
    assert session.query(Note).filter_by(leistung_id=leistung_id).count() == 0
    assert (
        session.query(NoteHistorie)
        .filter_by(schueler_id=graph.schueler_a.id, aktion="geloescht")
        .count()
        == 1
    )


def test_loeschen_trifft_nur_den_einen_tag(session, graph, kurs):
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("2.0"), datum=SCHULTAG
    )
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("3.0"), datum=ZWEITER_TAG
    )

    dienst.loesche_mitarbeitsnote(session, kurs, graph.schueler_a, datum=ZWEITER_TAG)

    werte = [
        n.notenwert
        for n in session.query(Note).join(Leistung).filter(
            Note.schueler_id == graph.schueler_a.id,
            Leistung.bezeichnung.like("Mitarbeit %"),
        )
    ]
    assert werte == [Decimal("2.0")]


def test_loeschen_ohne_note_meldet_nichts_geloescht(session, graph, kurs):
    assert (
        dienst.loesche_mitarbeitsnote(session, kurs, graph.schueler_a, datum=SCHULTAG)
        is False
    )
    assert session.query(NoteHistorie).filter_by(aktion="geloescht").count() == 0


def test_der_tagesstand_kennt_noten_und_teilnehmer(session, graph, kurs):
    verwaltung.setze_teilnahme(session, kurs, graph.schueler_b, ist_aktiv=False)
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.7"), datum=SCHULTAG
    )

    stand = dienst.tagesstand(session, kurs, SCHULTAG)

    assert stand.hindernis is None
    assert stand.teilnehmer == {graph.schueler_a.id}
    assert {sid: n.notenwert for sid, n in stand.noten.items()} == {
        graph.schueler_a.id: Decimal("1.7")
    }


def test_der_tagesstand_eines_anderen_tages_ist_leer(session, graph, kurs):
    dienst.mitarbeitsnote(
        session, kurs, graph.schueler_a, Decimal("1.7"), datum=SCHULTAG
    )

    assert dienst.tagesstand(session, kurs, ZWEITER_TAG).noten == {}


def test_der_tagesstand_nennt_ferien_und_fehlende_gruppe(session, graph, kurs):
    ferien = dienst.tagesstand(session, kurs, date(2026, 7, 15))
    ohne_gruppe = dienst.tagesstand(session, graph.kurs, SCHULTAG)

    assert "keinem Halbjahr" in ferien.hindernis
    assert "Notengruppe" in ohne_gruppe.hindernis
    assert ferien.noten == {} and ohne_gruppe.noten == {}


# ---------------------------------------------------------------------------
# The arithmetic the weight 3 exists for (3.1, 4.4)
# ---------------------------------------------------------------------------


def test_ein_halbjahr_mitarbeit_ueberstimmt_die_klassenarbeiten_nicht(
    session, graph, kurs
):
    """Two 2s in the written work stay a 2, whatever the participation says."""
    gruppen = _gruppen(session, kurs, graph.halbjahr_1)
    for nummer, wert in ((1, "2.0"), (2, "2.0")):
        leistung = notendienst.lege_leistung_an(
            session,
            gruppen["Klassenarbeit"],
            f"{nummer}. Klassenarbeit",
            date(2026, 10, nummer),
            Decimal("1.0"),
        )
        notendienst.setze_note(
            session, leistung, graph.schueler_a, NoteStatus.GEWERTET, Decimal(wert)
        )

    # Twenty participation grades, all of them a 5 -- far more than the
    # operator expects to hand out in a term.
    for tag in range(1, 21):
        dienst.mitarbeitsnote(
            session,
            kurs,
            graph.schueler_a,
            Decimal("5.0"),
            datum=date(2026, 11, tag),
        )
    session.flush()

    ergebnis = halbjahresergebnis(kurs, graph.schueler_a, graph.halbjahr_1)
    # 2 x 70 x 2,0 + 20 x 3 x 5,0 = 580 over 200  ->  2,9
    assert ergebnis.wert == Decimal("2.9")
    assert ergebnis.ganze_note == 3


def test_ohne_mitarbeit_bleibt_die_note_unveraendert(session, graph, kurs):
    """The counterpart: a pupil who gets none is not punished for it (4.4)."""
    gruppen = _gruppen(session, kurs, graph.halbjahr_1)
    leistung = notendienst.lege_leistung_an(
        session,
        gruppen["Klassenarbeit"],
        "1. Klassenarbeit",
        date(2026, 10, 1),
        Decimal("1.0"),
    )
    notendienst.setze_note(
        session, leistung, graph.schueler_a, NoteStatus.GEWERTET, Decimal("2.0")
    )
    session.flush()

    ergebnis = halbjahresergebnis(kurs, graph.schueler_a, graph.halbjahr_1)
    assert ergebnis.wert == Decimal("2.0")
