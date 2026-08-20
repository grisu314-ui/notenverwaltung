"""The delete function (specification 11).

Two things are checked here that a normal deletion test would not check:

* the count shown on the confirmation page is the count that actually
  disappears -- a number that is merely plausible is worse than no number;
* the bytes leave the file. That is not what DELETE does, and it is not even
  what VACUUM does in WAL mode.
"""

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.clock import utc_now
from app.db.models import (
    Klasse,
    Kurs,
    Kursteilnahme,
    Leistung,
    Note,
    NoteHistorie,
    Notengruppe,
    Notenueberschreibung,
    Schueler,
    Schuljahr,
    Sitzplan,
    Sitzplatz,
)
from app.enums import Bezugszeitraum, NoteStatus, UeberschreibungQuelle
from app.services import loeschen as loeschdienst
from app.services import noten as notendienst
from app.services import sitzplan as sitzplandienst
from app.services import verwaltung

# Recognisable in a hex dump and long enough not to be mistaken for noise.
FOTOMARKE = b"FOTOMARKIERUNG-" * 200


def pfad_von(db_url: str) -> Path:
    return Path(db_url.replace("sqlite+pysqlite:///", ""))


def rohbytes(db_url: str) -> bytes:
    """Everything SQLite has on disk for this database, concatenated."""
    hauptdatei = pfad_von(db_url)
    teile = []
    for datei in (hauptdatei, Path(f"{hauptdatei}-wal"), Path(f"{hauptdatei}-shm")):
        if datei.exists():
            teile.append(datei.read_bytes())
    return b"".join(teile)


@pytest.fixture
def bestand(session, graph):
    """The graph fixture, filled up to a photo, a history and a fixed grade."""
    graph.schueler_a.foto = FOTOMARKE
    graph.schueler_a.foto_geaendert_am = utc_now()
    notendienst.setze_note(
        session, graph.leistung, graph.schueler_a, NoteStatus.GEWERTET, Decimal("1.3")
    )
    notendienst.setze_note(
        session, graph.leistung, graph.schueler_b, NoteStatus.NICHT_ERBRACHT
    )
    session.add(
        Notenueberschreibung(
            schueler_id=graph.schueler_a.id,
            kurs_id=graph.kurs.id,
            bezugszeitraum=Bezugszeitraum.HALBJAHR_1,
            notenwert=Decimal("2.0"),
            quelle=UeberschreibungQuelle.MANUELL,
        )
    )
    session.commit()
    return graph


def zeilen(session, modell, bedingung=None) -> int:
    frage = session.query(modell)
    return frage.filter(bedingung).count() if bedingung is not None else frage.count()


# ---------------------------------------------------------------------------
# The counts
# ---------------------------------------------------------------------------


def test_der_umfang_zaehlt_was_tatsaechlich_verschwindet(session, bestand):
    """A number on the confirmation page that is only roughly right is a lie."""
    umfang = loeschdienst.umfang_schueler(session, bestand.schueler_a)
    vorher = {
        modell: zeilen(session, modell)
        for modell in (Schueler, Note, NoteHistorie, Kursteilnahme, Notenueberschreibung)
    }

    loeschdienst.loesche_schueler(session, bestand.schueler_a)
    session.commit()

    gezaehlt = dict(umfang.posten)
    for modell, name in (
        (Schueler, "Schülerdatensatz"),
        (Note, "Noten"),
        (NoteHistorie, "Einträge der Änderungshistorie"),
        (Kursteilnahme, "Kursteilnahmen"),
        (Notenueberschreibung, "festgesetzte Noten"),
    ):
        tatsaechlich = vorher[modell] - zeilen(session, modell)
        assert gezaehlt[name] == tatsaechlich, name


def test_der_umfang_eines_schuljahres_zaehlt_alles_darunter(session, bestand):
    umfang = loeschdienst.umfang_schuljahr(session, bestand.schuljahr)
    posten = dict(umfang.posten)

    assert posten["Klassen"] == 1
    assert posten["Schüler"] == 2
    assert posten["Fotos"] == 1
    assert posten["Kurse"] == 1
    assert posten["Notengruppen"] == 1
    assert posten["Leistungen"] == 1
    assert posten["Noten"] == 2
    assert posten["Einträge der Änderungshistorie"] == 2
    assert posten["Kursteilnahmen"] == 2
    assert posten["festgesetzte Noten"] == 1
    assert umfang.gesamt == sum(posten.values())


def test_ein_leeres_schuljahr_meldet_nur_sich_selbst(session):
    schuljahr = verwaltung.lege_schuljahr_an(
        session, "2030/31", date(2030, 8, 1), date(2031, 7, 31)
    )
    session.commit()

    umfang = loeschdienst.umfang_schuljahr(session, schuljahr)
    assert umfang.gesamt == 1


def test_das_protokoll_nennt_zahlen_und_keine_namen(session, bestand, caplog):
    """A log line naming the pupil would keep what the deletion removes."""
    with caplog.at_level("WARNING"):
        loeschdienst.loesche_schueler(session, bestand.schueler_a)
        session.commit()

    protokoll = "\n".join(eintrag.getMessage() for eintrag in caplog.records)
    assert "endgültig gelöscht" in protokoll
    assert "Noten: 1" in protokoll
    assert "Öztürk" not in protokoll
    assert "Änne" not in protokoll


# ---------------------------------------------------------------------------
# What is left afterwards
# ---------------------------------------------------------------------------


def test_vom_geloeschten_schueler_bleibt_in_keiner_tabelle_eine_zeile(session, bestand):
    kennung = bestand.schueler_a.id
    loeschdienst.loesche_schueler(session, bestand.schueler_a)
    session.commit()

    # Asked of the database, not of the ORM: a cascade that did not fire would
    # otherwise stay invisible behind the identity map.
    for tabelle in (
        "schueler",
        "note",
        "note_historie",
        "notenueberschreibung",
        "sitzplatz",
    ):
        spalte = "id" if tabelle == "schueler" else "schueler_id"
        anzahl = session.execute(
            text(f"SELECT count(*) FROM {tabelle} WHERE {spalte} = :kennung"),
            {"kennung": kennung},
        ).scalar_one()
        assert anzahl == 0, tabelle
    assert (
        session.execute(
            text("SELECT count(*) FROM kursteilnahme WHERE schueler_id = :kennung"),
            {"kennung": kennung},
        ).scalar_one()
        == 0
    )


def test_der_mitschueler_bleibt_unangetastet(session, bestand):
    loeschdienst.loesche_schueler(session, bestand.schueler_a)
    session.commit()

    verbleibend = session.query(Schueler).all()
    assert [s.nachname for s in verbleibend] == ["Straßer"]
    assert zeilen(session, Note, Note.schueler_id == bestand.schueler_b.id) == 1
    assert zeilen(session, NoteHistorie, NoteHistorie.schueler_id == bestand.schueler_b.id) == 1
    # The assessment itself belongs to the course, not to the pupil.
    assert zeilen(session, Leistung) == 1


def test_ein_anderes_schuljahr_bleibt_beim_loeschen_unversehrt(session, bestand):
    anderes = verwaltung.lege_schuljahr_an(
        session, "2027/28", date(2027, 8, 1), date(2028, 7, 31)
    )
    klasse = verwaltung.lege_klasse_an(session, anderes, "BFS 27a")
    schueler = verwaltung.lege_schueler_an(session, klasse, "Lea", "Amrhein")
    kurs = verwaltung.lege_kurs_an(session, klasse, "Mathematik")
    gruppe = verwaltung.lege_notengruppe_an(
        session, kurs, anderes.halbjahre[0], "Klassenarbeiten", Decimal("50")
    )
    leistung = notendienst.lege_leistung_an(
        session, gruppe, "1. Klassenarbeit", date(2027, 9, 15), Decimal("1.0")
    )
    notendienst.setze_note(
        session, leistung, schueler, NoteStatus.GEWERTET, Decimal("2.0")
    )
    session.commit()

    loeschdienst.loesche_schuljahr(session, bestand.schuljahr)
    session.commit()

    assert [j.bezeichnung for j in session.query(Schuljahr).all()] == ["2027/28"]
    assert zeilen(session, Klasse) == 1
    assert zeilen(session, Kurs) == 1
    # The one created by hand plus the six default groups of the new course
    # (three per term, 3.1) -- all of them belong to the year that stays.
    assert zeilen(session, Notengruppe) == 1 + 6
    assert zeilen(session, Leistung) == 1
    assert zeilen(session, Note) == 1
    assert zeilen(session, NoteHistorie) == 1
    assert zeilen(session, Kursteilnahme) == 1
    assert zeilen(session, Schueler) == 1
    assert zeilen(session, Notenueberschreibung) == 0
    assert session.query(Schuljahr).one().halbjahre != []


# ---------------------------------------------------------------------------
# The bytes
# ---------------------------------------------------------------------------


def test_die_fotobytes_stehen_vor_dem_loeschen_in_der_datei(bestand, db_url):
    """The premise of the next two tests, stated rather than assumed."""
    assert FOTOMARKE in rohbytes(db_url)


def test_ein_delete_allein_entfernt_die_fotobytes_nicht(session, bestand, db_url):
    """Why this module exists: DELETE only unlinks the pages."""
    session.delete(bestand.schueler_a)
    session.commit()

    assert session.query(Schueler).count() == 1
    assert FOTOMARKE in rohbytes(db_url)


def test_vacuum_allein_laesst_die_fotobytes_im_wal_stehen(
    session, bestand, db_url, engine
):
    """The reason ``verdichte`` does two things instead of one.

    VACUUM rewrites the main file, but in WAL mode it does so *through* the
    -wal file, where the old content stays readable until a checkpoint. Had
    this been assumed rather than measured, "vollständig entfernt" would have
    been quietly false.
    """
    loeschdienst.loesche_schueler(session, bestand.schueler_a)
    session.commit()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as verbindung:
        verbindung.exec_driver_sql("VACUUM")

    hauptdatei = pfad_von(db_url)
    assert FOTOMARKE not in hauptdatei.read_bytes()
    assert FOTOMARKE in Path(f"{hauptdatei}-wal").read_bytes()


def test_nach_dem_verdichten_sind_die_fotobytes_aus_der_datei_verschwunden(
    session, bestand, db_url, engine
):
    loeschdienst.loesche_schueler(session, bestand.schueler_a)
    session.commit()
    loeschdienst.verdichte(engine)

    assert FOTOMARKE not in rohbytes(db_url)


def test_verdichten_laesst_die_uebrigen_daten_und_die_pragmas_in_ruhe(
    session, bestand, db_url, engine
):
    """VACUUM rebuilds the file; the result still has to be the same database."""
    loeschdienst.loesche_schueler(session, bestand.schueler_a)
    session.commit()
    loeschdienst.verdichte(engine)

    assert [s.nachname for s in session.query(Schueler).all()] == ["Straßer"]
    with engine.connect() as verbindung:
        assert verbindung.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert verbindung.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1

    # Readable as a database from outside, i.e. not left half-rewritten.
    kopie = sqlite3.connect(f"file:{pfad_von(db_url)}?mode=ro", uri=True)
    try:
        assert kopie.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        kopie.close()


# ---------------------------------------------------------------------------
# The seating plan (5.6) is part of what a deletion removes -- and of what the
# confirmation page counts. A number that leaves something out is a lie.
# ---------------------------------------------------------------------------


def test_der_umfang_eines_schuelers_zaehlt_seinen_sitzplatz(session, bestand):
    plan = sitzplandienst.hole_oder_lege_an(session, bestand.klasse)
    sitzplandienst.setze_platz(session, plan, 1, 1, bestand.schueler_a)
    session.commit()

    umfang = loeschdienst.umfang_schueler(session, bestand.schueler_a)
    assert dict(umfang.posten)["Sitzplatzzuweisungen"] == 1

    loeschdienst.loesche_schueler(session, bestand.schueler_a)
    session.commit()

    assert zeilen(session, Sitzplatz) == 0
    # The plan itself belongs to the class and stays.
    assert zeilen(session, Sitzplan) == 1


def test_der_umfang_eines_schuljahres_zaehlt_plan_und_plaetze(session, bestand):
    plan = sitzplandienst.hole_oder_lege_an(session, bestand.klasse)
    sitzplandienst.setze_platz(session, plan, 1, 1, bestand.schueler_a)
    sitzplandienst.setze_platz(session, plan, 1, 2, bestand.schueler_b)
    session.commit()

    posten = dict(loeschdienst.umfang_schuljahr(session, bestand.schuljahr).posten)
    assert posten["Sitzpläne"] == 1
    assert posten["Sitzplatzzuweisungen"] == 2

    loeschdienst.loesche_schuljahr(session, bestand.schuljahr)
    session.commit()

    assert zeilen(session, Sitzplan) == 0
    assert zeilen(session, Sitzplatz) == 0
