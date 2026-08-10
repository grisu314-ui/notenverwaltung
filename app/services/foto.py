"""Accepting a pupil photo (specification 7).

The image is **re-encoded** rather than passed through. That is what drops
embedded metadata and any content smuggled into an otherwise valid file, and
it is the one place in this application where data from outside is parsed.

Nothing the client claims is trusted: neither the content type it announces
nor the file name it sends. The file name is not used at all -- the result is
stored as a BLOB, so no client-supplied string ever reaches a path.
"""

import logging
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.fehler import Verwaltungsfehler

logger = logging.getLogger(__name__)

# Specification 7: the client sends at most 512x512 as JPEG ~80, which is well
# under 100 kB. Two megabytes leaves room for a client that resized badly and
# still rejects anything that is plainly not a portrait.
GRENZE_BYTES = 2 * 1024 * 1024

# A 20 kB PNG can unpack to gigapixels. The header is read before any pixel is
# decoded, so this stops a decompression bomb before it costs memory.
GRENZE_PIXEL = 40_000_000

MAX_KANTE = 512
QUALITAET = 80
ERLAUBTE_FORMATE = {"JPEG", "PNG"}

WEISS = (255, 255, 255)


def _mit_weissem_grund(bild: Image.Image) -> Image.Image:
    """Flatten transparency onto white instead of onto black.

    A straight RGBA-to-RGB conversion turns every transparent pixel black,
    which on a portrait means a black frame.
    """
    if bild.mode not in ("RGBA", "LA", "P", "PA"):
        return bild.convert("RGB")
    mit_alpha = bild.convert("RGBA")
    grund = Image.new("RGB", mit_alpha.size, WEISS)
    grund.paste(mit_alpha, mask=mit_alpha.split()[-1])
    return grund


def verarbeite(rohdaten: bytes) -> bytes:
    """Check, rotate, shrink and re-encode an uploaded image.

    Returns JPEG bytes ready to be stored. Raises :class:`Verwaltungsfehler`
    with a German message for anything that does not pass.
    """
    if not rohdaten:
        raise Verwaltungsfehler("Es wurde keine Bilddatei übertragen.")
    if len(rohdaten) > GRENZE_BYTES:
        raise Verwaltungsfehler(
            f"Das Bild ist größer als {GRENZE_BYTES // (1024 * 1024)} MB und wurde "
            "nicht angenommen."
        )

    try:
        with Image.open(BytesIO(rohdaten)) as bild:
            # Image.open reads the header only, so format and size are known
            # before a single pixel is decoded.
            if bild.format not in ERLAUBTE_FORMATE:
                raise Verwaltungsfehler(
                    "Es werden nur JPEG- und PNG-Bilder angenommen."
                )
            breite, hoehe = bild.size
            if breite * hoehe > GRENZE_PIXEL:
                raise Verwaltungsfehler(
                    "Das Bild hat zu viele Bildpunkte und wurde nicht angenommen."
                )

            # Apply the orientation before the metadata is discarded, otherwise
            # a photo taken in portrait ends up lying on its side.
            gedreht = ImageOps.exif_transpose(bild) or bild
            fertig = _mit_weissem_grund(gedreht)
            fertig.thumbnail((MAX_KANTE, MAX_KANTE), Image.Resampling.LANCZOS)

            ziel = BytesIO()
            # No exif argument: the re-encoded image carries no metadata.
            fertig.save(ziel, format="JPEG", quality=QUALITAET, optimize=True)
            return ziel.getvalue()
    except Verwaltungsfehler:
        raise
    except UnidentifiedImageError as fehler:
        logger.info("Upload war kein lesbares Bild: %s", fehler)
        raise Verwaltungsfehler(
            "Die Datei ist kein lesbares Bild."
        ) from fehler
    except Image.DecompressionBombError as fehler:
        logger.warning("Dekomprimierungsbombe abgewiesen: %s", fehler)
        raise Verwaltungsfehler(
            "Das Bild hat zu viele Bildpunkte und wurde nicht angenommen."
        ) from fehler
    except OSError as fehler:
        # Truncated or damaged file -- logged, never swallowed.
        logger.warning("Bild konnte nicht verarbeitet werden: %s", fehler)
        raise Verwaltungsfehler(
            "Das Bild konnte nicht verarbeitet werden. Bitte erneut aufnehmen."
        ) from fehler
