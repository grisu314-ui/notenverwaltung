# Notenverwaltung

Selbst gehostete Webanwendung zur Notenverwaltung für eine Lehrkraft.
Maßgeblich ist `notenverwaltung-spezifikation.md`, Arbeitsvorgaben stehen in
`CLAUDE.md`.

## Stand der Umsetzung

| Bereich | Spezifikation | Stand |
|---|---|---|
| Projektstruktur, Datenmodell | 3 | umgesetzt |
| Notenlogik | 4 | offen |
| Ansichten | 5, 6, 7 | offen |
| Export | 8 | offen |
| Backup-Skript, Docker | 2.5 | offen |
| Löschfunktion | 11 | Kaskaden im Schema vorhanden, Bedienung offen |

## Einrichtung

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Python 3.11 oder neuer (die Anwendung verwendet `enum.StrEnum`).

## Datenbank

Der Pfad zur SQLite-Datei kommt aus der Umgebungsvariablen
`NOTENVERWALTUNG_DB`; ohne sie wird `data/notenverwaltung.db` relativ zum
Arbeitsverzeichnis verwendet. Das ist die einzige Konfiguration der Anwendung.

Das Verzeichnis muss existieren — SQLite legt es nicht an und meldet sonst nur
`unable to open database file`:

```bash
mkdir -p data
```

Schema anlegen oder aktualisieren:

```bash
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/alembic upgrade head
```

Entwicklungsdaten einspielen (erfundene Namen, keine Fotos, bricht bei einer
nicht leeren Datenbank ab):

```bash
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/python scripts/seed_dev.py
```

**Entwicklung, Tests und Migrationsproben laufen ausschließlich gegen diese
Entwicklungsdatenbank.** Die produktive Datei enthält Klarnamen und Lichtbilder
und wird im Entwicklungsprozess nicht angefasst. Eine Migration wird vor dem
produktiven Lauf auf einer Kopie des produktiven Bestands durchgespielt — die
Kopie über `VACUUM INTO` erzeugen, nie über `cp` auf die laufende Datei.

## Tests

```bash
.venv/bin/pytest
```

Einzelne Bereiche:

```bash
.venv/bin/pytest tests/test_schema_constraints.py
.venv/bin/pytest tests/test_migration.py
```

Jeder Test baut sich seine eigene Datenbank über die Alembic-Migration auf;
`create_all()` wird nirgends verwendet, auch nicht im Test. Damit ist die
Migration bei jedem Testlauf mitgeprüft. Der Testlauf bricht ab, wenn
`NOTENVERWALTUNG_DB` gesetzt ist.

## Migrationen

Neue Migration erzeugen:

```bash
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/alembic revision --autogenerate -m "beschreibung"
```

Die erzeugte Datei **immer von Hand prüfen**, insbesondere `ondelete`-Angaben
und die Reihenfolge der Tabellen. `test_migration.py` prüft anschließend, dass
Modelle und Migration übereinstimmen.

Zwei Besonderheiten von SQLite sind in `migrations/env.py` berücksichtigt:

- `render_as_batch=True`, weil SQLite die meisten `ALTER TABLE` nicht kann und
  Alembic die Tabelle stattdessen neu aufbaut. Dafür braucht jeder Constraint
  einen Namen; die Namenskonvention in `app/db/base.py` stellt das sicher.
- Fremdschlüssel sind während der Migration abgeschaltet, weil ein
  Tabellenneuaufbau durch einen Zwischenzustand läuft, den ein aktiver
  Fremdschlüssel ablehnen würde. Nach der Migration prüft
  `PRAGMA foreign_key_check`; ein Fund lässt die Migration fehlschlagen.

## Abhängigkeiten aktualisieren

Versionen sind in `requirements.txt` gepinnt. Aktualisierungspfad:

```bash
.venv/bin/pip install --upgrade SQLAlchemy alembic
.venv/bin/pytest
.venv/bin/pip freeze | grep -E '^(SQLAlchemy|alembic)=='   # neue Pins übernehmen
```

Bei einem Fehlschlag die alten Pins wiederherstellen. Die Anwendung baut keine
ausgehenden Verbindungen auf; Aktualisierungen sind der einzige Netzzugriff und
finden nur beim Entwickeln statt.

## Offene Punkte mit Bezug zum Datenmodell

- **O-1** — die Prozentgrenzen des RLP-Standardschlüssels sind ungeklärt. Das
  Seed-Skript legt einen linearen Platzhalter mit Bestehensgrenze 50 % an und
  kennzeichnet ihn über `notenschluessel.ist_platzhalter`. Diese Werte gehören
  nicht in den produktiven Bestand, solange die Grenzen nicht festgelegt sind.
- **O-7** — die Gewichtung der beiden Halbjahre für die Jahresnote ist
  ungeklärt. `kurs.gewicht_halbjahr_1` und `_2` sind deshalb ohne Vorgabewert
  und dürfen nur gemeinsam gesetzt werden. Solange sie leer sind, gibt es keine
  gewichtete Jahresnote, sondern nur das reine Mittel.
