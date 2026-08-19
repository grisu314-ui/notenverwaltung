# Entwicklung

## Einrichten

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
mkdir -p data
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/alembic upgrade head
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/python scripts/seed_dev.py
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/uvicorn app.web.app:app --reload
```

Python 3.11 oder neuer (`enum.StrEnum`). Der Container verwendet 3.11, weil
die Anwendung genau dagegen getestet ist.

Das Seed-Skript erzeugt erfundene Namen und Platzhalterbilder und bricht bei
einer nicht leeren Datenbank ab. **Entwicklung, Tests und Migrationsproben
laufen ausschließlich dagegen** — die produktive Datei enthält Klarnamen und
Lichtbilder und wird im Entwicklungsprozess nicht angefasst.

Die einzige Konfiguration der Anwendung ist `NOTENVERWALTUNG_DB`. Ohne sie
wird `data/notenverwaltung.db` relativ zum Arbeitsverzeichnis verwendet. Das
Verzeichnis muss existieren — SQLite legt es nicht an und meldet sonst nur
`unable to open database file`.

## Tests

```bash
.venv/bin/pytest
```

427 Tests. Jeder baut sich seine eigene Datenbank **über die Alembic-Migration
auf**; `create_all()` wird nirgends verwendet, auch nicht im Test. Damit ist
die Migration bei jedem Lauf mitgeprüft. Der Lauf bricht ab, wenn
`NOTENVERWALTUNG_DB` gesetzt ist — Tests fassen keinen konfigurierten
Datenbestand an.

`SAWarning` gilt als Fehler. Das hat schon ein stilles Nicht-Speichern im
Seed-Skript aufgedeckt.

Wichtige Dateien:

| Datei | Prüft |
|---|---|
| `test_berechnung.py`, `test_notenwert.py` | die Rechenlogik, darunter die Pflichtfälle T-1 bis T-9 |
| `test_schema_constraints.py` | dass das Schema falsche Daten wirklich ablehnt |
| `test_migration.py` | dass Modelle und Migration übereinstimmen |
| `test_backup.py` | Sicherung und die Folgen eines `cp` im WAL-Modus |
| `test_loeschen.py` | dass gelöschte Fotobytes die Datei verlassen |
| `test_sitzplan.py` | den Sitzplan: inaktive Schüler, Raster verkleinern, Tauschen |

## Aufbau

Drei Schichten. Die Notenberechnung steht bewusst außerhalb, ohne Kenntnis von
Web und Datenbank.

```
app/web/        FastAPI-Router, Jinja2-Templates, statische Dateien
app/services/   Geschäftslogik, Regeln, die die Datenbank nicht erzwingen kann
app/db/         SQLAlchemy-Modelle, Engine, Sitzungen
app/grading/    Notenlogik — rein rechnerisch, ohne ORM, ohne Web
```

Ein Aufruf geht durch `app/web/routers/…` → `app/services/…` → `app/db/…`.
Router enthalten keine Fachlogik; sie lesen das Formular, rufen einen Dienst
und rendern.

### Landkarte

**Kern**

| Datei | Inhalt |
|---|---|
| `app/grading/notenwert.py` | die sechzehn Werte, Anzeige, Rundung |
| `app/grading/berechnung.py` | Halbjahres- und Jahresnote |
| `app/db/models.py` | zwölf Tabellen, Spezifikation 3 |
| `app/enums.py` | die Statuswerte der Domäne |

**Dienste** (`app/services/`)

| Datei | Inhalt |
|---|---|
| `calculation.py` | Adapter ORM → Notenlogik |
| `verwaltung.py` | Regeln, die kein Fremdschlüssel ausdrücken kann |
| `noten.py` | Noten eintragen, Historie schreiben (in derselben Transaktion) |
| `kursblatt.py` | Kursübersicht als Matrix, Notenspiegel |
| `schuelerblatt.py` | Notenblatt eines Schülers |
| `suche.py` | Suche über alle Schuljahre |
| `sorting.py` | deutsche Namenssortierung |
| `foto.py` | Bilder prüfen und neu kodieren |
| `export.py` | XLSX und Markdown |
| `loeschen.py` | endgültiges Löschen samt Verdichten der Datei |
| `sitzplan.py` | Sitzplan: Raster bauen, Plätze setzen, räumen, tauschen |
| `settings.py` | persistierte Einstellungen |
| `fehler.py` | Datenbankfehler → lesbarer deutscher Satz |

**Web** (`app/web/`) — `app.py` mit den Fehlerbehandlern, `dependencies.py`
für die Sitzung je Anfrage, `gemeinsam.py` für Templates und Filter, dazu ein
Router je Bereich in `routers/`.

**Skripte** — `backup.py` (Sicherung), `schemastand.py` (Startprüfung),
`seed_dev.py` (Entwicklungsdaten).

## Datenbank

- `PRAGMA foreign_keys = ON` bei **jeder** Verbindung, gesetzt im
  `connect`-Ereignis in `app/db/session.py`. SQLite hat Fremdschlüssel
  standardmäßig aus; ohne das Pragma entstehen verwaiste Datensätze.
- WAL-Modus, `busy_timeout`. `synchronous` bleibt auf dem Standard —
  Haltbarkeit gegen Geschwindigkeit zu tauschen ist bei einer Anwendung, deren
  schlimmster Fehler eine still nicht geschriebene Note ist, der falsche
  Handel.
- Dezimalwerte liegen als kanonischer Text in der Datenbank
  (`app/db/types.py`). SQLAlchemys `Numeric` geht auf SQLite über `float` und
  verliert dabei Genauigkeit.
- Löschen ist im Schema kaskadierend. In der Verwaltung lässt sich deshalb
  **nur löschen, was leer ist**; das Löschen mit Inhalt hat seinen eigenen,
  bestätigten Weg (Spezifikation 11).

## Migrationen

```bash
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/alembic revision --autogenerate -m "beschreibung"
```

Die erzeugte Datei **immer von Hand prüfen**, besonders `ondelete`-Angaben und
die Reihenfolge der Tabellen. `test_migration.py` prüft danach, dass Modelle
und Migration übereinstimmen.

Zwei SQLite-Besonderheiten sind in `migrations/env.py` berücksichtigt:

- `render_as_batch=True`, weil SQLite die meisten `ALTER TABLE` nicht kann und
  Alembic die Tabelle stattdessen neu aufbaut. Dafür braucht jeder Constraint
  einen Namen; die Konvention in `app/db/base.py` stellt das sicher.
- Fremdschlüssel sind während der Migration abgeschaltet, weil der
  Tabellenneuaufbau durch einen Zwischenzustand läuft, den ein aktiver
  Fremdschlüssel ablehnen würde. Danach prüft `PRAGMA foreign_key_check`; ein
  Fund lässt die Migration fehlschlagen.

Vor dem produktiven Lauf auf einer **Kopie** des produktiven Bestands
durchspielen — die Kopie über `VACUUM INTO`, nie über `cp`.

## Konventionen

- Code, Bezeichner, Kommentare, Commit-Nachrichten: **Englisch**.
- Fachbegriffe des deutschen Schulwesens behalten ihre deutsche Bezeichnung,
  wo eine Übersetzung mehrdeutig wäre: `Notenschluessel`, `Notengruppe`,
  `Halbjahr`, `Tendenz`.
- Alle Oberflächentexte, Fehlermeldungen und Exporte: **Deutsch**.
- Notenwerte und Gewichte über `Decimal`, nie `float`. Rundung explizit.
- **Kein leeres `except`.** Jeder gefangene Fehler wird geloggt und führt zu
  einer sichtbaren Rückmeldung.
- Jinja2-Autoescaping bleibt an; kein `|safe` auf Daten aus der Datenbank.
  Schülernamen stammen aus Excel-Importen.

## Abhängigkeiten

Versionen sind in `requirements.txt` gepinnt.

```bash
.venv/bin/pip install --upgrade SQLAlchemy alembic
.venv/bin/pytest
.venv/bin/pip freeze | grep -E '^(SQLAlchemy|alembic)=='   # neue Pins übernehmen
```

Bei einem Fehlschlag die alten Pins wiederherstellen.

Neue Bibliotheken sparsam: Jede ist etwas, das der Betreiber allein aktuell
halten muss. Nichts, was sich in unter fünfzig Zeilen selbst schreiben lässt.

Für den Sitzplan (5.6) kam **keine** Bibliothek dazu. Zugewiesen wird mit zwei
Tippern statt mit Ziehen — das ist einhändig auf dem Telefon ohnehin die
bedienbare Form und kommt mit htmx und serverseitigem Rendern aus.

`app/web/static/htmx.min.js` ist htmx 2.0.10 (Lizenz 0BSD), mitgeliefert statt
über ein CDN. Aktualisierung von Hand:

```bash
curl -sS -o /tmp/htmx.tgz https://registry.npmjs.org/htmx.org/-/htmx.org-<version>.tgz
tar -xzf /tmp/htmx.tgz -C /tmp package/dist/htmx.min.js
cp /tmp/package/dist/htmx.min.js app/web/static/htmx.min.js
```

Danach die Version hier anpassen.

## Bewusste Auslassungen

Wer das Projekt übernimmt, wird versucht sein, diese Dinge zu ergänzen. Sie
fehlen nicht, sie sind entschieden.

| Nicht gebaut | Warum |
|---|---|
| Authentifizierung, Sessions, Benutzer | Der Zugang wird davor geregelt (Tailscale-ACLs). Nicht geschriebener Auth-Code kann keine Lücke haben |
| TLS | Der Verkehr läuft verschlüsselt durch das Tailnet; ein Zertifikat für einen internen Namen ist Betriebsaufwand ohne Gewinn |
| Punkteeingabe, Notenschlüssel | Noten werden direkt eingetragen, Umrechnung geschieht außerhalb (siehe `notenlogik.md`) |
| Offline-Fähigkeit, PWA, Service Worker | Reine Server-Anwendung. Bei Verbindungsverlust wird auf Papier notiert |
| Mehrbenutzerbetrieb, `owner_id` | Ein Nutzer |
| Hintergrundprozesse, Queue, Cache | Nichts läuft länger als eine Anfrage |
| Indizes, Pagination, Denormalisierung | Keine Optimierung ohne gemessenen Anlass — wenige hundert Schüler |
| Automatische Migration beim Start | Der Container startet lieber nicht, als den produktiven Bestand ungefragt umzubauen |
| Ziehen und Fallenlassen im Sitzplan, frei platzierbare Tische | Einhändig im Stehen nicht bedienbar; zwei Tipper auf ein Raster sind es (5.6) |
| Zweiter Sitzplan je Klasse, Klausurordnung, Übertrag ins Folgejahr | Gebraucht wird eine Sitzordnung je Klasse, sonst nichts |
| Oberfläche für die Änderungshistorie | Die Tabelle beantwortet die Frage per SQL, wenn sie gestellt wird |
| Gruppenmittel in Übersicht und Export | Existiert bei einstufiger Berechnung nicht |

Die vollständige Liste der Abweichungen von der ursprünglichen Fassung steht
am Ende von `notenverwaltung-spezifikation.md`.
