"""Search across the whole database (specification 5.2).

Deliberately not done with SQL ``LIKE``. SQLite's ``LIKE`` ignores case only
for ASCII and knows nothing about German letters, so "ozturk" would never find
"Öztürk" and "STRASSER" would never find "Straßer".

Instead the pupils are loaded and filtered in Python with the same
normalisation the sorting uses. At a few hundred pupils that is the correct
solution, not the lazy one: the photo column is deferred and does not come
along, so this is a few hundred short rows. The alternative would be either
wrong (``LIKE``) or an extra normalised column, i.e. a denormalisation without
a measured reason.
"""

from sqlalchemy.orm import Session

from app.db.models import Schueler
from app.services.sorting import vereinfacht


def suche_schueler(session: Session, begriff: str) -> list[Schueler]:
    """Pupils whose name contains the term -- all classes, all school years.

    Inactive pupils are included: a former pupil's grades have to stay
    findable. An empty term returns nothing rather than everything.
    """
    gesucht = vereinfacht(begriff.strip())
    if not gesucht:
        return []

    return [
        schueler
        for schueler in session.query(Schueler).all()
        if gesucht in vereinfacht(f"{schueler.vorname} {schueler.nachname}")
        or gesucht in vereinfacht(f"{schueler.nachname} {schueler.vorname}")
    ]
