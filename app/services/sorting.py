"""German name sorting and name display (specification 6).

Plain ASCII sorting is not acceptable: it would place Öztürk after Zäpfel.
Sorted according to DIN 5007 variant 1, which is what the specification asks
for -- Ä sorts like A, ß like ss.

Written by hand rather than taken from a library. ``locale.strxfrm`` would
need a German locale to be present in the container and falls back to byte
order without it -- silently, and in exactly the way this is meant to avoid.
"""

import unicodedata

from app.enums import Namensanzeige, Sortierung

# Letters that carry no combining mark and therefore survive NFD unchanged.
# str.casefold() already turns ß into ss.
_ERSATZ = str.maketrans(
    {
        "ı": "i",
        "ł": "l",
        "đ": "d",
        "ø": "o",
        "æ": "ae",
        "œ": "oe",
        "ð": "d",
        "þ": "th",
    }
)


def vereinfacht(text: str) -> str:
    """Sort form of a string: lower case, without diacritics.

    Ä becomes a, ß becomes ss, Aydın becomes aydin.
    """
    zerlegt = unicodedata.normalize("NFD", text.casefold())
    ohne_akzente = "".join(z for z in zerlegt if not unicodedata.combining(z))
    return ohne_akzente.translate(_ERSATZ)


def namensschluessel(
    vorname: str, nachname: str, sortierung: Sortierung
) -> tuple[str, str, str, str]:
    """Sort key for a pupil.

    The original spellings are part of the key, so that two names with the
    same sort form -- Müller and Muller -- keep a stable, reproducible order
    instead of depending on the order they were read from the database.
    """
    if sortierung is Sortierung.NACHNAME:
        return (
            vereinfacht(nachname),
            vereinfacht(vorname),
            nachname,
            vorname,
        )
    return (
        vereinfacht(vorname),
        vereinfacht(nachname),
        vorname,
        nachname,
    )


def anzeigename(vorname: str, nachname: str, anzeige: Namensanzeige) -> str:
    if anzeige is Namensanzeige.NACHNAME_VORNAME:
        return f"{nachname}, {vorname}"
    return f"{vorname} {nachname}"
