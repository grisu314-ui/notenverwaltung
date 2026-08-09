"""Column type for exact decimal storage on SQLite."""

from decimal import Decimal

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class DecimalText(TypeDecorator):
    """Stores ``Decimal`` values as their canonical string form.

    SQLite has no decimal type. SQLAlchemy's ``Numeric`` round-trips through
    ``float`` on this dialect and warns about it; for grade values and weights
    that is not acceptable. Storing the canonical string keeps every value
    bit-for-bit as it was entered.

    Deliberately accepted consequence: columns of this type cannot be compared,
    sorted or aggregated numerically in SQL, because the comparison would be
    lexicographic ('10.0' < '2.0'). All arithmetic happens in Python with
    ``Decimal`` in the grading module.

    ``float`` is rejected on binding rather than silently converted: an
    inexact value must not enter the database unnoticed.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return str(Decimal(value))
        raise TypeError(
            f"DecimalText erwartet Decimal, int oder None, nicht "
            f"{type(value).__name__}. Fließkommawerte sind nicht zulässig."
        )

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(value)
