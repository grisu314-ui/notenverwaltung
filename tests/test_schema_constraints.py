"""The guarantees the database itself has to give.

These are not academic: without the foreign key pragma SQLite silently keeps
orphaned grades, and without the CHECK constraints a grade could be stored in
a state the grading module cannot interpret.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    MAX_RASTER,
    VORGABE_GEWICHT_HALBJAHR,
    Halbjahr,
    Kurs,
    Note,
    NoteHistorie,
    Notenueberschreibung,
    Schueler,
    Sitzplan,
    Sitzplatz,
)
from app.enums import (
    Bezugszeitraum,
    HistorieAktion,
    NoteStatus,
    UeberschreibungQuelle,
)


def _anzahl(session, tabelle: str) -> int:
    return session.connection().exec_driver_sql(f"SELECT count(*) FROM {tabelle}").scalar()


def test_fremdschluessel_werden_erzwungen(session, graph):
    session.add(Schueler(vorname="Test", nachname="Test", klasse_id=999))
    with pytest.raises(IntegrityError):
        session.flush()


def test_loeschen_eines_schuljahrs_entfernt_alle_abhaengigen_daten(session, graph):
    """Specification section 11: deletion has to be complete."""
    session.add(
        NoteHistorie(
            note_id=graph.note.id,
            schueler_id=graph.schueler_a.id,
            leistung_id=graph.leistung.id,
            aktion=HistorieAktion.ANGELEGT,
            neuer_notenwert=Decimal("2.0"),
            neuer_status=NoteStatus.GEWERTET,
        )
    )
    session.add(
        Notenueberschreibung(
            schueler_id=graph.schueler_a.id,
            kurs_id=graph.kurs.id,
            bezugszeitraum=Bezugszeitraum.HALBJAHR_1,
            notenwert=Decimal("2.0"),
            quelle=UeberschreibungQuelle.MANUELL,
            begruendung="Testfall",
        )
    )
    session.commit()

    session.delete(graph.schuljahr)
    session.commit()

    for tabelle in (
        "schuljahr",
        "halbjahr",
        "klasse",
        "schueler",
        "kurs",
        "kursteilnahme",
        "notengruppe",
        "leistung",
        "note",
        "note_historie",
        "notenueberschreibung",
    ):
        assert _anzahl(session, tabelle) == 0, tabelle


def test_loeschen_eines_schuelers_entfernt_seine_historie(session, graph):
    session.add(
        NoteHistorie(
            note_id=graph.note.id,
            schueler_id=graph.schueler_a.id,
            leistung_id=graph.leistung.id,
            aktion=HistorieAktion.GEAENDERT,
            alter_notenwert=Decimal("3.0"),
            alter_status=NoteStatus.GEWERTET,
            neuer_notenwert=Decimal("2.0"),
            neuer_status=NoteStatus.GEWERTET,
        )
    )
    session.commit()

    session.delete(graph.schueler_a)
    session.commit()

    assert _anzahl(session, "note_historie") == 0
    assert _anzahl(session, "note") == 0
    # The other pupil is untouched.
    assert _anzahl(session, "schueler") == 1


def test_je_schueler_und_leistung_nur_eine_note(session, graph):
    session.add(
        Note(
            leistung_id=graph.leistung.id,
            schueler_id=graph.schueler_a.id,
            notenwert=Decimal("3.0"),
            status=NoteStatus.GEWERTET,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_halbjahr_nummer_muss_eins_oder_zwei_sein(session, graph):
    session.add(
        Halbjahr(
            schuljahr_id=graph.schuljahr.id,
            nummer=3,
            beginn=date(2026, 8, 1),
            ende=date(2027, 1, 31),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_unbekannter_status_wird_abgewiesen(session, graph):
    session.add(
        Note(
            leistung_id=graph.leistung.id,
            schueler_id=graph.schueler_b.id,
            notenwert=Decimal("2.0"),
            status="entschuldigt",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_gewertete_note_ohne_notenwert_wird_abgewiesen(session, graph):
    session.add(
        Note(
            leistung_id=graph.leistung.id,
            schueler_id=graph.schueler_b.id,
            notenwert=None,
            status=NoteStatus.GEWERTET,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_nicht_erbracht_wird_ohne_notenwert_gespeichert(session, graph):
    """The 6.0 comes from the status in the grading module, never from the row.

    Otherwise a later status change could not be told apart from a real 6.
    """
    session.add(
        Note(
            leistung_id=graph.leistung.id,
            schueler_id=graph.schueler_b.id,
            notenwert=None,
            status=NoteStatus.NICHT_ERBRACHT,
        )
    )
    session.commit()

    note = session.query(Note).filter_by(schueler_id=graph.schueler_b.id).one()
    assert note.notenwert is None
    assert note.status == NoteStatus.NICHT_ERBRACHT


def test_nicht_gewertet_wird_ohne_notenwert_gespeichert(session, graph):
    session.add(
        Note(
            leistung_id=graph.leistung.id,
            schueler_id=graph.schueler_b.id,
            notenwert=None,
            status=NoteStatus.NICHT_GEWERTET,
        )
    )
    session.commit()

    assert _anzahl(session, "note") == 2


def test_halbjahrsgewichte_haben_die_vorgabe(session, graph):
    """Open point O-7, answered: 50/50, editable per course."""
    kurs = session.get(Kurs, graph.kurs.id)
    assert kurs.gewicht_halbjahr_1 == VORGABE_GEWICHT_HALBJAHR
    assert kurs.gewicht_halbjahr_2 == VORGABE_GEWICHT_HALBJAHR


@pytest.mark.parametrize("spalte", ["gewicht_halbjahr_1", "gewicht_halbjahr_2"])
def test_halbjahrsgewichte_duerfen_nicht_leer_sein(session, graph, spalte):
    setattr(graph.kurs, spalte, None)
    with pytest.raises(IntegrityError):
        session.flush()


def test_mehrere_festsetzungen_je_bezugszeitraum_sind_zulaessig(session, graph):
    """Append-only: the newest record wins, the previous one stays readable."""
    for notenwert, quelle in (
        (Decimal("3.0"), UeberschreibungQuelle.BERECHNET_UEBERNOMMEN),
        (Decimal("2.0"), UeberschreibungQuelle.MANUELL),
    ):
        session.add(
            Notenueberschreibung(
                schueler_id=graph.schueler_a.id,
                kurs_id=graph.kurs.id,
                bezugszeitraum=Bezugszeitraum.JAHR,
                notenwert=notenwert,
                quelle=quelle,
                begruendung=None,
            )
        )
        session.commit()

    festsetzungen = (
        session.query(Notenueberschreibung)
        .filter_by(schueler_id=graph.schueler_a.id, bezugszeitraum=Bezugszeitraum.JAHR)
        .order_by(Notenueberschreibung.erstellt_am.desc(), Notenueberschreibung.id.desc())
        .all()
    )
    assert len(festsetzungen) == 2
    assert festsetzungen[0].notenwert == Decimal("2.0")
    assert festsetzungen[1].notenwert == Decimal("3.0")


def test_unbekannter_bezugszeitraum_wird_abgewiesen(session, graph):
    session.add(
        Notenueberschreibung(
            schueler_id=graph.schueler_a.id,
            kurs_id=graph.kurs.id,
            bezugszeitraum="quartal_1",
            notenwert=Decimal("2.0"),
            quelle=UeberschreibungQuelle.MANUELL,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_historie_ueberlebt_das_loeschen_der_note(session, graph):
    """The deletion is one of the events the history exists for (3.2)."""
    session.add(
        NoteHistorie(
            note_id=graph.note.id,
            schueler_id=graph.schueler_a.id,
            leistung_id=graph.leistung.id,
            aktion=HistorieAktion.GELOESCHT,
            alter_notenwert=Decimal("2.0"),
            alter_status=NoteStatus.GEWERTET,
        )
    )
    session.commit()

    session.delete(graph.note)
    session.commit()

    eintrag = session.query(NoteHistorie).one()
    assert _anzahl(session, "note") == 0
    assert eintrag.aktion == HistorieAktion.GELOESCHT
    assert eintrag.alter_notenwert == Decimal("2.0")


def test_kurs_und_fach_sind_je_klasse_eindeutig(session, graph):
    session.add(Kurs(klasse_id=graph.klasse.id, fach="Deutsch"))
    with pytest.raises(IntegrityError):
        session.flush()


def _sitzplan(session, graph) -> Sitzplan:
    plan = Sitzplan(klasse_id=graph.klasse.id)
    session.add(plan)
    session.flush()
    return plan


def test_je_klasse_nur_ein_sitzplan(session, graph):
    """Specification 5.6: exactly one plan per class, enforced by the schema."""
    _sitzplan(session, graph)
    session.add(Sitzplan(klasse_id=graph.klasse.id))
    with pytest.raises(IntegrityError):
        session.flush()


def test_ein_platz_traegt_nur_einen_schueler(session, graph):
    plan = _sitzplan(session, graph)
    session.add(
        Sitzplatz(sitzplan=plan, schueler=graph.schueler_a, reihe=1, position=1)
    )
    session.flush()

    session.add(
        Sitzplatz(sitzplan=plan, schueler=graph.schueler_b, reihe=1, position=1)
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_ein_schueler_sitzt_nur_auf_einem_platz(session, graph):
    plan = _sitzplan(session, graph)
    session.add(
        Sitzplatz(sitzplan=plan, schueler=graph.schueler_a, reihe=1, position=1)
    )
    session.flush()

    session.add(
        Sitzplatz(sitzplan=plan, schueler=graph.schueler_a, reihe=2, position=3)
    )
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    "reihen, sitze", [(0, 6), (5, 0), (MAX_RASTER + 1, 6), (5, MAX_RASTER + 1)]
)
def test_rastergroesse_bleibt_in_den_grenzen(session, graph, reihen, sitze):
    session.add(
        Sitzplan(klasse_id=graph.klasse.id, reihen=reihen, sitze_je_reihe=sitze)
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_platz_ausserhalb_des_rasters_wird_vom_schema_nicht_erkannt(session, graph):
    """Deliberate gap, documented rather than papered over.

    SQLite allows no subquery in a CHECK, so the schema cannot compare a seat
    against the grid of its plan. The service layer does it; this test pins
    down that the database does **not**, so nobody relies on it.
    """
    plan = _sitzplan(session, graph)
    session.add(
        Sitzplatz(sitzplan=plan, schueler=graph.schueler_a, reihe=99, position=99)
    )
    session.flush()

    assert _anzahl(session, "sitzplatz") == 1


def test_geloeschter_schueler_raeumt_seinen_platz(session, graph):
    plan = _sitzplan(session, graph)
    session.add(
        Sitzplatz(sitzplan=plan, schueler=graph.schueler_a, reihe=1, position=1)
    )
    session.commit()

    session.delete(graph.schueler_a)
    session.commit()

    assert _anzahl(session, "sitzplatz") == 0
    assert _anzahl(session, "sitzplan") == 1


def test_geloeschte_klasse_nimmt_den_sitzplan_mit(session, graph):
    plan = _sitzplan(session, graph)
    session.add(
        Sitzplatz(sitzplan=plan, schueler=graph.schueler_a, reihe=1, position=1)
    )
    session.commit()

    session.delete(graph.schuljahr)
    session.commit()

    assert _anzahl(session, "sitzplan") == 0
    assert _anzahl(session, "sitzplatz") == 0


def test_arbeitet_digital_ist_nicht_null_und_hat_die_vorgabe_false(session, graph):
    """A NOT NULL column with a server default, or the migration cannot run.

    SQLite refuses to add a NOT NULL column to a table that already holds
    rows without one; every pupil that existed before migration 0003 starts
    at false.
    """
    spalten = {
        zeile[1]: zeile
        for zeile in session.connection()
        .exec_driver_sql("PRAGMA table_info(schueler)")
        .fetchall()
    }
    _, _, typ, nicht_null, vorgabe, _ = spalten["arbeitet_digital"]

    assert typ == "BOOLEAN"
    assert nicht_null == 1
    assert vorgabe is not None

    session.add(Schueler(vorname="Ohne", nachname="Angabe", klasse_id=graph.klasse.id))
    session.flush()
    assert (
        session.connection()
        .exec_driver_sql(
            "SELECT count(*) FROM schueler WHERE arbeitet_digital IS NULL"
        )
        .scalar()
        == 0
    )
