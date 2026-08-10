"""Back up the database (specification 2, point 5).

Uses ``VACUUM INTO``, never a file copy. On a database in WAL mode a plain
``cp`` of the .db file produces an inconsistent snapshot -- in the worst case
one that does not contain the most recent commits at all. That is not a
theoretical risk: the test in ``tests/test_backup.py`` demonstrates a copy in
which a table written seconds earlier is missing entirely.

The source is opened read-only. Two things follow: the productive database
cannot be modified by a backup run, and a mistyped path fails instead of
silently creating an empty database.

Usage:

    NOTENVERWALTUNG_DB=/daten/notenverwaltung.db \\
        python scripts/backup.py /backups --aufbewahren 14
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import database_path  # noqa: E402

NAMENSMUSTER = "notenverwaltung-*.db"
ZEITFORMAT = "%Y-%m-%d-%H%M%S"
VORGABE_AUFBEWAHREN = 14


class BackupFehler(RuntimeError):
    """Anything that stops a backup from being made or verified."""


def _pruefe_kopie(ziel: Path) -> int:
    """Open the copy and read from it.

    A backup nobody reads is not a backup. This is the cheapest possible
    proof that the file is a usable database and not a truncated write.
    """
    kopie = sqlite3.connect(f"file:{ziel}?mode=ro", uri=True)
    try:
        ergebnis = kopie.execute("PRAGMA integrity_check").fetchone()
        if not ergebnis or ergebnis[0] != "ok":
            raise BackupFehler(
                f"Die Sicherung {ziel} ist beschädigt: {ergebnis and ergebnis[0]}"
            )
        verwaist = kopie.execute("PRAGMA foreign_key_check").fetchall()
        if verwaist:
            raise BackupFehler(
                f"Die Sicherung {ziel} enthält verwaiste Datensätze: {verwaist!r}"
            )
        return kopie.execute(
            "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0]
    finally:
        kopie.close()


def sichere(quelle: Path, zielverzeichnis: Path) -> Path:
    """Write one consistent snapshot and verify it. Returns its path."""
    if not quelle.exists():
        raise BackupFehler(f"Die Datenbank {quelle} gibt es nicht.")
    zielverzeichnis.mkdir(parents=True, exist_ok=True)

    ziel = zielverzeichnis / f"notenverwaltung-{datetime.now():{ZEITFORMAT}}.db"
    if ziel.exists():
        raise BackupFehler(f"Die Sicherung {ziel} gibt es bereits.")

    verbindung = sqlite3.connect(f"file:{quelle}?mode=ro", uri=True)
    try:
        # Bound parameter, no assembled SQL -- and VACUUM INTO also compacts.
        verbindung.execute("VACUUM INTO ?", (str(ziel),))
    except sqlite3.Error as fehler:
        raise BackupFehler(f"Die Sicherung ist fehlgeschlagen: {fehler}") from fehler
    finally:
        verbindung.close()

    _pruefe_kopie(ziel)
    return ziel


def raeume_auf(zielverzeichnis: Path, aufbewahren: int) -> list[Path]:
    """Remove all but the newest ``aufbewahren`` snapshots. Returns the deleted."""
    if aufbewahren < 1:
        raise BackupFehler("Es muss mindestens eine Sicherung aufbewahrt werden.")
    vorhanden = sorted(zielverzeichnis.glob(NAMENSMUSTER))
    zu_alt = vorhanden[:-aufbewahren] if len(vorhanden) > aufbewahren else []
    for datei in zu_alt:
        datei.unlink()
    return zu_alt


def main() -> int:
    zerleger = argparse.ArgumentParser(
        description="Sichert die Datenbank per VACUUM INTO."
    )
    zerleger.add_argument(
        "zielverzeichnis", type=Path, help="Verzeichnis für die Sicherungen"
    )
    zerleger.add_argument(
        "--aufbewahren",
        type=int,
        default=VORGABE_AUFBEWAHREN,
        help=f"Anzahl der Stände, die bleiben (Vorgabe {VORGABE_AUFBEWAHREN})",
    )
    argumente = zerleger.parse_args()

    quelle = database_path()
    try:
        ziel = sichere(quelle, argumente.zielverzeichnis)
        entfernt = raeume_auf(argumente.zielverzeichnis, argumente.aufbewahren)
    except BackupFehler as fehler:
        # Non-zero exit so cron reports it instead of failing quietly.
        print(f"Sicherung fehlgeschlagen: {fehler}", file=sys.stderr)
        return 1

    groesse = ziel.stat().st_size
    print(f"Gesichert nach {ziel} ({groesse // 1024} kB), geprüft.")
    if entfernt:
        print(f"{len(entfernt)} ältere Sicherung(en) entfernt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
