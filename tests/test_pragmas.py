"""Specification section 2: the pragmas must hold on every connection."""

from app.db.session import BUSY_TIMEOUT_MS, create_app_engine


def test_fremdschluessel_sind_eingeschaltet(engine):
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_wal_modus_ist_aktiv(engine):
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"


def test_busy_timeout_ist_gesetzt(engine):
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == BUSY_TIMEOUT_MS


def test_pragmas_gelten_auf_jeder_neuen_verbindung(engine):
    """Not just on the first one -- a pool hands out several over time."""
    for _ in range(3):
        with engine.connect() as connection:
            connection.detach()  # force a fresh DBAPI connection next time
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_fremdschluessel_lassen_sich_nur_fuer_migrationen_abschalten(db_url):
    engine = create_app_engine(db_url, enable_foreign_keys=False)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
    finally:
        engine.dispose()
