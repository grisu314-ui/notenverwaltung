"""Rules the database cannot enforce (specification 5.5, 3.1)."""

from datetime import date
from decimal import Decimal

import pytest

from app.db.models import Halbjahr, Kursteilnahme, Schuljahr
from app.services import verwaltung
from app.services.fehler import Verwaltungsfehler


def _schuljahr(session, bezeichnung="2026/27", ist_aktiv=False):
    return verwaltung.lege_schuljahr_an(
        session, bezeichnung, date(2026, 8, 1), date(2027, 7, 31), ist_aktiv
    )


def test_ein_schuljahr_bekommt_immer_beide_halbjahre(session):
    """Without both terms the year grade is uncomputable and nothing says why."""
    schuljahr = _schuljahr(session)
    session.commit()

    halbjahre = sorted(schuljahr.halbjahre, key=lambda h: h.nummer)
    assert [h.nummer for h in halbjahre] == [1, 2]
    assert halbjahre[0].beginn == date(2026, 8, 1)
    assert halbjahre[0].ende == date(2027, 1, 31)
    assert halbjahre[1].beginn == date(2027, 2, 1)
    assert halbjahre[1].ende == date(2027, 7, 31)


def test_ungewoehnlicher_zeitraum_erzeugt_trotzdem_gueltige_halbjahre():
    """The split date has to stay inside the range, else the CHECK would fire."""
    ende_hj1, beginn_hj2 = verwaltung.halbjahresgrenzen(
        date(2026, 3, 1), date(2026, 9, 30)
    )
    assert date(2026, 3, 1) < ende_hj1 < beginn_hj2 < date(2026, 9, 30)


def test_schuljahr_mit_ende_vor_beginn_wird_abgewiesen(session):
    with pytest.raises(Verwaltungsfehler):
        verwaltung.lege_schuljahr_an(
            session, "2026/27", date(2027, 8, 1), date(2026, 7, 31)
        )


def test_es_gibt_immer_hoechstens_ein_aktives_schuljahr(session):
    erstes = _schuljahr(session, "2025/26", ist_aktiv=True)
    zweites = verwaltung.lege_schuljahr_an(
        session, "2026/27", date(2026, 8, 1), date(2027, 7, 31), ist_aktiv=True
    )
    session.commit()

    assert session.query(Schuljahr).filter_by(ist_aktiv=True).count() == 1
    assert zweites.ist_aktiv is True
    assert erstes.ist_aktiv is False


def test_halbjahr_muss_im_schuljahr_liegen(session):
    schuljahr = _schuljahr(session)
    session.commit()
    halbjahr = schuljahr.halbjahre[0]

    with pytest.raises(Verwaltungsfehler) as fehler:
        verwaltung.aendere_halbjahr(
            session, halbjahr, date(2026, 1, 1), date(2026, 12, 31)
        )
    assert "innerhalb seines Schuljahres" in str(fehler.value)


def test_neuer_kurs_traegt_alle_aktiven_schueler_ein(session):
    """Explicitly required by 3.1."""
    schuljahr = _schuljahr(session)
    klasse = verwaltung.lege_klasse_an(session, schuljahr, "BFS 26a")
    aktiv = verwaltung.lege_schueler_an(session, klasse, "Änne", "Öztürk")
    inaktiv = verwaltung.lege_schueler_an(session, klasse, "Bernd", "Straßer")
    inaktiv.ist_aktiv = False
    session.flush()

    kurs = verwaltung.lege_kurs_an(session, klasse, "Deutsch")
    session.commit()

    teilnehmer = {teilnahme.schueler_id for teilnahme in kurs.teilnahmen}
    assert teilnehmer == {aktiv.id}


def test_ein_spaeter_angelegter_schueler_kommt_in_bestehende_kurse(session):
    schuljahr = _schuljahr(session)
    klasse = verwaltung.lege_klasse_an(session, schuljahr, "BFS 26a")
    kurs = verwaltung.lege_kurs_an(session, klasse, "Deutsch")
    schueler = verwaltung.lege_schueler_an(session, klasse, "Cem", "Aydın")
    session.commit()

    assert session.get(Kursteilnahme, (kurs.id, schueler.id)) is not None


def test_notengruppe_mit_fremdem_halbjahr_wird_abgewiesen(session):
    """No foreign key can express this; the error would falsify a term grade."""
    schuljahr = _schuljahr(session)
    fremdes = verwaltung.lege_schuljahr_an(
        session, "2027/28", date(2027, 8, 1), date(2028, 7, 31)
    )
    klasse = verwaltung.lege_klasse_an(session, schuljahr, "BFS 26a")
    kurs = verwaltung.lege_kurs_an(session, klasse, "Deutsch")
    session.flush()

    with pytest.raises(Verwaltungsfehler) as fehler:
        verwaltung.lege_notengruppe_an(
            session, kurs, fremdes.halbjahre[0], "Klassenarbeiten", Decimal("50")
        )
    assert "anderen Schuljahr" in str(fehler.value)


@pytest.mark.parametrize("gewicht", ["0", "-10"])
def test_unzulaessige_gewichte_werden_abgewiesen(session, gewicht):
    schuljahr = _schuljahr(session)
    klasse = verwaltung.lege_klasse_an(session, schuljahr, "BFS 26a")
    kurs = verwaltung.lege_kurs_an(session, klasse, "Deutsch")
    session.flush()

    with pytest.raises(Verwaltungsfehler):
        verwaltung.lege_notengruppe_an(
            session, kurs, schuljahr.halbjahre[0], "Tests", Decimal(gewicht)
        )


def test_teilnahme_laesst_sich_umschalten(session):
    schuljahr = _schuljahr(session)
    klasse = verwaltung.lege_klasse_an(session, schuljahr, "BFS 26a")
    schueler = verwaltung.lege_schueler_an(session, klasse, "Änne", "Öztürk")
    kurs = verwaltung.lege_kurs_an(session, klasse, "Deutsch")
    session.commit()

    verwaltung.setze_teilnahme(session, kurs, schueler, False)
    session.commit()
    assert session.get(Kursteilnahme, (kurs.id, schueler.id)).ist_aktiv is False

    verwaltung.setze_teilnahme(session, kurs, schueler, True)
    session.commit()
    assert session.get(Kursteilnahme, (kurs.id, schueler.id)).ist_aktiv is True


def test_teilnahme_nur_fuer_schueler_der_eigenen_klasse(session):
    schuljahr = _schuljahr(session)
    eine = verwaltung.lege_klasse_an(session, schuljahr, "BFS 26a")
    andere = verwaltung.lege_klasse_an(session, schuljahr, "BS EHK 26")
    fremder = verwaltung.lege_schueler_an(session, andere, "Lea", "Amrhein")
    kurs = verwaltung.lege_kurs_an(session, eine, "Deutsch")
    session.flush()

    with pytest.raises(Verwaltungsfehler):
        verwaltung.setze_teilnahme(session, kurs, fremder, True)


# --------------------------------------------------------------------------
# Deletion: only what is empty
# --------------------------------------------------------------------------


def test_notengruppe_mit_leistungen_laesst_sich_nicht_loeschen(session, graph):
    with pytest.raises(Verwaltungsfehler) as fehler:
        verwaltung.loesche_notengruppe(session, graph.notengruppe)
    assert "Leistungen" in str(fehler.value)


def test_leere_notengruppe_laesst_sich_loeschen(session, graph):
    leer = verwaltung.lege_notengruppe_an(
        session, graph.kurs, graph.halbjahr_1, "Tests", Decimal("30")
    )
    session.commit()

    verwaltung.loesche_notengruppe(session, leer)
    session.commit()
    assert leer not in graph.kurs.notengruppen


def test_kurs_mit_notengruppen_laesst_sich_nicht_loeschen(session, graph):
    with pytest.raises(Verwaltungsfehler):
        verwaltung.loesche_kurs(session, graph.kurs)


def test_klasse_mit_schuelern_laesst_sich_nicht_loeschen(session, graph):
    with pytest.raises(Verwaltungsfehler):
        verwaltung.loesche_klasse(session, graph.klasse)


# Schüler und Schuljahre werden nicht mehr hier gelöscht, sondern über die
# Löschfunktion aus Abschnitt 11 -- siehe tests/test_loeschen.py.
