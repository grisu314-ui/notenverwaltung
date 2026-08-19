"""The seating plan through the web layer (specification 5.6).

What these prove: the plan is read-only until the edit mode is on, every
mode renders without JavaScript, and a change is answered with the stored
state rather than with an optimistic one.

What they cannot prove: how the printed page looks, and what the browser
shows when the connection drops mid-request. Both are checked by hand.
"""

from app.db.models import Sitzplan, Sitzplatz

HTMX = {"HX-Request": "true"}


def url(graph) -> str:
    return f"/klassen/{graph.klasse.id}/sitzplan"


def test_der_plan_entsteht_beim_ersten_aufruf(client, session, graph):
    assert session.query(Sitzplan).count() == 0

    antwort = client.get(url(graph))

    assert antwort.status_code == 200
    assert "Tafel" in antwort.text
    assert session.query(Sitzplan).count() == 1


def test_die_klassenansicht_fuehrt_zum_sitzplan(client, graph):
    antwort = client.get(f"/klassen/{graph.klasse.id}")

    assert f'href="/klassen/{graph.klasse.id}/sitzplan"' in antwort.text


def test_die_ansicht_bietet_keine_zuweisung_an(client, graph):
    """Read-only until the edit mode is switched on: no stray reseating."""
    antwort = client.get(url(graph))

    assert "Plätze bearbeiten" in antwort.text
    assert "modus=zuweisen" not in antwort.text
    assert "Raster übernehmen" not in antwort.text


def test_der_bearbeitungsmodus_macht_die_plaetze_antippbar(client, graph):
    antwort = client.get(url(graph), params={"modus": "bearbeiten"})

    assert "modus=zuweisen&amp;reihe=1&amp;position=1" in antwort.text
    assert "Raster übernehmen" in antwort.text


def test_ein_freier_platz_bietet_die_nicht_zugewiesenen_an(client, graph):
    antwort = client.get(
        f"{url(graph)}/raster",
        params={"modus": "zuweisen", "reihe": 2, "position": 3},
        headers=HTMX,
    )

    assert "Reihe 2, Platz 3" in antwort.text
    assert "Öztürk" in antwort.text
    assert "Straßer" in antwort.text


def test_zuweisen_antwortet_mit_dem_gespeicherten_stand(client, session, graph):
    antwort = client.post(
        f"{url(graph)}/platz/2/3",
        data={"schueler_id": graph.schueler_a.id},
        headers=HTMX,
    )

    assert antwort.status_code == 200
    assert "gespeichert" in antwort.text
    platz = session.query(Sitzplatz).one()
    assert (platz.reihe, platz.position) == (2, 3)
    assert platz.schueler_id == graph.schueler_a.id


def test_ein_besetzter_platz_bietet_raeumen_und_tauschen(client, graph):
    client.post(
        f"{url(graph)}/platz/1/1", data={"schueler_id": graph.schueler_a.id}, headers=HTMX
    )

    antwort = client.get(
        f"{url(graph)}/raster",
        params={"modus": "menu", "reihe": 1, "position": 1},
        headers=HTMX,
    )

    assert "Platz räumen" in antwort.text
    assert "modus=tauschen" in antwort.text
    assert f'href="/schueler/{graph.schueler_a.id}"' in antwort.text


def test_raeumen_gibt_den_platz_frei(client, session, graph):
    client.post(
        f"{url(graph)}/platz/1/1", data={"schueler_id": graph.schueler_a.id}, headers=HTMX
    )

    antwort = client.post(f"{url(graph)}/platz/1/1/raeumen", headers=HTMX)

    assert antwort.status_code == 200
    assert session.query(Sitzplatz).count() == 0


def test_tauschen_vertauscht_zwei_plaetze(client, session, graph):
    client.post(
        f"{url(graph)}/platz/1/1", data={"schueler_id": graph.schueler_a.id}, headers=HTMX
    )
    client.post(
        f"{url(graph)}/platz/2/2", data={"schueler_id": graph.schueler_b.id}, headers=HTMX
    )

    antwort = client.post(
        f"{url(graph)}/tauschen",
        data={"von_reihe": 1, "von_position": 1, "nach_reihe": 2, "nach_position": 2},
        headers=HTMX,
    )

    assert antwort.status_code == 200
    belegung = {
        (platz.reihe, platz.position): platz.schueler_id
        for platz in session.query(Sitzplatz).all()
    }
    assert belegung == {
        (1, 1): graph.schueler_b.id,
        (2, 2): graph.schueler_a.id,
    }


def test_ein_besetzter_platz_wird_nicht_ueberschrieben(client, session, graph):
    """A page out of step with the database gets a German refusal, not a move."""
    client.post(
        f"{url(graph)}/platz/1/1", data={"schueler_id": graph.schueler_a.id}, headers=HTMX
    )

    antwort = client.post(
        f"{url(graph)}/platz/1/1",
        data={"schueler_id": graph.schueler_b.id},
        headers=HTMX,
    )

    assert antwort.status_code == 400
    assert "sitzt bereits" in antwort.text
    assert session.query(Sitzplatz).one().schueler_id == graph.schueler_a.id


def test_zuweisen_ausserhalb_des_rasters_wird_abgewiesen(client, session, graph):
    antwort = client.post(
        f"{url(graph)}/platz/9/9",
        data={"schueler_id": graph.schueler_a.id},
        headers=HTMX,
    )

    assert antwort.status_code == 400
    assert "außerhalb des Rasters" in antwort.text
    assert session.query(Sitzplatz).count() == 0


def test_das_raster_laesst_sich_aendern(client, session, graph):
    antwort = client.post(
        f"{url(graph)}/raster",
        data={"reihen": 3, "sitze_je_reihe": 8},
        follow_redirects=False,
    )

    assert antwort.status_code == 303
    plan = session.query(Sitzplan).one()
    assert (plan.reihen, plan.sitze_je_reihe) == (3, 8)


def test_verkleinern_unter_einen_besetzten_platz_nennt_den_schueler(
    client, session, graph
):
    client.post(
        f"{url(graph)}/platz/5/6", data={"schueler_id": graph.schueler_a.id}, headers=HTMX
    )

    antwort = client.post(
        f"{url(graph)}/raster", data={"reihen": 2, "sitze_je_reihe": 2}
    )

    assert antwort.status_code == 400
    assert "Öztürk" in antwort.text
    plan = session.query(Sitzplan).one()
    assert (plan.reihen, plan.sitze_je_reihe) == (5, 6)


def test_ein_unbekannter_modus_faellt_auf_die_ansicht_zurueck(client, graph):
    antwort = client.get(url(graph), params={"modus": "unfug"})

    assert antwort.status_code == 200
    assert "Plätze bearbeiten" in antwort.text


def test_ein_platz_ausserhalb_des_rasters_faellt_auf_die_bearbeitung_zurueck(
    client, graph
):
    """A link that was open while the grid shrank must not raise."""
    antwort = client.get(
        f"{url(graph)}/raster",
        params={"modus": "zuweisen", "reihe": 99, "position": 99},
        headers=HTMX,
    )

    assert antwort.status_code == 200
    assert "Reihe 99" not in antwort.text


def test_der_sitzplan_fasst_keine_note_an(client, session, graph):
    """Specification 5.6: a view onto pupils, never a way into a grade."""
    vorher = graph.note.notenwert

    client.post(
        f"{url(graph)}/platz/1/1", data={"schueler_id": graph.schueler_a.id}, headers=HTMX
    )
    seite = client.get(url(graph))

    session.refresh(graph.note)
    assert graph.note.notenwert == vorher
    # No way into the grade entry from here, and no grade on the page.
    assert "/leistungen/" not in seite.text
    assert "<select" not in seite.text
