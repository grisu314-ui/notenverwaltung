"""The management routes (specification 5.5)."""

from app.db.models import Klasse, Kurs, Notengruppe, Schueler, Schuljahr


def test_verwaltungsseite_ist_erreichbar(client):
    antwort = client.get("/verwaltung")
    assert antwort.status_code == 200
    assert "Verwaltung" in antwort.text


def test_schuljahr_anlegen_erzeugt_beide_halbjahre(client, session):
    antwort = client.post(
        "/verwaltung/schuljahre",
        data={
            "bezeichnung": "2028/29",
            "beginn": "2028-08-01",
            "ende": "2029-07-31",
            "ist_aktiv": "true",
        },
    )
    assert antwort.status_code == 200  # after the redirect
    assert "Angelegt." in antwort.text
    assert "1. Halbjahr" in antwort.text
    assert "2. Halbjahr" in antwort.text

    schuljahr = session.query(Schuljahr).filter_by(bezeichnung="2028/29").one()
    assert len(schuljahr.halbjahre) == 2
    assert schuljahr.ist_aktiv is True


def test_doppelte_klassenbezeichnung_ergibt_eine_lesbare_meldung(client, graph):
    antwort = client.post(
        f"/verwaltung/klassen/schuljahr/{graph.schuljahr.id}",
        data={"bezeichnung": "BFS 26a", "notiz": ""},
    )
    assert antwort.status_code == 400
    assert "gibt es in diesem Schuljahr bereits" in antwort.text


def test_schuljahr_mit_ende_vor_beginn_ergibt_eine_lesbare_meldung(client):
    antwort = client.post(
        "/verwaltung/schuljahre",
        data={"bezeichnung": "Falsch", "beginn": "2029-08-01", "ende": "2028-07-31"},
    )
    assert antwort.status_code == 400
    assert "nach dem Beginn" in antwort.text


def test_klasse_anlegen_und_oeffnen(client, graph, session):
    antwort = client.post(
        f"/verwaltung/klassen/schuljahr/{graph.schuljahr.id}",
        data={"bezeichnung": "BFS 26b", "notiz": "Testklasse"},
    )
    assert antwort.status_code == 200
    assert "BFS 26b" in antwort.text
    assert session.query(Klasse).filter_by(bezeichnung="BFS 26b").count() == 1


def test_schueler_anlegen(client, graph, session):
    antwort = client.post(
        f"/verwaltung/schueler/klasse/{graph.klasse.id}",
        data={
            "vorname": "Jorinde",
            "nachname": "Osterloh",
            "listennummer": "7",
            "notiz": "",
        },
    )
    assert antwort.status_code == 200
    schueler = session.query(Schueler).filter_by(nachname="Osterloh").one()
    assert schueler.listennummer == 7
    assert schueler.ist_aktiv is True


def test_schueler_ohne_namen_wird_abgewiesen(client, graph):
    antwort = client.post(
        f"/verwaltung/schueler/klasse/{graph.klasse.id}",
        data={"vorname": "  ", "nachname": "Osterloh", "listennummer": "", "notiz": ""},
    )
    assert antwort.status_code == 400
    assert "dürfen nicht leer sein" in antwort.text


def test_schueler_deaktivieren_statt_loeschen(client, graph, session):
    antwort = client.post(
        f"/verwaltung/schueler/{graph.schueler_a.id}",
        data={
            "vorname": "Änne",
            "nachname": "Öztürk",
            "listennummer": "",
            "notiz": "",
            # checkbox not sent -> inactive
        },
    )
    assert antwort.status_code == 200
    session.expire_all()
    assert session.get(Schueler, graph.schueler_a.id).ist_aktiv is False
    # The grades stay.
    assert session.get(Schueler, graph.schueler_a.id).noten


def test_kurs_anlegen_traegt_die_teilnehmer_ein(client, graph, session):
    antwort = client.post(
        f"/verwaltung/kurse/klasse/{graph.klasse.id}",
        data={"fach": "Wirtschaftslehre", "notiz": ""},
    )
    assert antwort.status_code == 200
    kurs = session.query(Kurs).filter_by(fach="Wirtschaftslehre").one()
    assert {t.schueler_id for t in kurs.teilnahmen} == {
        graph.schueler_a.id,
        graph.schueler_b.id,
    }


def test_kursgewichte_akzeptieren_ein_komma(client, graph, session):
    antwort = client.post(
        f"/verwaltung/kurse/{graph.kurs.id}",
        data={
            "fach": "Deutsch",
            "notiz": "",
            "gewicht_halbjahr_1": "40,5",
            "gewicht_halbjahr_2": "59,5",
        },
    )
    assert antwort.status_code == 200
    session.expire_all()
    kurs = session.get(Kurs, graph.kurs.id)
    assert str(kurs.gewicht_halbjahr_1) == "40.5"


def test_kursgewicht_null_wird_abgewiesen(client, graph):
    antwort = client.post(
        f"/verwaltung/kurse/{graph.kurs.id}",
        data={
            "fach": "Deutsch",
            "notiz": "",
            "gewicht_halbjahr_1": "0",
            "gewicht_halbjahr_2": "100",
        },
    )
    assert antwort.status_code == 400
    assert "größer als 0" in antwort.text


def test_kursgewicht_als_text_wird_abgewiesen(client, graph):
    antwort = client.post(
        f"/verwaltung/kurse/{graph.kurs.id}",
        data={
            "fach": "Deutsch",
            "notiz": "",
            "gewicht_halbjahr_1": "viel",
            "gewicht_halbjahr_2": "50",
        },
    )
    assert antwort.status_code == 400
    assert "keine gültige Zahl" in antwort.text


def test_notengruppe_anlegen(client, graph, session):
    antwort = client.post(
        f"/verwaltung/notengruppen/kurs/{graph.kurs.id}",
        data={
            "halbjahr_id": str(graph.halbjahr_1.id),
            "bezeichnung": "Tests",
            "gewicht": "30",
            "reihenfolge": "2",
        },
    )
    assert antwort.status_code == 200
    gruppe = session.query(Notengruppe).filter_by(bezeichnung="Tests").one()
    assert str(gruppe.gewicht) == "30"


def test_notengruppe_mit_leistungen_laesst_sich_nicht_loeschen(client, graph):
    antwort = client.post(f"/verwaltung/notengruppen/{graph.notengruppe.id}/loeschen")
    assert antwort.status_code == 400
    assert "Löschfunktion" in antwort.text


def test_teilnahme_umschalten(client, graph, session):
    antwort = client.post(
        f"/verwaltung/teilnahmen/kurs/{graph.kurs.id}/schueler/{graph.schueler_b.id}",
        data={},  # checkbox not sent -> no longer taking part
    )
    assert antwort.status_code == 200
    session.expire_all()
    teilnahme = {t.schueler_id: t for t in graph.kurs.teilnahmen}
    assert teilnahme[graph.schueler_b.id].ist_aktiv is False
    assert teilnahme[graph.schueler_a.id].ist_aktiv is True


def test_unbekannter_datensatz_ergibt_404(client):
    assert client.get("/verwaltung/klassen/999999").status_code == 404


def test_umlaute_und_klammern_kommen_maskiert_an(client, graph):
    client.post(
        f"/verwaltung/schueler/klasse/{graph.klasse.id}",
        data={
            "vorname": "<b>Ärger</b>",
            "nachname": "Straßer",
            "listennummer": "",
            "notiz": "",
        },
    )
    antwort = client.get(f"/verwaltung/klassen/{graph.klasse.id}")
    assert "<b>Ärger</b>" not in antwort.text
    assert "&lt;b&gt;Ärger&lt;/b&gt;" in antwort.text


def test_unvollstaendiges_formular_ergibt_eine_deutsche_seite(client, graph):
    """FastAPI would answer with raw JSON otherwise."""
    antwort = client.post(
        f"/verwaltung/klassen/schuljahr/{graph.schuljahr.id}", data={"notiz": ""}
    )
    assert antwort.status_code == 400
    assert "Eingabe unvollständig" in antwort.text
    assert "application/json" not in antwort.headers.get("content-type", "")


def test_unvollstaendiges_datum_ergibt_eine_deutsche_seite(client):
    antwort = client.post(
        "/verwaltung/schuljahre",
        data={"bezeichnung": "2030/31", "beginn": "kein datum", "ende": "2031-07-31"},
    )
    assert antwort.status_code == 400
    assert "Eingabe unvollständig" in antwort.text
