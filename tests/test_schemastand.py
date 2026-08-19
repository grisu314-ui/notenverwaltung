"""The start-up check that refuses an outstanding migration."""

from pathlib import Path

from scripts.schemastand import erwarteter_stand, ist_aktuell, vorhandener_stand


def test_eine_migrierte_datenbank_gilt_als_aktuell(db_url):
    assert ist_aktuell(db_url) is True
    assert vorhandener_stand(db_url) == erwarteter_stand()


def test_eine_leere_datei_gilt_nicht_als_aktuell(tmp_path):
    leer = tmp_path / "leer.db"
    leer.touch()
    assert ist_aktuell(f"sqlite+pysqlite:///{leer}") is False
    assert vorhandener_stand(f"sqlite+pysqlite:///{leer}") is None


def test_ein_alter_stand_wird_erkannt(db_url):
    """The case this exists for: the application is newer than the database."""
    import sqlite3

    pfad = Path(db_url.replace("sqlite+pysqlite:///", ""))
    verbindung = sqlite3.connect(pfad)
    verbindung.execute("UPDATE alembic_version SET version_num = '0000'")
    verbindung.commit()
    verbindung.close()

    assert ist_aktuell(db_url) is False
    assert vorhandener_stand(db_url) == "0000"


def test_der_erwartete_stand_kommt_aus_den_migrationen():
    """Pinned on purpose: a new migration has to be noticed here as well."""
    assert erwarteter_stand() == "0002"
