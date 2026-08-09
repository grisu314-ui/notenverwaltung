"""The migration is the only way the schema is ever created or changed."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db.base import Base
from app.db.session import create_app_engine

ERWARTETE_TABELLEN = {
    "einstellung",
    "halbjahr",
    "klasse",
    "kurs",
    "kursteilnahme",
    "leistung",
    "note",
    "note_historie",
    "notengruppe",
    "notenueberschreibung",
    "schueler",
    "schuljahr",
}


def _tabellen(connection) -> set[str]:
    rows = connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row[0] for row in rows} - {"alembic_version"}


def test_upgrade_legt_alle_tabellen_an(engine):
    with engine.connect() as connection:
        assert _tabellen(connection) == ERWARTETE_TABELLEN


def test_upgrade_hinterlaesst_keine_verwaisten_datensaetze(engine):
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []


def test_migration_und_modelle_stimmen_ueberein(engine):
    """Autogenerate finds nothing to do -- models and migration cannot drift."""
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "render_as_batch": True}
        )
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_entfernt_alle_tabellen(db_url, alembic_cfg):
    command.downgrade(alembic_cfg, "base")

    engine = create_app_engine(db_url)
    try:
        with engine.connect() as connection:
            assert _tabellen(connection) == set()
    finally:
        engine.dispose()
