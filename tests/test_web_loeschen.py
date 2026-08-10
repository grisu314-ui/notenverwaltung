"""The two-step delete route (specification 11)."""

from decimal import Decimal

from app.clock import utc_now
from app.db.models import Schueler, Schuljahr
from app.enums import NoteStatus
from app.services import noten as notendienst


def _mit_foto_und_note(session, graph):
    graph.schueler_a.foto = b"nicht wirklich ein Bild"
    graph.schueler_a.foto_geaendert_am = utc_now()
    notendienst.setze_note(
        session, graph.leistung, graph.schueler_a, NoteStatus.GEWERTET, Decimal("2.0")
    )
    session.commit()


# ---------------------------------------------------------------------------
# The confirmation page
# ---------------------------------------------------------------------------


def test_die_bestaetigungsseite_nennt_zahlen_und_die_sicherungen(client, session, graph):
    _mit_foto_und_note(session, graph)

    antwort = client.get(f"/verwaltung/loeschen/schueler/{graph.schueler_a.id}")

    assert antwort.status_code == 200
    assert "Änne Öztürk" in antwort.text
    assert "Noten" in antwort.text
    assert "Foto" in antwort.text
    assert "Sicherungen" in antwort.text
    assert "rückgängig" in antwort.text
    # Nothing has happened yet.
    assert session.query(Schueler).count() == 2


def test_die_bestaetigungsseite_eines_schuljahres_nennt_seine_klassen(client, graph):
    antwort = client.get(f"/verwaltung/loeschen/schuljahre/{graph.schuljahr.id}")

    assert antwort.status_code == 200
    assert "2026/27" in antwort.text
    assert "Klassen" in antwort.text
    assert "Schüler" in antwort.text


def test_ein_unbekannter_datensatz_ergibt_die_deutsche_404_seite(client):
    antwort = client.get("/verwaltung/loeschen/schueler/9999")
    assert antwort.status_code == 404
    assert "nicht gefunden" in antwort.text

    antwort = client.get("/verwaltung/loeschen/schuljahre/9999")
    assert antwort.status_code == 404


def test_die_schuelerseite_verlinkt_die_loeschfunktion(client, graph):
    antwort = client.get(f"/verwaltung/schueler/{graph.schueler_a.id}")
    assert f"/verwaltung/loeschen/schueler/{graph.schueler_a.id}" in antwort.text


def test_die_schuljahrseite_verlinkt_die_loeschfunktion(client, graph):
    antwort = client.get(f"/verwaltung/schuljahre/{graph.schuljahr.id}")
    assert f"/verwaltung/loeschen/schuljahre/{graph.schuljahr.id}" in antwort.text


# ---------------------------------------------------------------------------
# Executing it
# ---------------------------------------------------------------------------


def test_ein_falsch_getippter_name_loescht_nichts(client, session, graph):
    _mit_foto_und_note(session, graph)

    antwort = client.post(
        f"/verwaltung/loeschen/schueler/{graph.schueler_a.id}",
        data={"bestaetigung": "Anne Ötztürk"},
    )

    assert antwort.status_code == 400
    assert "Es wurde nichts gelöscht." in antwort.text
    assert session.query(Schueler).count() == 2


def test_ein_leeres_bestaetigungsfeld_loescht_nichts(client, session, graph):
    antwort = client.post(
        f"/verwaltung/loeschen/schueler/{graph.schueler_a.id}",
        data={"bestaetigung": ""},
    )

    assert antwort.status_code == 400
    assert session.query(Schueler).count() == 2


def test_der_richtige_name_loescht_den_schueler(client, session, graph):
    _mit_foto_und_note(session, graph)

    antwort = client.post(
        f"/verwaltung/loeschen/schueler/{graph.schueler_a.id}",
        data={"bestaetigung": "Änne Öztürk"},
    )

    assert antwort.status_code == 200  # after the redirect to the class
    assert "Gelöscht." in antwort.text
    assert [s.nachname for s in session.query(Schueler).all()] == ["Straßer"]


def test_der_name_darf_ohne_umlautpunkte_getippt_werden(client, session, graph):
    """Strict about deliberateness, forgiving about a phone keyboard."""
    antwort = client.post(
        f"/verwaltung/loeschen/schueler/{graph.schueler_a.id}",
        data={"bestaetigung": "Anne Ozturk"},
    )

    assert antwort.status_code == 200
    assert session.query(Schueler).count() == 1


def test_ein_gescheitertes_verdichten_wird_dem_nutzer_gesagt(
    client, session, graph, monkeypatch, caplog
):
    """The rows are gone, the bytes are not -- reporting plain success lies."""
    from sqlalchemy.exc import OperationalError

    from app.web.routers import loeschen as router

    def sperrt(_engine):
        raise OperationalError("VACUUM", {}, Exception("database is locked"))

    monkeypatch.setattr(router.loeschdienst, "verdichte", sperrt)

    with caplog.at_level("ERROR"):
        antwort = client.post(
            f"/verwaltung/loeschen/schueler/{graph.schueler_a.id}",
            data={"bestaetigung": "Änne Öztürk"},
        )

    assert antwort.status_code == 200
    assert "nicht verdichten" in antwort.text
    assert "Bytes stehen noch in der Datei" in antwort.text
    assert "Verdichten nach dem Löschen fehlgeschlagen" in caplog.text
    # The deletion itself stands.
    assert session.query(Schueler).count() == 1


def test_die_richtige_bezeichnung_loescht_das_schuljahr(client, session, graph):
    _mit_foto_und_note(session, graph)

    antwort = client.post(
        f"/verwaltung/loeschen/schuljahre/{graph.schuljahr.id}",
        data={"bestaetigung": "2026/27"},
    )

    assert antwort.status_code == 200
    assert "Gelöscht." in antwort.text
    assert session.query(Schuljahr).count() == 0
    assert session.query(Schueler).count() == 0


def test_eine_falsche_bezeichnung_loescht_kein_schuljahr(client, session, graph):
    antwort = client.post(
        f"/verwaltung/loeschen/schuljahre/{graph.schuljahr.id}",
        data={"bestaetigung": "2027/28"},
    )

    assert antwort.status_code == 400
    assert "2026/27" in antwort.text
    assert session.query(Schuljahr).count() == 1
