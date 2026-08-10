"""Accepting a photo (specification 7).

Test images are generated with Pillow; nothing is loaded from outside.
"""

from io import BytesIO

import pytest
from PIL import Image

from app.services.fehler import Verwaltungsfehler
from app.services.foto import GRENZE_BYTES, MAX_KANTE, verarbeite

JPEG_KOPF = b"\xff\xd8\xff"


def bilddaten(
    groesse=(800, 600), format="JPEG", modus="RGB", farbe=(30, 90, 180), **speichern
) -> bytes:
    bild = Image.new(modus, groesse, farbe)
    puffer = BytesIO()
    bild.save(puffer, format=format, **speichern)
    return puffer.getvalue()


def geoeffnet(rohdaten: bytes) -> Image.Image:
    return Image.open(BytesIO(rohdaten))


def test_jpeg_wird_angenommen():
    ergebnis = verarbeite(bilddaten())
    assert ergebnis.startswith(JPEG_KOPF)


def test_png_wird_als_jpeg_gespeichert():
    """Whatever comes in, JPEG comes out -- the column holds one type only."""
    ergebnis = verarbeite(bilddaten(format="PNG"))
    assert ergebnis.startswith(JPEG_KOPF)
    assert geoeffnet(ergebnis).format == "JPEG"


def test_grosses_bild_wird_verkleinert():
    ergebnis = verarbeite(bilddaten(groesse=(2000, 1000)))
    breite, hoehe = geoeffnet(ergebnis).size
    assert breite <= MAX_KANTE and hoehe <= MAX_KANTE
    assert breite == MAX_KANTE  # the longer side ends up at the limit


def test_kleines_bild_wird_nicht_vergroessert():
    ergebnis = verarbeite(bilddaten(groesse=(200, 200)))
    assert geoeffnet(ergebnis).size == (200, 200)


def test_metadaten_fallen_weg():
    """Re-encoding is what drops them; the column must not carry EXIF."""
    bild = Image.new("RGB", (300, 300), (10, 10, 10))
    exif = bild.getexif()
    exif[271] = "Testkamera"  # Make
    puffer = BytesIO()
    bild.save(puffer, format="JPEG", exif=exif)
    assert b"Testkamera" in puffer.getvalue()

    ergebnis = verarbeite(puffer.getvalue())
    assert b"Testkamera" not in ergebnis
    assert not geoeffnet(ergebnis).getexif()


def test_exif_drehung_wird_angewendet():
    """Otherwise a portrait photo ends up lying on its side."""
    bild = Image.new("RGB", (400, 200), (200, 30, 30))
    exif = bild.getexif()
    exif[274] = 6  # rotate 90 degrees
    puffer = BytesIO()
    bild.save(puffer, format="JPEG", exif=exif)

    breite, hoehe = geoeffnet(verarbeite(puffer.getvalue())).size
    assert hoehe > breite  # landscape became portrait


def test_transparenz_wird_weiss_hinterlegt_statt_schwarz():
    daten = bilddaten(groesse=(50, 50), format="PNG", modus="RGBA", farbe=(0, 0, 0, 0))
    ergebnis = geoeffnet(verarbeite(daten)).convert("RGB")
    assert ergebnis.getpixel((25, 25)) == (255, 255, 255)


def test_keine_bilddatei_wird_abgewiesen():
    with pytest.raises(Verwaltungsfehler) as fehler:
        verarbeite(b"das ist ein Text und kein Bild" * 10)
    assert "kein lesbares Bild" in str(fehler.value)


def test_leere_uebertragung_wird_abgewiesen():
    with pytest.raises(Verwaltungsfehler):
        verarbeite(b"")


def test_zu_grosse_datei_wird_abgewiesen():
    with pytest.raises(Verwaltungsfehler) as fehler:
        verarbeite(b"\xff\xd8\xff" + b"x" * GRENZE_BYTES)
    assert "größer als" in str(fehler.value)


def test_nicht_erlaubtes_format_wird_abgewiesen():
    """GIF is a valid image and still not accepted."""
    with pytest.raises(Verwaltungsfehler) as fehler:
        verarbeite(bilddaten(groesse=(20, 20), format="GIF", modus="P"))
    assert "JPEG- und PNG" in str(fehler.value)


def test_dekomprimierungsbombe_wird_abgewiesen():
    """A small PNG that would unpack to gigapixels never gets decoded."""
    bombe = bilddaten(groesse=(20000, 20000), format="PNG", modus="1", farbe=0)
    assert len(bombe) < 200_000  # tiny on disk, 400 megapixels unpacked
    with pytest.raises(Verwaltungsfehler) as fehler:
        verarbeite(bombe)
    assert "Bildpunkte" in str(fehler.value)


def test_abgeschnittene_datei_wird_abgewiesen():
    daten = bilddaten()
    with pytest.raises(Verwaltungsfehler):
        verarbeite(daten[: len(daten) // 3])
