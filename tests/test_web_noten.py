"""The serial grade entry through the web layer (specification 5.4, 10).

What these tests can prove: the confirmation is rendered from the stored
record after the commit, and a refused entry stores nothing and says so.

What they cannot prove: what the browser shows when the connection drops
mid-request. That is exactly the case the requirement is about, and it is
covered by the manual acceptance run documented in README.md.
"""

from decimal import Decimal

from app.db.models import Note, NoteHistorie

HTMX = {"HX-Request": "true"}


def eingabe_url(graph, schueler) -> str:
    return f"/leistungen/{graph.leistung.id}/schueler/{schueler.id}"


def test_eingabemaske_listet_die_aktiven_teilnehmer(client, graph):
    antwort = client.get(f"/leistungen/{graph.leistung.id}")
    assert antwort.status_code == 200
    assert "Öztürk" in antwort.text
    assert "Straßer" in antwort.text
    assert "1 von 2" in antwort.text


def test_eingabemaske_zeigt_alle_sechzehn_noten_und_die_sonderfaelle(client, graph):
    antwort = client.get(f"/leistungen/{graph.leistung.id}")
    for beschriftung in ("1+", "2−", "6", "nicht gewertet", "nicht erbracht"):
        assert f">{beschriftung}</option>" in antwort.text


def test_note_eintragen_bestaetigt_den_gespeicherten_stand(client, session, graph):
    antwort = client.post(
        eingabe_url(graph, graph.schueler_b), data={"wert": "3.0"}, headers=HTMX
    )
    assert antwort.status_code == 200
    assert "gespeichert" in antwort.text
    # The confirmation comes from the stored row, not from the request.
    note = session.query(Note).filter_by(schueler_id=graph.schueler_b.id).one()
    assert note.notenwert == Decimal("3.0")
    assert session.query(NoteHistorie).count() == 1


def test_die_zaehlung_wird_mitgefuehrt(client, graph):
    antwort = client.post(
        eingabe_url(graph, graph.schueler_b), data={"wert": "3.0"}, headers=HTMX
    )
    assert 'id="zaehler"' in antwort.text
    assert "2 von 2" in antwort.text


def test_abgewiesene_eingabe_speichert_nichts_und_sagt_es(client, session, graph):
    antwort = client.post(
        eingabe_url(graph, graph.schueler_b), data={"wert": "2.5"}, headers=HTMX
    )
    assert antwort.status_code == 400
    assert "keine gültige Note" in antwort.text
    assert session.query(Note).filter_by(schueler_id=graph.schueler_b.id).count() == 0


def test_eingabe_fuer_einen_nicht_teilnehmer_wird_abgewiesen(client, session, graph):
    from app.services.verwaltung import setze_teilnahme

    setze_teilnahme(session, graph.kurs, graph.schueler_b, False)
    session.commit()

    antwort = client.post(
        eingabe_url(graph, graph.schueler_b), data={"wert": "3.0"}, headers=HTMX
    )
    assert antwort.status_code == 400
    assert session.query(Note).filter_by(schueler_id=graph.schueler_b.id).count() == 0


def test_note_leeren(client, session, graph):
    antwort = client.post(
        eingabe_url(graph, graph.schueler_a), data={"wert": ""}, headers=HTMX
    )
    assert antwort.status_code == 200
    assert session.query(Note).count() == 0
    assert session.query(NoteHistorie).count() == 1


def test_sonderstatus_speichert_keinen_wert(client, session, graph):
    client.post(
        eingabe_url(graph, graph.schueler_b),
        data={"wert": "nicht_erbracht"},
        headers=HTMX,
    )
    note = session.query(Note).filter_by(schueler_id=graph.schueler_b.id).one()
    assert note.notenwert is None
    assert note.status == "nicht_erbracht"


def test_eingabe_funktioniert_auch_ohne_htmx(client, session, graph):
    """If JavaScript fails, the page reloads and shows the stored state."""
    antwort = client.post(eingabe_url(graph, graph.schueler_b), data={"wert": "4.0"})
    assert antwort.status_code == 200
    assert "2 von 2" in antwort.text
    assert session.query(Note).filter_by(schueler_id=graph.schueler_b.id).count() == 1


def test_leistung_anlegen_und_oeffnen(client, session, graph):
    antwort = client.post(
        f"/notengruppen/{graph.notengruppe.id}/leistungen",
        data={
            "bezeichnung": "2. Klassenarbeit",
            "datum": "2026-11-04",
            "gewicht": "2",
        },
    )
    assert antwort.status_code == 200
    assert "2. Klassenarbeit" in antwort.text
    assert "0 von 2" in antwort.text


def test_leistungsuebersicht_zeigt_die_notenzahl(client, graph):
    antwort = client.get(f"/kurse/{graph.kurs.id}/leistungen")
    assert antwort.status_code == 200
    assert "1. Klassenarbeit" in antwort.text
    assert "1 Noten" in antwort.text


def test_leistung_mit_noten_laesst_sich_nicht_loeschen(client, graph):
    antwort = client.post(f"/leistungen/{graph.leistung.id}/loeschen")
    assert antwort.status_code == 400
    assert "Noten daran hängen" in antwort.text


def test_leistung_bearbeiten(client, session, graph):
    antwort = client.post(
        f"/leistungen/{graph.leistung.id}",
        data={
            "bezeichnung": "1. Klassenarbeit (verschoben)",
            "datum": "2026-09-22",
            "gewicht": "1,5",
        },
    )
    assert antwort.status_code == 200
    session.expire_all()
    assert graph.leistung.bezeichnung == "1. Klassenarbeit (verschoben)"
    assert str(graph.leistung.gewicht) == "1.5"


def test_die_eingabemaske_laedt_das_hilfsskript(client, graph):
    antwort = client.get(f"/leistungen/{graph.leistung.id}")
    assert "/static/eingabe.js" in antwort.text
    assert client.get("/static/eingabe.js").status_code == 200


def test_ohne_javascript_gibt_es_einen_absendeknopf(client, graph):
    antwort = client.get(f"/leistungen/{graph.leistung.id}")
    assert "<noscript>" in antwort.text
