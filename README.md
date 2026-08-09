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
| Punkteeingabe, Notenschlüssel | 4.2, 4.3, 5.4 | **wird nicht gebaut**, siehe unten |

## Bewusste Abweichung: keine Punkteeingabe

Noten werden ausschließlich direkt als Notenstufe mit Tendenz eingetragen
(1+ bis 6, die sechzehn Werte aus Abschnitt 4.1). Eine Umrechnung von Punkten
in Noten findet außerhalb dieser Anwendung statt. Entscheidung des
Auftraggebers, getroffen bei der Klärung des offenen Punktes O-1.

Daraus folgt:

- Es gibt keine Notenschlüssel-Entität, keine Prozentgrenzen, kein
  `max_punkte`, keine gespeicherten Punkte und keine Eingabeart. Abschnitt 4.2
  entfällt vollständig, 4.3 zur Hälfte, 5.4 verliert die Live-Anzeige der Note
  neben dem Punktefeld.
- **Von den zehn verbindlichen Testfällen aus Abschnitt 4.6 entfallen T-5, T-6
  und T-10 ersatzlos**, weil sie Punkteeingabe und Notenschlüsseländerung
  prüfen. Es verbleiben sieben Pflichtfälle: T-1 bis T-4 sowie T-7 bis T-9.
  Die Spezifikation ist in diesem Punkt nicht nachgeführt; maßgeblich ist diese
  Notiz.

Eine spätere Rückkehr zur Punkteeingabe ist möglich, kostet aber eine Migration
und den Nachbau der genannten Abschnitte.

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

Beide sind geklärt:

- **O-1** — entfällt. Es gibt keine Prozentgrenzen, weil es keine Punkteeingabe
  gibt (siehe oben).
- **O-7** — Gewichtung der beiden Halbjahre für die Jahresnote: 50/50, pro Kurs
  in `kurs.gewicht_halbjahr_1` und `_2` änderbar. Die Vorgabe steht als
  `VORGABE_GEWICHT_HALBJAHR` in `app/db/models.py`.

  Fachlicher Hinweis, damit er nicht verloren geht: Abschnitt 4.5 der
  Spezifikation weist darauf hin, dass die Schulordnung für die Jahresnote eine
  „stärkere Berücksichtigung der Leistungen im letzten Schulhalbjahr" verlangt,
  die ein Mittel 50/50 nicht abbildet. Der berechnete Wert ist hier aber nur
  ein Vorschlag; verbindlich ist die von der Lehrkraft festgesetzte Note
  (`notenueberschreibung`), und die ist der Ort, an dem diese Anforderung
  erfüllt wird.

Ebenfalls erledigt: **O-4** entfällt mit der Punkteeingabe („Mitarbeit als
Punktesystem" ist genau das), **O-8** ist verneint — Kurse bleiben
klassengebunden, `kurs.klasse_id` ist NOT NULL.

Weiterhin offen und vor der Notenlogik zu klären: **O-2** (Behandlung leerer
Notengruppen bei der Gewichtung), **O-3** (Rundungsregel und Schwelle für die
Zeugnisnote), **O-5** (Sichtbarkeit der Noten aus Halbjahr 1 in Halbjahr 2).
**O-6** (Layout des Tabellenexports) wird erst für Abschnitt 8 gebraucht.
