"""The sixteen canonical grade values of specification 4.1, and rounding.

Free of any database or web dependency on purpose: this is the part of the
application whose errors do not surface until a wrong grade is on a report,
so it has to be testable without a running application.

Rounding rules, both decided by the operator and both deviating from 4.4:

* Calculated values carry **one** decimal place, not the two named in 4.4.
* A tie always goes to the better grade, i.e. the numerically smaller value.
  4.4 names commercial rounding (2.50 to 3) as its default; here 2.50 gives 2.

There is no conversion of a calculated average back to a Tendenznote: no view
shows one. The table below is used for entering and displaying single grades.
"""

from decimal import ROUND_HALF_DOWN, Decimal

# Specification 4.1. Tendencies exist from 1+ to 5-; the grade 6 has none.
# U+2212 MINUS SIGN, as in the specification.
_TABELLE: tuple[tuple[str, str], ...] = (
    ("1+", "0.7"),
    ("1", "1.0"),
    ("1−", "1.3"),
    ("2+", "1.7"),
    ("2", "2.0"),
    ("2−", "2.3"),
    ("3+", "2.7"),
    ("3", "3.0"),
    ("3−", "3.3"),
    ("4+", "3.7"),
    ("4", "4.0"),
    ("4−", "4.3"),
    ("5+", "4.7"),
    ("5", "5.0"),
    ("5−", "5.3"),
    ("6", "6.0"),
)

ANZEIGE_JE_NOTENWERT: dict[Decimal, str] = {
    Decimal(wert): anzeige for anzeige, wert in _TABELLE
}
NOTENWERT_JE_ANZEIGE: dict[str, Decimal] = {
    anzeige: Decimal(wert) for anzeige, wert in _TABELLE
}

NOTENWERTE: tuple[Decimal, ...] = tuple(NOTENWERT_JE_ANZEIGE.values())

KLEINSTER_NOTENWERT = NOTENWERTE[0]
GROESSTER_NOTENWERT = NOTENWERTE[-1]


class UngueltigeNoteError(ValueError):
    """A value that is not one of the sixteen canonical grade values."""


def ist_gueltiger_notenwert(wert: Decimal) -> bool:
    """True for the sixteen values of 4.1, regardless of scale (1.0 == 1.00)."""
    return wert in ANZEIGE_JE_NOTENWERT


def pruefe_notenwert(wert: Decimal) -> Decimal:
    """Return the value, or raise if it is not a canonical grade value."""
    if not ist_gueltiger_notenwert(wert):
        raise UngueltigeNoteError(
            f"{wert} ist keine gültige Note. Zulässig sind die Werte aus "
            "Abschnitt 4.1 (1+ bis 6)."
        )
    return wert


def als_anzeige(wert: Decimal) -> str:
    """Grade value as it is shown: 0.7 becomes "1+", never "0,7"."""
    try:
        return ANZEIGE_JE_NOTENWERT[wert]
    except KeyError:
        raise UngueltigeNoteError(
            f"{wert} ist keine gültige Note und kann nicht angezeigt werden."
        ) from None


def aus_anzeige(text: str) -> Decimal:
    """Grade value from its display form.

    A plain hyphen is accepted for the minus sign, because that is what a
    keyboard produces.
    """
    bereinigt = text.strip().replace("-", "−")
    try:
        return NOTENWERT_JE_ANZEIGE[bereinigt]
    except KeyError:
        raise UngueltigeNoteError(f"'{text}' ist keine gültige Note.") from None


def als_dezimalanzeige(wert: Decimal) -> str:
    """A calculated value in German notation with one decimal: "2,6"."""
    return f"{runde_auf_anzeige(wert):f}".replace(".", ",")


def runde_auf_anzeige(wert: Decimal) -> Decimal:
    """Round a calculated value to one decimal place, ties to the better grade.

    ROUND_HALF_DOWN rounds a tie towards zero, which for grade values -- always
    positive -- is the smaller and therefore better grade: 1.75 gives 1.7.
    """
    return wert.quantize(Decimal("0.1"), rounding=ROUND_HALF_DOWN)


def ganze_notenstufe(wert: Decimal) -> int:
    """The whole grade 1 to 6 derived from a calculated value (4.4, 4.5).

    Derived from the value as displayed, so that the shown number and the
    shown grade can never contradict each other. Ties go to the better grade:
    2.50 gives 2, 2.51 gives 3.

    Raises for a value outside the range the grade table can produce -- a
    weighted mean of valid grades can never leave it, so such a value means a
    defect and must not be papered over.
    """
    if not KLEINSTER_NOTENWERT <= wert <= GROESSTER_NOTENWERT:
        raise UngueltigeNoteError(
            f"{wert} liegt außerhalb des Notenbereichs "
            f"{KLEINSTER_NOTENWERT} bis {GROESSTER_NOTENWERT}."
        )
    gerundet = runde_auf_anzeige(wert)
    return int(gerundet.quantize(Decimal("1"), rounding=ROUND_HALF_DOWN))
