"""Uploading and removing a photo through the web layer (specification 7)."""

from io import BytesIO

from PIL import Image

from app.db.models import Schueler


def bilddatei(groesse=(600, 400), format="PNG") -> bytes:
    bild = Image.new("RGB", groesse, (40, 120, 200))
    puffer = BytesIO()
    bild.save(puffer, format=format)
    return puffer.getvalue()


def test_hochladen_speichert_das_neu_kodierte_bild(client, session, graph):
    antwort = client.post(
        f"/verwaltung/schueler/{graph.schueler_a.id}/foto",
        files={"datei": ("foto.png", bilddatei(), "image/png")},
    )
    assert antwort.status_code == 200

    session.expire_all()
    schueler = session.get(Schueler, graph.schueler_a.id)
    assert schueler.foto is not None
    assert schueler.foto.startswith(b"\xff\xd8\xff")  # JPEG, obwohl PNG kam
    assert schueler.foto_geaendert_am is not None


def test_der_gemeldete_typ_wird_nicht_geglaubt(client, session, graph):
    """The client says PNG, the bytes are not an image. The bytes decide."""
    antwort = client.post(
        f"/verwaltung/schueler/{graph.schueler_a.id}/foto",
        files={"datei": ("foto.png", b"kein Bild, nur Text" * 20, "image/png")},
    )
    assert antwort.status_code == 400
    assert "kein lesbares Bild" in antwort.text

    session.expire_all()
    assert session.get(Schueler, graph.schueler_a.id).foto is None


def test_zu_grosse_datei_wird_abgewiesen(client, session, graph):
    antwort = client.post(
        f"/verwaltung/schueler/{graph.schueler_a.id}/foto",
        files={"datei": ("gross.jpg", b"\xff\xd8\xff" + b"x" * 3_000_000, "image/jpeg")},
    )
    assert antwort.status_code == 400
    session.expire_all()
    assert session.get(Schueler, graph.schueler_a.id).foto is None


def test_foto_wird_danach_ausgeliefert(client, graph):
    client.post(
        f"/verwaltung/schueler/{graph.schueler_a.id}/foto",
        files={"datei": ("foto.png", bilddatei(), "image/png")},
    )
    antwort = client.get(f"/schueler/{graph.schueler_a.id}/foto")
    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "image/jpeg"


def test_kachel_zeigt_danach_das_bild_statt_der_initialen(client, graph):
    client.post(
        f"/verwaltung/schueler/{graph.schueler_a.id}/foto",
        files={"datei": ("foto.png", bilddatei(), "image/png")},
    )
    antwort = client.get(f"/klassen/{graph.klasse.id}")
    assert f"/schueler/{graph.schueler_a.id}/foto" in antwort.text


def test_entfernen_setzt_beides_zurueck(client, session, graph):
    client.post(
        f"/verwaltung/schueler/{graph.schueler_a.id}/foto",
        files={"datei": ("foto.png", bilddatei(), "image/png")},
    )
    antwort = client.post(f"/verwaltung/schueler/{graph.schueler_a.id}/foto/loeschen")
    assert antwort.status_code == 200

    session.expire_all()
    schueler = session.get(Schueler, graph.schueler_a.id)
    assert schueler.foto is None
    assert schueler.foto_geaendert_am is None


def test_unbekannter_schueler_ergibt_404(client):
    antwort = client.post(
        "/verwaltung/schueler/999999/foto",
        files={"datei": ("foto.png", bilddatei(), "image/png")},
    )
    assert antwort.status_code == 404


def test_die_bearbeitung_laedt_das_zuschneideskript(client, graph):
    antwort = client.get(f"/verwaltung/schueler/{graph.schueler_a.id}")
    assert "/static/zuschnitt.js" in antwort.text
    assert 'capture="environment"' in antwort.text
    assert client.get("/static/zuschnitt.js").status_code == 200


def test_ohne_javascript_gibt_es_einen_direkten_upload(client, graph):
    antwort = client.get(f"/verwaltung/schueler/{graph.schueler_a.id}")
    assert "<noscript>" in antwort.text
    assert 'enctype="multipart/form-data"' in antwort.text
