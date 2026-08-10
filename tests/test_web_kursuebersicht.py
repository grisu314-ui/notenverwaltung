"""The course overview through the web layer (specification 5.3)."""

from datetime import date
from decimal import Decimal

from app.db.models import Leistung, Note, Notengruppe, Schueler
from app.enums import NoteStatus


def _zweites_halbjahr(session, graph):
    gruppe = Notengruppe(
        kurs=graph.kurs,
        halbjahr=graph.halbjahr_2,
        bezeichnung="Klassenarbeiten",
        gewicht=Decimal("50"),
        reihenfolge=1,
    )
    session.add(gruppe)
    leistung = Leistung(
        notengruppe=gruppe,
        bezeichnung="1. Arbeit HJ2",
        datum=date(2027, 3, 1),
        gewicht=Decimal("1.0"),
    )
    session.add(leistung)
    session.add(
        Note(
            leistung=leistung,
            schueler=graph.schueler_a,
            notenwert=Decimal("3.0"),
            status=NoteStatus.GEWERTET,
        )
    )
    session.commit()
    return leistung


def test_uebersicht_zeigt_matrix_und_spiegel(client, graph):
    antwort = client.get(f"/kurse/{graph.kurs.id}")
    assert antwort.status_code == 200
    assert "Klassenarbeiten" in antwort.text
    assert "1. Klassenarbeit" in antwort.text
    assert "Öztürk" in antwort.text
    assert "Notenspiegel je Leistung" in antwort.text


def test_gruppengewicht_ist_sichtbar(client, graph):
    """Explicitly required by 5.3."""
    antwort = client.get(f"/kurse/{graph.kurs.id}")
    assert "Gewicht 50" in antwort.text


def test_keine_gruppenmittel(client, graph):
    """Deviation from 5.3 decided by the operator."""
    antwort = client.get(f"/kurse/{graph.kurs.id}")
    assert "Gruppenmittel" not in antwort.text


def test_ergebnis_und_berechneter_wert_stehen_nebeneinander(client, graph):
    antwort = client.get(f"/kurse/{graph.kurs.id}")
    assert "(2,0)" in antwort.text


def test_umschaltung_zwischen_den_ansichten(client, session, graph):
    _zweites_halbjahr(session, graph)

    erstes = client.get(f"/kurse/{graph.kurs.id}?ansicht=halbjahr_1")
    assert "1. Klassenarbeit" in erstes.text
    assert "1. Arbeit HJ2" not in erstes.text

    zweites = client.get(f"/kurse/{graph.kurs.id}?ansicht=halbjahr_2")
    assert "1. Arbeit HJ2" in zweites.text
    assert "1. Klassenarbeit" not in zweites.text

    jahr = client.get(f"/kurse/{graph.kurs.id}?ansicht=jahr")
    assert "1. Klassenarbeit" in jahr.text
    assert "1. Arbeit HJ2" in jahr.text
    assert "Jahr" in jahr.text


def test_unbekannte_ansicht_faellt_zurueck(client, graph):
    antwort = client.get(f"/kurse/{graph.kurs.id}?ansicht=quartal")
    assert antwort.status_code == 200
    assert "1. Klassenarbeit" in antwort.text


def test_spaltenkopf_verlinkt_die_serieneingabe(client, graph):
    antwort = client.get(f"/kurse/{graph.kurs.id}")
    assert f'/leistungen/{graph.leistung.id}"' in antwort.text


def test_klassenansicht_verlinkt_die_uebersicht(client, graph):
    antwort = client.get(f"/klassen/{graph.klasse.id}")
    assert f'href="/kurse/{graph.kurs.id}"' in antwort.text


def test_sonderstatus_werden_gekennzeichnet(client, session, graph):
    session.add(
        Note(
            leistung=graph.leistung,
            schueler=graph.schueler_b,
            notenwert=None,
            status=NoteStatus.NICHT_ERBRACHT,
        )
    )
    session.commit()

    antwort = client.get(f"/kurse/{graph.kurs.id}")
    assert "n.e." in antwort.text
    assert "zählt als 6" in antwort.text


def test_unbekannter_kurs_ergibt_404(client):
    assert client.get("/kurse/999999").status_code == 404


def test_namen_werden_maskiert(client, session, graph):
    from app.db.models import Kursteilnahme

    schueler = Schueler(
        klasse_id=graph.klasse.id, vorname="<b>Ärger</b>", nachname="Test"
    )
    session.add(schueler)
    session.flush()
    session.add(Kursteilnahme(kurs=graph.kurs, schueler=schueler, ist_aktiv=True))
    session.commit()

    antwort = client.get(f"/kurse/{graph.kurs.id}")
    assert "<b>Ärger</b>" not in antwort.text
    assert "&lt;b&gt;Ärger&lt;/b&gt;" in antwort.text
