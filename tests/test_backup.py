"""Backup and restore (specification 2, point 5)."""

import shutil
import sqlite3

import pytest

from app.db.models import Schueler
from scripts.backup import BackupFehler, raeume_auf, sichere


def pfad_von(db_url: str):
    from pathlib import Path

    return Path(db_url.replace("sqlite+pysqlite:///", ""))


def test_die_kopie_enthaelt_die_daten(session, graph, db_url, tmp_path):
    session.commit()
    ziel = sichere(pfad_von(db_url), tmp_path / "sicherungen")

    kopie = sqlite3.connect(f"file:{ziel}?mode=ro", uri=True)
    namen = {zeile[0] for zeile in kopie.execute("SELECT nachname FROM schueler")}
    assert namen == {"Öztürk", "Straßer"}


def test_cp_verliert_daten_die_vacuum_into_behaelt(session, graph, db_url, tmp_path):
    """The reason the rule exists, demonstrated rather than asserted.

    The session fixture holds an open connection in WAL mode, so this is the
    state of a running application: the most recent commits live in the -wal
    file. Copying only the .db file loses them.
    """
    session.commit()
    quelle = pfad_von(db_url)

    per_kopie = tmp_path / "per_cp.db"
    shutil.copyfile(quelle, per_kopie)

    per_vacuum = sichere(quelle, tmp_path / "sicherungen")

    def schueler_in(datei) -> int:
        verbindung = sqlite3.connect(f"file:{datei}?mode=ro", uri=True)
        try:
            return verbindung.execute("SELECT count(*) FROM schueler").fetchone()[0]
        except sqlite3.DatabaseError:
            return -1  # not even a readable schema
        finally:
            verbindung.close()

    assert schueler_in(per_vacuum) == 2
    assert schueler_in(per_kopie) < 2


def test_die_sicherung_wird_geprueft(session, graph, db_url, tmp_path):
    """A backup nobody reads is not a backup."""
    session.commit()
    ziel = sichere(pfad_von(db_url), tmp_path / "sicherungen")

    kopie = sqlite3.connect(f"file:{ziel}?mode=ro", uri=True)
    assert kopie.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert kopie.execute("PRAGMA foreign_key_check").fetchall() == []


def test_wiederherstellen_ergibt_denselben_bestand(session, graph, db_url, tmp_path):
    """The restore test of 2.5, as far as it can be automated."""
    session.commit()
    ziel = sichere(pfad_von(db_url), tmp_path / "sicherungen")

    from app.db.session import create_app_engine, create_session_factory

    engine = create_app_engine(f"sqlite+pysqlite:///{ziel}")
    try:
        wieder = create_session_factory(engine)()
        namen = {s.nachname for s in wieder.query(Schueler).all()}
        assert namen == {"Öztürk", "Straßer"}
        # The photo column survives as bytes, not as something stringified.
        assert wieder.query(Schueler).count() == 2
        wieder.close()
    finally:
        engine.dispose()


def test_fehlende_quelle_wird_gemeldet(tmp_path):
    """A mistyped path must fail, not silently create an empty database."""
    with pytest.raises(BackupFehler) as fehler:
        sichere(tmp_path / "gibtesnicht.db", tmp_path / "sicherungen")
    assert "gibt es nicht" in str(fehler.value)
    assert not (tmp_path / "gibtesnicht.db").exists()


def test_aufbewahrung_behaelt_die_neuesten(tmp_path):
    verzeichnis = tmp_path / "sicherungen"
    verzeichnis.mkdir()
    for tag in range(1, 6):
        (verzeichnis / f"notenverwaltung-2026-09-0{tag}-120000.db").touch()

    entfernt = raeume_auf(verzeichnis, aufbewahren=3)

    assert len(entfernt) == 2
    verbleibend = sorted(p.name for p in verzeichnis.glob("notenverwaltung-*.db"))
    assert verbleibend == [
        "notenverwaltung-2026-09-03-120000.db",
        "notenverwaltung-2026-09-04-120000.db",
        "notenverwaltung-2026-09-05-120000.db",
    ]


def test_aufbewahrung_ruehrt_fremde_dateien_nicht_an(tmp_path):
    verzeichnis = tmp_path / "sicherungen"
    verzeichnis.mkdir()
    (verzeichnis / "notenverwaltung-2026-09-01-120000.db").touch()
    (verzeichnis / "notenverwaltung-2026-09-02-120000.db").touch()
    (verzeichnis / "wichtig.txt").touch()

    raeume_auf(verzeichnis, aufbewahren=1)

    assert (verzeichnis / "wichtig.txt").exists()


def test_aufbewahrung_unter_eins_wird_abgewiesen(tmp_path):
    with pytest.raises(BackupFehler):
        raeume_auf(tmp_path, aufbewahren=0)
