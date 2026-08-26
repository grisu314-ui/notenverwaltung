"""The two numbers a class is judged by before the lesson (specification 5.1).

Both count the **active** pupils only, and both are shown in two places --
the class view and the seating plan. That is why they live here and not in a
router: two views computing the same number separately is how the two numbers
eventually disagree.

``papiertiger`` is the number of paper copies to bring. The teacher relies on
it before entering the room, so it is counted from the stored data and never
estimated.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Klasse, Schueler


@dataclass(frozen=True)
class Zahlen:
    """Headcount of a class and how many of them need paper."""

    schueleranzahl: int
    papiertiger: int


def zahlen(session: Session, klasse: Klasse) -> Zahlen:
    """Count the active pupils and those without a device of their own.

    An inactive pupil counts in neither number: they have left the class, so
    they neither sit in the room nor need a copy.

    Counted with a query rather than off ``klasse.schueler``. That collection
    still holds a row deleted and flushed in the same session, and this is a
    number the teacher acts on -- it has to describe the database, not the
    session's memory of it.
    """
    aktive = select(Schueler).where(
        Schueler.klasse_id == klasse.id, Schueler.ist_aktiv.is_(True)
    )
    schueleranzahl = session.execute(
        select(func.count()).select_from(aktive.subquery())
    ).scalar_one()
    papiertiger = session.execute(
        select(func.count()).select_from(
            aktive.where(Schueler.arbeitet_digital.is_(False)).subquery()
        )
    ).scalar_one()
    return Zahlen(schueleranzahl=schueleranzahl, papiertiger=papiertiger)
