"""The two numbers of a class (specification 5.1).

"Papiertiger" is the number of paper copies to bring to the lesson. The
teacher relies on it before entering the room, so it is worth its own tests:
a number that is only roughly right is worse than no number at all.
"""

from app.db.models import Schueler
from app.services.klasse import zahlen


def test_beide_zahlen_zaehlen_die_aktiven_schueler(session, graph):
    ergebnis = zahlen(session, graph.klasse)

    assert ergebnis.schueleranzahl == 2
    # Nobody works digitally yet, so everybody needs a copy.
    assert ergebnis.papiertiger == 2


def test_ein_digitaler_schueler_senkt_nur_die_kopienzahl(session, graph):
    graph.schueler_a.arbeitet_digital = True
    session.flush()

    ergebnis = zahlen(session, graph.klasse)

    assert ergebnis.schueleranzahl == 2
    assert ergebnis.papiertiger == 1


def test_ein_inaktiver_schueler_zaehlt_in_keiner_der_beiden_zahlen(session, graph):
    """He has left the class: he neither sits in the room nor needs a copy."""
    graph.schueler_b.ist_aktiv = False
    session.flush()

    ergebnis = zahlen(session, graph.klasse)

    assert ergebnis.schueleranzahl == 1
    assert ergebnis.papiertiger == 1


def test_ein_inaktiver_digitaler_schueler_verfaelscht_nichts(session, graph):
    graph.schueler_a.arbeitet_digital = True
    graph.schueler_a.ist_aktiv = False
    session.flush()

    ergebnis = zahlen(session, graph.klasse)

    assert ergebnis.schueleranzahl == 1
    assert ergebnis.papiertiger == 1


def test_alle_digital_heisst_keine_kopie(session, graph):
    for schueler in (graph.schueler_a, graph.schueler_b):
        schueler.arbeitet_digital = True
    session.flush()

    ergebnis = zahlen(session, graph.klasse)

    assert ergebnis.schueleranzahl == 2
    assert ergebnis.papiertiger == 0


def test_eine_klasse_ohne_schueler_meldet_null_und_null(session, graph):
    for schueler in list(graph.klasse.schueler):
        session.delete(schueler)
    session.flush()

    ergebnis = zahlen(session, graph.klasse)

    assert ergebnis.schueleranzahl == 0
    assert ergebnis.papiertiger == 0


def test_die_vorgabe_eines_neuen_schuelers_ist_papier(session, graph):
    """The cautious direction: too many copies costs paper, too few a lesson."""
    neuer = Schueler(klasse=graph.klasse, vorname="Neu", nachname="Zugang")
    session.add(neuer)
    session.flush()

    assert neuer.arbeitet_digital is False
    assert zahlen(session, graph.klasse).papiertiger == 3
