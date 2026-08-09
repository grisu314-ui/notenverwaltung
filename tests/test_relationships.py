"""The object graph has to be navigable in both directions after a reload."""

from sqlalchemy import inspect

from app.db.models import Klasse, Kurs, Schueler, Schuljahr


def test_graph_ist_nach_neuladen_vollstaendig_navigierbar(session, graph):
    schuljahr_id = graph.schuljahr.id
    session.commit()
    session.expunge_all()

    schuljahr = session.get(Schuljahr, schuljahr_id)
    assert [halbjahr.nummer for halbjahr in schuljahr.halbjahre] == [1, 2]

    klasse = schuljahr.klassen[0]
    assert {schueler.vorname for schueler in klasse.schueler} == {"Änne", "Bernd"}

    kurs = klasse.kurse[0]
    assert {teilnahme.schueler.nachname for teilnahme in kurs.teilnahmen} == {
        "Öztürk",
        "Straßer",
    }

    notengruppe = kurs.notengruppen[0]
    assert notengruppe.halbjahr.nummer == 1

    note = notengruppe.leistungen[0].noten[0]
    assert note.schueler.vorname == "Änne"
    assert note.leistung.notengruppe.kurs.klasse.schuljahr.bezeichnung == "2026/27"


def test_rueckweg_vom_schueler_zum_schuljahr(session, graph):
    schueler_id = graph.schueler_a.id
    session.commit()
    session.expunge_all()

    schueler = session.get(Schueler, schueler_id)
    assert schueler.klasse.schuljahr.ist_aktiv is True
    assert schueler.noten[0].leistung.bezeichnung == "1. Klassenarbeit"


def test_foto_wird_nicht_mitgeladen(session, graph):
    """A class list must not pull thirty photos into memory."""
    session.expunge_all()

    schueler = session.query(Schueler).first()
    assert "foto" in inspect(schueler).unloaded

    assert schueler.foto is None  # still reachable, loaded on demand
    assert "foto" not in inspect(schueler).unloaded


def test_kurs_ohne_notenschluessel_ist_zulaessig(session, graph):
    """The course default is optional; an assessment can carry its own key."""
    kurs = Kurs(klasse_id=graph.klasse.id, fach="Sport")
    session.add(kurs)
    session.commit()

    assert session.get(Kurs, kurs.id).notenschluessel is None


def test_klasse_gehoert_zu_genau_einem_schuljahr(session, graph):
    klasse = session.get(Klasse, graph.klasse.id)
    assert klasse.schuljahr_id == graph.schuljahr.id
