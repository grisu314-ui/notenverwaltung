"""The web foundation: routing, error handling, output encoding."""

import logging

from app.db.models import Klasse
from app.web.app import app


def test_startseite_zeigt_das_aktive_schuljahr(client, graph):
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "2026/27" in antwort.text
    assert "BFS 26a" in antwort.text


def test_startseite_ohne_aktives_schuljahr(client, session, graph):
    graph.schuljahr.ist_aktiv = False
    session.commit()

    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "Kein aktives Schuljahr" in antwort.text


def test_unbekannte_adresse_liefert_eine_deutsche_fehlerseite(client):
    antwort = client.get("/gibtesnicht")
    assert antwort.status_code == 404
    assert "Seite nicht gefunden" in antwort.text


def test_unerwarteter_fehler_wird_protokolliert_und_angezeigt(client, caplog):
    """No silent failure: logged with traceback and visible to the user."""

    @app.get("/kaputt-fuer-den-test")
    def kaputt():
        raise RuntimeError("absichtlich kaputt")

    with caplog.at_level(logging.ERROR):
        antwort = client.get("/kaputt-fuer-den-test")

    assert antwort.status_code == 500
    assert "Unerwarteter Fehler" in antwort.text
    assert "absichtlich kaputt" in caplog.text
    # The internal message is logged, not shown to the user.
    assert "absichtlich kaputt" not in antwort.text


def test_fehler_bei_htmx_anfrage_liefert_nur_einen_block(client):
    antwort = client.get("/gibtesnicht", headers={"HX-Request": "true"})
    assert antwort.status_code == 404
    assert "<html" not in antwort.text
    assert "Seite nicht gefunden" in antwort.text


def test_namen_werden_maskiert_ausgegeben(client, session, graph):
    """Names come from Excel imports; autoescaping has to stay on."""
    session.add(
        Klasse(schuljahr_id=graph.schuljahr.id, bezeichnung='<script>alert("x")</script>')
    )
    session.commit()

    antwort = client.get("/")
    assert "<script>alert" not in antwort.text
    assert "&lt;script&gt;" in antwort.text


def test_htmx_wird_lokal_ausgeliefert(client):
    """No external CDN: the file ships with the application."""
    antwort = client.get("/static/htmx.min.js")
    assert antwort.status_code == 200
    assert "htmx" in antwort.text[:200]


def test_stylesheet_wird_ausgeliefert(client):
    assert client.get("/static/stil.css").status_code == 200


def test_statische_dateien_tragen_eine_versionsmarke(client, graph):
    """Without it a browser keeps the stylesheet it already has.

    That is not cosmetic: a free seat of the seating plan is an empty element
    whose whole visible form comes from CSS. With a stale stylesheet the plan
    renders as a bare nested list -- seen in production on a phone that had
    used the application for weeks.
    """
    from app.web.gemeinsam import STATIKVERSION

    antwort = client.get(f"/klassen/{graph.klasse.id}")

    assert f"/static/stil.css?v={STATIKVERSION}" in antwort.text
    assert STATIKVERSION.isdigit() and STATIKVERSION != "0"


def test_htmx_bekommt_eine_zeitgrenze(client, graph):
    """A request that hangs has to become visible as a failure.

    Not every device reports a dropped connection: an Android phone keeps the
    request open in flight mode and sends it once the network returns. Without
    a limit the row sits on "speichert ..." indefinitely.
    """
    antwort = client.get(f"/klassen/{graph.klasse.id}")

    assert 'name="htmx-config"' in antwort.text
    assert '"timeout":30000' in antwort.text
