"""The seating plan service (specification 5.6).

The cases worth having are the ones where a seat and a pupil disagree: the
pupil who went inactive, the grid that shrank under an occupied seat, the
page that no longer matches the database.
"""

import pytest

from app.db.models import (
    MAX_RASTER,
    VORGABE_REIHEN,
    VORGABE_SITZE_JE_REIHE,
    Klasse,
    Schueler,
    Sitzplatz,
)
from app.services import sitzplan as dienst
from app.services.fehler import Verwaltungsfehler


def _plan(session, graph):
    return dienst.hole_oder_lege_an(session, graph.klasse)


def _platz(blatt, reihe, position):
    return blatt.reihen[reihe - 1].plaetze[position - 1]


def test_der_plan_entsteht_beim_ersten_oeffnen(session, graph):
    assert graph.klasse.sitzplan is None

    plan = _plan(session, graph)

    assert plan.reihen == VORGABE_REIHEN
    assert plan.sitze_je_reihe == VORGABE_SITZE_JE_REIHE
    assert dienst.hole_oder_lege_an(session, graph.klasse) is plan


def test_leerer_plan_zeigt_alle_schueler_als_ohne_platz(session, graph):
    blatt = dienst.blatt(session, graph.klasse)

    assert len(blatt.reihen) == VORGABE_REIHEN
    assert all(len(reihe.plaetze) == VORGABE_SITZE_JE_REIHE for reihe in blatt.reihen)
    assert blatt.anzahl_besetzt == 0
    # Sorted by surname: Öztürk before Straßer, Ö like O (specification 6).
    assert [s.nachname for s in blatt.ohne_platz] == ["Öztürk", "Straßer"]


def test_zuweisen_setzt_den_schueler_auf_den_platz(session, graph):
    plan = _plan(session, graph)

    dienst.setze_platz(session, plan, 2, 3, graph.schueler_a)
    blatt = dienst.blatt(session, graph.klasse)

    assert _platz(blatt, 2, 3).schueler is graph.schueler_a
    assert blatt.anzahl_besetzt == 1
    assert graph.schueler_a not in blatt.ohne_platz
    assert blatt.anzahl_ohne_platz == 1


def test_zuweisen_ausserhalb_des_rasters_wird_abgewiesen(session, graph):
    plan = _plan(session, graph)

    with pytest.raises(Verwaltungsfehler, match="außerhalb des Rasters"):
        dienst.setze_platz(session, plan, 6, 1, graph.schueler_a)


def test_zuweisen_eines_fremden_schuelers_wird_abgewiesen(session, graph):
    plan = _plan(session, graph)
    andere = Klasse(schuljahr=graph.schuljahr, bezeichnung="BFS 26b")
    fremder = Schueler(klasse=andere, vorname="Carla", nachname="Fremd")
    session.add(andere)
    session.flush()

    with pytest.raises(Verwaltungsfehler, match="nicht zu der Klasse"):
        dienst.setze_platz(session, plan, 1, 1, fremder)


def test_ein_inaktiver_schueler_bekommt_keinen_platz(session, graph):
    plan = _plan(session, graph)
    graph.schueler_a.ist_aktiv = False
    session.flush()

    with pytest.raises(Verwaltungsfehler, match="inaktiver Schüler"):
        dienst.setze_platz(session, plan, 1, 1, graph.schueler_a)


def test_ein_besetzter_platz_wird_nicht_stillschweigend_uebernommen(session, graph):
    """A page that no longer matches the database must not move anyone."""
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 1, 1, graph.schueler_a)

    with pytest.raises(Verwaltungsfehler, match="sitzt bereits"):
        dienst.setze_platz(session, plan, 1, 1, graph.schueler_b)

    blatt = dienst.blatt(session, graph.klasse)
    assert _platz(blatt, 1, 1).schueler is graph.schueler_a


def test_zweite_zuweisung_raeumt_den_bisherigen_platz(session, graph):
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 1, 1, graph.schueler_a)

    dienst.setze_platz(session, plan, 4, 5, graph.schueler_a)

    blatt = dienst.blatt(session, graph.klasse)
    assert _platz(blatt, 1, 1).ist_frei
    assert _platz(blatt, 4, 5).schueler is graph.schueler_a
    assert session.query(Sitzplatz).count() == 1


def test_derselbe_platz_fuer_denselben_schueler_bleibt_wie_er_ist(session, graph):
    plan = _plan(session, graph)
    platz = dienst.setze_platz(session, plan, 1, 1, graph.schueler_a)

    assert dienst.setze_platz(session, plan, 1, 1, graph.schueler_a) is platz
    assert session.query(Sitzplatz).count() == 1


def test_raeumen_gibt_den_platz_frei(session, graph):
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 1, 1, graph.schueler_a)

    assert dienst.raeume_platz(session, plan, 1, 1) is True
    assert dienst.raeume_platz(session, plan, 1, 1) is False

    blatt = dienst.blatt(session, graph.klasse)
    assert _platz(blatt, 1, 1).ist_frei
    assert graph.schueler_a in blatt.ohne_platz


def test_tauschen_vertauscht_zwei_besetzte_plaetze(session, graph):
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 1, 1, graph.schueler_a)
    dienst.setze_platz(session, plan, 3, 2, graph.schueler_b)

    dienst.tausche(session, plan, (1, 1), (3, 2))

    blatt = dienst.blatt(session, graph.klasse)
    assert _platz(blatt, 1, 1).schueler is graph.schueler_b
    assert _platz(blatt, 3, 2).schueler is graph.schueler_a


def test_tauschen_auf_einen_freien_platz_verschiebt(session, graph):
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 1, 1, graph.schueler_a)

    dienst.tausche(session, plan, (1, 1), (5, 6))

    blatt = dienst.blatt(session, graph.klasse)
    assert _platz(blatt, 1, 1).ist_frei
    assert _platz(blatt, 5, 6).schueler is graph.schueler_a
    assert session.query(Sitzplatz).count() == 1


def test_tauschen_zweier_freier_plaetze_wird_abgewiesen(session, graph):
    plan = _plan(session, graph)

    with pytest.raises(Verwaltungsfehler, match="nichts zu tauschen"):
        dienst.tausche(session, plan, (1, 1), (2, 2))


def test_raster_laesst_sich_unabhaengig_aendern(session, graph):
    plan = _plan(session, graph)

    dienst.setze_raster(session, plan, 3, 8)

    blatt = dienst.blatt(session, graph.klasse)
    assert len(blatt.reihen) == 3
    assert len(blatt.reihen[0].plaetze) == 8


@pytest.mark.parametrize(
    "reihen, sitze", [(0, 6), (5, 0), (MAX_RASTER + 1, 6), (5, MAX_RASTER + 1)]
)
def test_raster_ausserhalb_der_grenzen_wird_abgewiesen(session, graph, reihen, sitze):
    plan = _plan(session, graph)

    with pytest.raises(Verwaltungsfehler, match="zwischen 1 und 12"):
        dienst.setze_raster(session, plan, reihen, sitze)


def test_verkleinern_unter_einen_besetzten_platz_wird_abgewiesen(session, graph):
    """The rule that keeps the grid from quietly dropping someone (5.6)."""
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 5, 6, graph.schueler_a)

    with pytest.raises(Verwaltungsfehler) as fehler:
        dienst.setze_raster(session, plan, 4, 6)

    assert "Öztürk" in str(fehler.value)
    assert "Reihe 5, Platz 6" in str(fehler.value)
    assert plan.reihen == VORGABE_REIHEN


def test_ein_inaktiver_schueler_haelt_seinen_platz_frei(session, graph):
    """Deactivating is reversible here too: the row stays, the seat looks free."""
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 2, 2, graph.schueler_a)
    graph.schueler_a.ist_aktiv = False
    session.flush()

    blatt = dienst.blatt(session, graph.klasse)
    assert _platz(blatt, 2, 2).ist_frei
    assert graph.schueler_a not in blatt.ohne_platz
    assert session.query(Sitzplatz).count() == 1

    graph.schueler_a.ist_aktiv = True
    session.flush()
    assert _platz(dienst.blatt(session, graph.klasse), 2, 2).schueler is graph.schueler_a


def test_der_platz_eines_inaktiven_schuelers_ist_vergebbar(session, graph):
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 2, 2, graph.schueler_a)
    graph.schueler_a.ist_aktiv = False
    session.flush()

    dienst.setze_platz(session, plan, 2, 2, graph.schueler_b)

    blatt = dienst.blatt(session, graph.klasse)
    assert _platz(blatt, 2, 2).schueler is graph.schueler_b
    assert session.query(Sitzplatz).count() == 1


def test_ein_inaktiver_schueler_haelt_das_verkleinern_nicht_auf(session, graph):
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 5, 6, graph.schueler_a)
    graph.schueler_a.ist_aktiv = False
    session.flush()

    dienst.setze_raster(session, plan, 3, 4)

    assert plan.reihen == 3
    assert session.query(Sitzplatz).count() == 1


def test_wer_ausserhalb_des_rasters_sitzt_gilt_als_ohne_platz(session, graph):
    """Otherwise the pupil is on no seat and on no list -- invisible."""
    plan = _plan(session, graph)
    dienst.setze_platz(session, plan, 5, 6, graph.schueler_a)
    graph.schueler_a.ist_aktiv = False
    session.flush()
    dienst.setze_raster(session, plan, 3, 4)

    graph.schueler_a.ist_aktiv = True
    session.flush()

    blatt = dienst.blatt(session, graph.klasse)
    assert graph.schueler_a in blatt.ohne_platz
    assert blatt.anzahl_besetzt == 0
