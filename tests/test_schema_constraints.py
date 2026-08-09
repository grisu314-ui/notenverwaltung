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
    Halbjahr,
    Kurs,
    Leistung,
    Note,
    NoteHistorie,
    Notenueberschreibung,
    Schueler,
)
from app.enums import (
    Bezugszeitraum,
    Eingabeart,
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

    # The grading key is shared data and must survive.
    assert _anzahl(session, "notenschluessel") == 1


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


def test_notenschluessel_kann_nicht_geloescht_werden_solange_benutzt(session, graph):
    session.delete(graph.notenschluessel)
    with pytest.raises(IntegrityError):
        session.commit()


def test_je_schueler_und_leistung_nur_eine_note(session, graph):
    session.add(
        Note(
            leistung_id=graph.leistung.id,
            schueler_id=graph.schueler_a.id,
            eingabeart=Eingabeart.NOTE,
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
            eingabeart=Eingabeart.NOTE,
            notenwert=Decimal("2.0"),
            status="entschuldigt",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_punkteingabe_ohne_punkte_wird_abgewiesen(session, graph):
    session.add(
        Note(
            leistung_id=graph.leistung.id,
            schueler_id=graph.schueler_b.id,
            eingabeart=Eingabeart.PUNKTE,
            punkte=None,
            notenwert=Decimal("2.0"),
            status=NoteStatus.GEWERTET,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_noteneingabe_mit_punkten_wird_abgewiesen(session, graph):
    session.add(
        Note(
            leistung_id=graph.leistung.id,
            schueler_id=graph.schueler_b.id,
            eingabeart=Eingabeart.NOTE,
            punkte=Decimal("45"),
            notenwert=Decimal("2.0"),
            status=NoteStatus.GEWERTET,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_gewertete_note_ohne_notenwert_wird_abgewiesen(session, graph):
    session.add(
        Note(
            leistung_id=graph.leistung.id,
            schueler_id=graph.schueler_b.id,
            eingabeart=Eingabeart.NOTE,
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
            eingabeart=Eingabeart.NOTE,
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
            eingabeart=Eingabeart.NOTE,
            notenwert=None,
            status=NoteStatus.NICHT_GEWERTET,
        )
    )
    session.commit()

    assert _anzahl(session, "note") == 2


@pytest.mark.parametrize(
    ("gewicht_1", "gewicht_2"),
    [(Decimal("40"), None), (None, Decimal("60"))],
)
def test_halbjahrsgewichte_nur_paarweise(session, graph, gewicht_1, gewicht_2):
    """A single weight would silently define the other one."""
    graph.kurs.gewicht_halbjahr_1 = gewicht_1
    graph.kurs.gewicht_halbjahr_2 = gewicht_2
    with pytest.raises(IntegrityError):
        session.flush()


def test_halbjahrsgewichte_duerfen_beide_fehlen(session, graph):
    """As long as O-7 is open, "not decided" has to be a storable state."""
    kurs = session.get(Kurs, graph.kurs.id)
    assert kurs.gewicht_halbjahr_1 is None
    assert kurs.gewicht_halbjahr_2 is None


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


def test_leistung_ohne_eigenen_schluessel_erbt_vom_kurs(session, graph):
    """NULL means "course default"; that is what T-10 depends on."""
    leistung = session.get(Leistung, graph.leistung.id)
    assert leistung.notenschluessel_id is None
    assert leistung.notengruppe.kurs.notenschluessel.bezeichnung == "IHK"
