"""Check whether the database matches the migrations (specification 2).

Run before the application starts. If a migration is outstanding the
container does **not** start, and this says what to do.

The alternative -- migrating automatically on start -- would rebuild the
productive database, holding real names and photographs, without anyone
having rehearsed it on a copy. ``CLAUDE.md`` rules that out, and the decision
was confirmed by the operator.

Exit codes: 0 the database is current, 1 it is not or cannot be read.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.config import Config  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

from app.config import database_path, database_url  # noqa: E402
from app.db.session import create_app_engine  # noqa: E402

WURZEL = Path(__file__).resolve().parents[1]


def erwarteter_stand() -> str:
    config = Config(str(WURZEL / "alembic.ini"))
    config.set_main_option("script_location", str(WURZEL / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def vorhandener_stand(url: str) -> str | None:
    """Revision the database is on, or None if it has never been migrated."""
    engine = create_app_engine(url)
    try:
        with engine.connect() as verbindung:
            return MigrationContext.configure(verbindung).get_current_revision()
    finally:
        engine.dispose()


def ist_aktuell(url: str) -> bool:
    return vorhandener_stand(url) == erwarteter_stand()


def main() -> int:
    pfad = database_path()
    erwartet = erwarteter_stand()

    if not pfad.exists():
        print(
            f"Die Datenbank {pfad} gibt es nicht.\n"
            "Bei der Ersteinrichtung einmal anlegen:\n"
            "    alembic upgrade head\n"
            "Kommt stattdessen ein Rechtefehler, gehört das Verzeichnis dem "
            "falschen Benutzer — siehe README.",
            file=sys.stderr,
        )
        return 1

    try:
        vorhanden = vorhandener_stand(database_url(pfad))
    except Exception as fehler:  # noqa: BLE001 - reported, never swallowed
        print(f"Die Datenbank {pfad} ist nicht lesbar: {fehler}", file=sys.stderr)
        return 1

    if vorhanden == erwartet:
        return 0

    print(
        f"Die Datenbank ist auf Stand '{vorhanden}', erwartet wird '{erwartet}'.\n"
        "Die Anwendung startet nicht, damit nichts ungeprüft umgebaut wird.\n"
        "Erst sichern, dann migrieren — siehe README, Abschnitt „Aktualisieren“.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
