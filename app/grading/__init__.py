"""Grade calculation (specification section 4).

Free of any database or web dependency, so the calculation is testable
without a running application.
"""

from app.grading.berechnung import (
    Einzelnote,
    Ergebnis,
    FehlenderNotenwertError,
    Notengruppe,
    UngueltigeGewichtungError,
    halbjahresnote,
    jahresnote,
)
from app.grading.notenwert import (
    UngueltigeNoteError,
    als_anzeige,
    als_dezimalanzeige,
    aus_anzeige,
    ganze_notenstufe,
    ist_gueltiger_notenwert,
    runde_auf_anzeige,
)

__all__ = [
    "Einzelnote",
    "Ergebnis",
    "FehlenderNotenwertError",
    "Notengruppe",
    "UngueltigeGewichtungError",
    "UngueltigeNoteError",
    "als_anzeige",
    "als_dezimalanzeige",
    "aus_anzeige",
    "ganze_notenstufe",
    "halbjahresnote",
    "ist_gueltiger_notenwert",
    "jahresnote",
    "runde_auf_anzeige",
]
