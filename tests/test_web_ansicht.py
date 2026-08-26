"""Class view, pupil view and search through the web layer (5.1, 5.2, 6)."""

from app.db.models import Schueler


def test_klassenansicht_zeigt_nur_aktive_schueler(client, session, graph):
    graph.schueler_b.ist_aktiv = False
    session.commit()

    antwort = client.get(f"/klassen/{graph.klasse.id}")
    assert antwort.status_code == 200
    assert "Öztürk" in antwort.text
    assert "Straßer" not in antwort.text


def test_startseite_verlinkt_die_klassenansicht(client, graph):
    """The link existed before the route did."""
    startseite = client.get("/")
    assert f'href="/klassen/{graph.klasse.id}"' in startseite.text
    assert client.get(f"/klassen/{graph.klasse.id}").status_code == 200


def test_sortierung_laesst_sich_umschalten_und_bleibt_erhalten(client, graph):
    ziel = f"/klassen/{graph.klasse.id}"

    nach_nachname = client.get(ziel).text
    assert nach_nachname.index("Öztürk") < nach_nachname.index("Straßer")

    antwort = client.post(
        "/einstellungen/sortierung", data={"sortierung": "vorname", "ziel": ziel}
    )
    assert antwort.status_code == 200
    nach_vorname = antwort.text
    # Änne before Bernd
    assert nach_vorname.index("Änne") < nach_vorname.index("Bernd")

    # And it survives a reload.
    assert client.get(ziel).text.index("Änne") < client.get(ziel).text.index("Bernd")


def test_namensanzeige_laesst_sich_umschalten(client, graph):
    ziel = f"/klassen/{graph.klasse.id}"
    assert "Öztürk, Änne" in client.get(ziel).text

    antwort = client.post(
        "/einstellungen/namensanzeige",
        data={"namensanzeige": "vorname_nachname", "ziel": ziel},
    )
    assert "Änne Öztürk" in antwort.text


def test_umschalter_leitet_nicht_auf_fremde_seiten(client, graph):
    """The target comes from a form field; an open redirect is not on offer."""
    antwort = client.post(
        "/einstellungen/sortierung",
        data={"sortierung": "vorname", "ziel": "https://example.invalid/"},
        follow_redirects=False,
    )
    assert antwort.headers["location"] == "/"


def test_unbekannte_sortierung_wird_abgewiesen(client, graph):
    antwort = client.post(
        "/einstellungen/sortierung", data={"sortierung": "geburtsdatum", "ziel": "/"}
    )
    assert antwort.status_code == 400
    assert "Unbekannte Sortierung" in antwort.text


def test_schueleransicht_zeigt_noten_und_ergebnisse(client, graph):
    antwort = client.get(f"/schueler/{graph.schueler_a.id}")
    assert antwort.status_code == 200
    assert "Deutsch" in antwort.text
    assert "1. Klassenarbeit" in antwort.text
    assert "Klassenarbeiten" in antwort.text
    assert "2026/27" in antwort.text
    assert "2 (berechnet 2,0)" in antwort.text


def test_schueleransicht_zeigt_tendenznoten_als_zeichen(client, session, graph):
    """Specification 4.1: the single grade 0.7 is shown as "1+"."""
    from decimal import Decimal

    graph.note.notenwert = Decimal("0.7")
    session.commit()

    antwort = client.get(f"/schueler/{graph.schueler_a.id}")
    assert "1+" in antwort.text
    # The raw value would show up like this if the filter were missing.
    assert "0.7" not in antwort.text
    # The calculated term average is a different thing and stays a decimal.
    assert "1 (berechnet 0,7)" in antwort.text


def test_foto_ohne_bild_liefert_404_statt_serverfehler(client, graph):
    """Every pupil is without a photo until the capture step exists."""
    antwort = client.get(f"/schueler/{graph.schueler_a.id}/foto")
    assert antwort.status_code == 404


def test_foto_wird_ausgeliefert_wenn_vorhanden(client, session, graph):
    from datetime import datetime

    graph.schueler_a.foto = b"\xff\xd8\xff\xdbnicht wirklich ein JPEG"
    graph.schueler_a.foto_geaendert_am = datetime(2026, 9, 1, 12, 0)
    session.commit()

    antwort = client.get(f"/schueler/{graph.schueler_a.id}/foto")
    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "image/jpeg"
    assert antwort.content.startswith(b"\xff\xd8")


def test_kachel_zeigt_initialen_ohne_foto(client, graph):
    antwort = client.get(f"/klassen/{graph.klasse.id}")
    assert "ÄÖ" in antwort.text
    assert f"/schueler/{graph.schueler_a.id}/foto" not in antwort.text


def test_unbekannter_schueler_ergibt_die_deutsche_404_seite(client):
    antwort = client.get("/schueler/999999")
    assert antwort.status_code == 404
    assert "nicht gefunden" in antwort.text


def test_suche_ueber_die_oberflaeche(client, graph):
    antwort = client.get("/suche", params={"q": "ozturk"})
    assert antwort.status_code == 200
    assert "Öztürk" in antwort.text
    assert f"/schueler/{graph.schueler_a.id}" in antwort.text


def test_suche_ohne_treffer_sagt_das(client, graph):
    antwort = client.get("/suche", params={"q": "Xylophon"})
    assert "Keine Treffer" in antwort.text


def test_leere_suche_listet_nicht_die_ganze_datenbank(client, graph):
    antwort = client.get("/suche")
    assert antwort.status_code == 200
    assert "Öztürk" not in antwort.text


def test_suchbegriff_wird_maskiert_ausgegeben(client, graph):
    antwort = client.get("/suche", params={"q": '<script>alert("x")</script>'})
    assert "<script>alert" not in antwort.text
    assert "&lt;script&gt;" in antwort.text


def test_namen_in_der_ansicht_werden_maskiert(client, session, graph):
    session.add(
        Schueler(klasse_id=graph.klasse.id, vorname="<b>Ärger</b>", nachname="Test")
    )
    session.commit()

    antwort = client.get(f"/klassen/{graph.klasse.id}")
    assert "<b>Ärger</b>" not in antwort.text
    assert "&lt;b&gt;Ärger&lt;/b&gt;" in antwort.text


# ---------------------------------------------------------------------------
# The two numbers and the marking of "arbeitet digital" (5.1, 3.1)
# ---------------------------------------------------------------------------


def test_die_klassenansicht_zeigt_beide_zahlen(client, session, graph):
    antwort = client.get(f"/klassen/{graph.klasse.id}")

    assert "Schüleranzahl" in antwort.text
    assert "Papiertiger" in antwort.text
    assert "<strong>2</strong>" in antwort.text


def test_die_kopienzahl_folgt_dem_merkmal(client, session, graph):
    """The number the teacher acts on has to move when the data moves."""
    graph.schueler_a.arbeitet_digital = True
    session.commit()

    antwort = client.get(f"/klassen/{graph.klasse.id}")

    # Two pupils, one of them digital: two heads, one copy.
    assert "Schüleranzahl <strong>2</strong>" in antwort.text
    assert "Papiertiger <strong>1</strong>" in antwort.text


def test_nur_die_kachel_eines_digitalen_schuelers_ist_markiert(client, session, graph):
    antwort = client.get(f"/klassen/{graph.klasse.id}")
    assert "digitalpunkt" not in antwort.text

    graph.schueler_a.arbeitet_digital = True
    session.commit()

    antwort = client.get(f"/klassen/{graph.klasse.id}")
    assert antwort.text.count("digitalpunkt") == 1
    assert "schuelerkachel digital" in antwort.text


def test_die_schueleransicht_fuehrt_in_die_verwaltung(client, graph):
    """The management page existed; the way into it did not (5.2)."""
    antwort = client.get(f"/schueler/{graph.schueler_a.id}")

    assert f'href="/verwaltung/schueler/{graph.schueler_a.id}"' in antwort.text
