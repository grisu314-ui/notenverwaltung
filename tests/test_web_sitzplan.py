"""The seating plan through the web layer (specification 5.6).

What these prove: the plan is read-only until the edit mode is on, every
mode renders without JavaScript, and a change is answered with the stored
state rather than with an optimistic one.

What they cannot prove: how the printed page looks, and what the browser
shows when the connection drops mid-request. Both are checked by hand.
"""

import re
from datetime import date
from decimal import Decimal

import pytest

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


def test_das_umsetzen_laesst_jede_note_in_ruhe(client, session, graph):
    """Seating is seating. The one grade the plan writes is the participation
    grade, and it takes a chosen course and an explicit entry (5.6)."""
    vorher = graph.note.notenwert

    client.post(
        f"{url(graph)}/platz/1/1", data={"schueler_id": graph.schueler_a.id}, headers=HTMX
    )
    seite = client.get(url(graph))

    session.refresh(graph.note)
    assert graph.note.notenwert == vorher
    # No grades on the plan and no way into the serial entry from here.
    assert "/leistungen/" not in seite.text


# ---------------------------------------------------------------------------
# The participation grade of the day (5.6)
#
# "Today" is fixed for every test that stores a grade. The plan asks the
# clock, and a test that reads the real date stops working once the school
# year of the fixture is over (31.07.2027).
# ---------------------------------------------------------------------------

SCHULTAG = date(2026, 12, 1)
FERIENTAG = date(2027, 8, 15)


@pytest.fixture
def heute(monkeypatch):
    """Set today's date for the plan; returns a setter for other days."""

    def setze(tag):
        monkeypatch.setattr("app.web.routers.sitzplan.heute_lokal", lambda: tag)
        monkeypatch.setattr("app.services.sitzplan.heute_lokal", lambda: tag)

    setze(SCHULTAG)
    return setze



def _kurs_mit_vorgabegruppen(session, graph):
    from app.services import verwaltung

    kurs = verwaltung.lege_kurs_an(session, graph.klasse, "Politik")
    session.commit()
    return kurs


def _setze(client, graph, reihe, position, schueler, kurs=None):
    daten = {"schueler_id": schueler.id}
    if kurs is not None:
        daten["kurs"] = kurs.id
    return client.post(
        f"{url(graph)}/platz/{reihe}/{position}", data=daten, headers=HTMX
    )


def test_die_seite_bietet_die_kurse_der_klasse_an(client, session, graph):
    _kurs_mit_vorgabegruppen(session, graph)

    antwort = client.get(url(graph))

    assert "kein Kurs gewählt" in antwort.text
    assert "Politik" in antwort.text


def test_ohne_kurs_gibt_es_keine_mitarbeitsnote(client, session, graph):
    _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a)

    antwort = client.get(
        f"{url(graph)}/raster",
        params={"modus": "menu", "reihe": 1, "position": 1},
        headers=HTMX,
    )

    # The hint mentions it, the menu does not offer it.
    assert "modus=mitarbeit" not in antwort.text
    assert "oben den Kurs wählen" in antwort.text


def test_mit_kurs_bietet_der_platz_die_mitarbeitsnote_an(client, session, graph):
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)

    antwort = client.get(
        f"{url(graph)}/raster",
        params={"modus": "menu", "reihe": 1, "position": 1, "kurs": kurs.id},
        headers=HTMX,
    )

    assert "Mitarbeitsnote" in antwort.text
    assert "modus=mitarbeit" in antwort.text


def test_die_eingabemaske_zeigt_ganze_noten_und_ein_notizfeld(
    client, session, graph
):
    """On the plan a participation grade is a whole grade (5.6); the serial
    entry keeps all sixteen values."""
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)

    antwort = client.get(
        f"{url(graph)}/raster",
        params={"modus": "mitarbeit", "reihe": 1, "position": 1, "kurs": kurs.id},
        headers=HTMX,
    )

    for beschriftung in ("1", "2", "6"):
        assert f">{beschriftung}</option>" in antwort.text
    for tendenz in ("1+", "2−", "5+"):
        assert f">{tendenz}</option>" not in antwort.text
    assert 'name="notiz"' in antwort.text
    # A participation grade is always counted (5.6).
    assert "nicht erbracht" not in antwort.text


def test_eine_mitarbeitsnote_wird_gespeichert_und_bestaetigt(
    client, session, graph, heute
):
    from app.db.models import Note

    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)

    antwort = client.post(
        f"{url(graph)}/platz/1/1/mitarbeit",
        data={"kurs": kurs.id, "notenwert": "1.0", "notiz": "Trug die Diskussion."},
        headers=HTMX,
    )

    assert antwort.status_code == 200
    assert "gespeichert" in antwort.text
    assert "Öztürk" in antwort.text
    note = (
        session.query(Note)
        .filter(Note.schueler_id == graph.schueler_a.id, Note.notiz.isnot(None))
        .one()
    )
    assert note.notiz == "Trug die Diskussion."


def test_eine_mitarbeitsnote_auf_einen_leeren_platz_wird_abgewiesen(
    client, session, graph
):
    kurs = _kurs_mit_vorgabegruppen(session, graph)

    antwort = client.post(
        f"{url(graph)}/platz/1/1/mitarbeit",
        data={"kurs": kurs.id, "notenwert": "1.0"},
        headers=HTMX,
    )

    assert antwort.status_code == 400
    assert "sitzt niemand" in antwort.text


def test_ein_ungueltiger_notenwert_wird_abgewiesen(client, session, graph):
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)

    antwort = client.post(
        f"{url(graph)}/platz/1/1/mitarbeit",
        data={"kurs": kurs.id, "notenwert": "2.5"},
        headers=HTMX,
    )

    assert antwort.status_code == 400
    assert "keine gültige Note" in antwort.text


def test_ein_kurs_einer_fremden_klasse_wird_abgewiesen(client, session, graph):
    from app.db.models import Klasse
    from app.services import verwaltung

    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)
    andere = verwaltung.lege_klasse_an(session, graph.schuljahr, "BFS 26b")
    fremd = verwaltung.lege_kurs_an(session, andere, "Sport")
    session.commit()

    antwort = client.post(
        f"{url(graph)}/platz/1/1/mitarbeit",
        data={"kurs": fremd.id, "notenwert": "1.0"},
        headers=HTMX,
    )

    assert antwort.status_code == 400
    assert "kein Kurs gewählt" in antwort.text


def test_der_kurs_bleibt_beim_umsetzen_erhalten(client, session, graph):
    """And he survives as a usable parameter, not as double-escaped text:
    &amp;amp; would reach the server as a parameter called "amp;kurs"."""
    kurs = _kurs_mit_vorgabegruppen(session, graph)

    antwort = _setze(client, graph, 1, 1, graph.schueler_a, kurs)

    assert f"&amp;kurs={kurs.id}" in antwort.text
    assert "amp;amp;" not in antwort.text


# ---------------------------------------------------------------------------
# "arbeitet digital" on the plan (specification 5.6)
# ---------------------------------------------------------------------------


def test_der_sitzplan_zeigt_dieselben_zahlen_wie_die_klassenansicht(
    client, session, graph
):
    graph.schueler_a.arbeitet_digital = True
    session.commit()

    plan = client.get(url(graph))
    klasse = client.get(f"/klassen/{graph.klasse.id}")

    for zeile in ("Schüleranzahl <strong>2</strong>", "Papiertiger <strong>1</strong>"):
        assert zeile in plan.text, zeile
        assert zeile in klasse.text, zeile


def test_der_platz_eines_digitalen_schuelers_ist_markiert(client, session, graph):
    client.post(
        f"{url(graph)}/platz/1/1", data={"schueler_id": graph.schueler_a.id}, headers=HTMX
    )

    ohne = client.get(url(graph))
    assert "digitalpunkt" not in ohne.text

    graph.schueler_a.arbeitet_digital = True
    session.commit()

    mit = client.get(url(graph))
    assert "digitalpunkt" in mit.text
    assert "platz belegt digital" in mit.text


def test_die_markierung_haengt_nicht_allein_an_der_farbe(client, session, graph):
    """Colour alone carries no information, and print drops backgrounds.

    The dot is a character in the markup, so it survives both.
    """
    client.post(
        f"{url(graph)}/platz/1/1", data={"schueler_id": graph.schueler_a.id}, headers=HTMX
    )
    graph.schueler_a.arbeitet_digital = True
    session.commit()

    antwort = client.get(url(graph))

    assert "●" in antwort.text
    assert 'title="arbeitet digital"' in antwort.text


# ---------------------------------------------------------------------------
# The quick entry: a participation grade select under every pupil (5.6)
# ---------------------------------------------------------------------------


def _schnell(client, graph, schueler, kurs, notenwert, htmx=True):
    return client.post(
        f"{url(graph)}/mitarbeit/{schueler.id}",
        data={"kurs": kurs.id, "notenwert": notenwert},
        headers=HTMX if htmx else {},
        follow_redirects=False,
    )


def _noten_des_tages(session, schueler):
    from app.db.models import Leistung, Note

    session.expire_all()
    return (
        session.query(Note)
        .join(Leistung)
        .filter(Leistung.datum == SCHULTAG, Note.schueler_id == schueler.id)
        .all()
    )


def test_die_ansicht_bietet_die_schnelleingabe_an(client, session, graph, heute):
    kurs = _kurs_mit_vorgabegruppen(session, graph)

    antwort = client.get(url(graph), params={"kurs": kurs.id})

    assert "Mitarbeitsnoten" in antwort.text
    assert f"modus=noten&amp;kurs={kurs.id}" in antwort.text


def test_ohne_kurs_zeigt_die_schnelleingabe_keine_felder(client, session, graph, heute):
    _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a)

    antwort = client.get(url(graph), params={"modus": "noten"})

    assert "oben den Kurs wählen" in antwort.text
    assert 'class="mitarbeitsfeld' not in antwort.text


def test_unter_jedem_teilnehmer_steht_ein_feld(client, session, graph, heute):
    """Seated or not: a pupil without a seat is no pupil without a grade."""
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)

    antwort = client.get(url(graph), params={"modus": "noten", "kurs": kurs.id})

    assert f'id="mitarbeit-{graph.schueler_a.id}"' in antwort.text
    assert f'id="mitarbeit-{graph.schueler_b.id}"' in antwort.text
    feld = antwort.text.split(f'id="mitarbeit-{graph.schueler_a.id}"')[1].split("</select>")[0]
    angeboten = re.findall(r">([^<]*)</option>", feld)
    assert angeboten == ["–", "1", "2", "3", "4", "5", "6"]
    # Always counted (5.6), and nothing given yet.
    assert "nicht erbracht" not in antwort.text
    assert "✓" not in antwort.text


def test_in_der_schnelleingabe_fuehrt_kein_platz_weg(client, session, graph, heute):
    """A stray touch between two grades must not open the pupil's page."""
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)

    antwort = client.get(url(graph), params={"modus": "noten", "kurs": kurs.id})

    assert 'href="/schueler/' not in antwort.text
    assert "modus=zuweisen" not in antwort.text
    assert "Raster übernehmen" not in antwort.text
    assert "Fertig" in antwort.text


def test_wer_den_kurs_nicht_besucht_bekommt_kein_feld(client, session, graph, heute):
    from app.db.models import Kursteilnahme

    kurs = _kurs_mit_vorgabegruppen(session, graph)
    session.get(Kursteilnahme, (kurs.id, graph.schueler_b.id)).ist_aktiv = False
    session.commit()

    antwort = client.get(url(graph), params={"modus": "noten", "kurs": kurs.id})

    assert f'id="mitarbeit-{graph.schueler_a.id}"' in antwort.text
    assert f'id="mitarbeit-{graph.schueler_b.id}"' not in antwort.text
    assert "nicht im Kurs" in antwort.text


def test_eine_auswahl_wird_gespeichert_und_aus_dem_datensatz_bestaetigt(
    client, session, graph, heute
):
    kurs = _kurs_mit_vorgabegruppen(session, graph)

    antwort = _schnell(client, graph, graph.schueler_a, kurs, "2.0")

    assert antwort.status_code == 200
    assert f'id="mitarbeit-{graph.schueler_a.id}"' in antwort.text
    assert 'value="2.0" selected' in antwort.text
    assert "✓" in antwort.text
    [note] = _noten_des_tages(session, graph.schueler_a)
    assert note.notenwert == Decimal("2.0")
    assert note.leistung.bezeichnung == "Mitarbeit 01.12.2026"
    assert note.leistung.notengruppe.kurs_id == kurs.id


def test_die_heutige_note_steht_nach_dem_neuladen_im_feld(
    client, session, graph, heute
):
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _schnell(client, graph, graph.schueler_a, kurs, "2.0")

    antwort = client.get(url(graph), params={"modus": "noten", "kurs": kurs.id})

    assert 'value="2.0" selected' in antwort.text


def test_ausserhalb_der_schnelleingabe_zeigt_der_plan_keine_noten(
    client, session, graph, heute
):
    """5.6: the grade shows in the quick entry only, never in view or print."""
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)
    _schnell(client, graph, graph.schueler_a, kurs, "2.0")

    for modus in ("ansicht", "bearbeiten"):
        antwort = client.get(url(graph), params={"modus": modus, "kurs": kurs.id})
        assert 'class="mitarbeitsfeld' not in antwort.text, modus
        assert 'value="2.0" selected' not in antwort.text, modus


def test_eine_zweite_auswahl_aendert_die_note_und_die_historie(
    client, session, graph, heute
):
    from app.db.models import NoteHistorie

    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _schnell(client, graph, graph.schueler_a, kurs, "2.0")
    _schnell(client, graph, graph.schueler_a, kurs, "3.0")

    [note] = _noten_des_tages(session, graph.schueler_a)
    assert note.notenwert == Decimal("3.0")
    aktionen = [
        e.aktion
        for e in session.query(NoteHistorie)
        .filter_by(note_id=note.id)
        .order_by(NoteHistorie.id)
    ]
    assert aktionen == ["angelegt", "geaendert"]


def test_der_strich_nimmt_die_heutige_note_zurueck(client, session, graph, heute):
    from app.db.models import NoteHistorie

    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _schnell(client, graph, graph.schueler_a, kurs, "5.0")

    antwort = _schnell(client, graph, graph.schueler_a, kurs, "")

    assert antwort.status_code == 200
    assert "gelöscht" in antwort.text
    assert 'value="" selected' in antwort.text
    assert _noten_des_tages(session, graph.schueler_a) == []
    assert (
        session.query(NoteHistorie)
        .filter_by(schueler_id=graph.schueler_a.id, aktion="geloescht")
        .count()
        == 1
    )


def test_der_strich_ohne_note_aendert_nichts(client, session, graph, heute):
    kurs = _kurs_mit_vorgabegruppen(session, graph)

    antwort = _schnell(client, graph, graph.schueler_a, kurs, "")

    assert antwort.status_code == 200
    assert _noten_des_tages(session, graph.schueler_a) == []


def test_die_schnelleingabe_laesst_die_notiz_stehen(client, session, graph, heute):
    """The quick entry has no remark field; it must not wipe one given earlier."""
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)
    client.post(
        f"{url(graph)}/platz/1/1/mitarbeit",
        data={"kurs": kurs.id, "notenwert": "1.0", "notiz": "Trug die Diskussion."},
        headers=HTMX,
    )

    _schnell(client, graph, graph.schueler_a, kurs, "2.0")

    [note] = _noten_des_tages(session, graph.schueler_a)
    assert note.notenwert == Decimal("2.0")
    assert note.notiz == "Trug die Diskussion."


def test_das_platzmenue_ist_mit_der_heutigen_note_vorbelegt(
    client, session, graph, heute
):
    """A preset 3 would overwrite a 1- when only a remark is added later."""
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)
    client.post(
        f"{url(graph)}/platz/1/1/mitarbeit",
        data={"kurs": kurs.id, "notenwert": "1.3", "notiz": "Gute Frage."},
        headers=HTMX,
    )

    antwort = client.get(
        f"{url(graph)}/raster",
        params={"modus": "mitarbeit", "reihe": 1, "position": 1, "kurs": kurs.id},
        headers=HTMX,
    )

    assert 'value="1.3" selected' in antwort.text
    assert 'value="3.0" selected' not in antwort.text
    assert 'value="Gute Frage."' in antwort.text
    assert "Heute schon eingetragen: 1−" in antwort.text


def test_eine_gespeicherte_tendenz_bleibt_im_feld_sichtbar(
    client, session, graph, heute
):
    """The plan offers whole grades only, but a 2- stored today -- from the
    serial entry, say -- must not show as "–", as if there were no grade."""
    from app.services import sitzplan as dienst

    kurs = _kurs_mit_vorgabegruppen(session, graph)
    dienst.mitarbeitsnote(session, kurs, graph.schueler_a, Decimal("2.3"), datum=SCHULTAG)
    session.commit()

    antwort = client.get(url(graph), params={"modus": "noten", "kurs": kurs.id})

    feld = antwort.text.split(f'id="mitarbeit-{graph.schueler_a.id}"')[1].split("</select>")[0]
    assert re.findall(r">([^<]*)</option>", feld) == ["–", "1", "2", "2−", "3", "4", "5", "6"]
    assert 'value="2.3" selected' in feld
    # Only the stored one; no other Tendenz is offered.
    anderes = antwort.text.split(f'id="mitarbeit-{graph.schueler_b.id}"')[1].split("</select>")[0]
    assert "2−" not in anderes


def test_ohne_eigene_note_bleibt_das_platzmenue_auf_drei(client, session, graph, heute):
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    _setze(client, graph, 1, 1, graph.schueler_a, kurs)

    antwort = client.get(
        f"{url(graph)}/raster",
        params={"modus": "mitarbeit", "reihe": 1, "position": 1, "kurs": kurs.id},
        headers=HTMX,
    )

    assert 'value="3.0" selected' in antwort.text
    assert "Heute schon eingetragen" not in antwort.text


def test_ohne_gruppe_mitarbeit_nennt_der_plan_den_grund(client, session, graph, heute):
    """Said once above the grid, not thirty times after thirty taps."""
    from app.db.models import Notengruppe

    kurs = _kurs_mit_vorgabegruppen(session, graph)
    gruppe = (
        session.query(Notengruppe)
        .filter_by(kurs_id=kurs.id, halbjahr_id=graph.halbjahr_1.id, bezeichnung="Mitarbeit")
        .one()
    )
    gruppe.bezeichnung = "Mündlich"
    session.commit()

    seite = client.get(url(graph), params={"modus": "noten", "kurs": kurs.id})
    antwort = _schnell(client, graph, graph.schueler_a, kurs, "1.0")

    assert "keine Notengruppe „Mitarbeit“" in seite.text
    assert 'class="mitarbeitsfeld' not in seite.text
    assert antwort.status_code == 400
    assert "keine Notengruppe" in antwort.text


def test_in_den_ferien_gibt_es_keine_felder(client, session, graph, heute):
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    heute(FERIENTAG)

    seite = client.get(url(graph), params={"modus": "noten", "kurs": kurs.id})

    assert "In den Ferien" in seite.text
    assert 'class="mitarbeitsfeld' not in seite.text


def test_ein_schueler_einer_anderen_klasse_wird_abgewiesen(
    client, session, graph, heute
):
    from app.db.models import Schueler
    from app.services import verwaltung

    kurs = _kurs_mit_vorgabegruppen(session, graph)
    andere = verwaltung.lege_klasse_an(session, graph.schuljahr, "BFS 26b")
    fremd = Schueler(klasse=andere, vorname="Carla", nachname="Fremd")
    session.add(fremd)
    session.commit()

    antwort = _schnell(client, graph, fremd, kurs, "1.0")

    assert antwort.status_code == 400
    assert "kein aktiver Schüler dieser Klasse" in antwort.text


def test_ein_inaktiver_schueler_wird_abgewiesen(client, session, graph, heute):
    kurs = _kurs_mit_vorgabegruppen(session, graph)
    graph.schueler_a.ist_aktiv = False
    session.commit()

    antwort = _schnell(client, graph, graph.schueler_a, kurs, "1.0")

    assert antwort.status_code == 400
    assert _noten_des_tages(session, graph.schueler_a) == []


def test_ein_status_statt_einer_note_wird_abgewiesen(client, session, graph, heute):
    kurs = _kurs_mit_vorgabegruppen(session, graph)

    antwort = _schnell(client, graph, graph.schueler_a, kurs, "nicht_erbracht")

    assert antwort.status_code == 400
    assert "keine gültige Note" in antwort.text
    assert _noten_des_tages(session, graph.schueler_a) == []


def test_ohne_javascript_fuehrt_das_speichern_zurueck_in_die_schnelleingabe(
    client, session, graph, heute
):
    kurs = _kurs_mit_vorgabegruppen(session, graph)

    antwort = _schnell(client, graph, graph.schueler_a, kurs, "2.0", htmx=False)

    assert antwort.status_code == 303
    assert antwort.headers["location"] == (
        f"/klassen/{graph.klasse.id}/sitzplan?modus=noten&kurs={kurs.id}"
    )
    assert len(_noten_des_tages(session, graph.schueler_a)) == 1
