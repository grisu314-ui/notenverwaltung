# Notenverwaltung

Selbst gehostete Webanwendung zur Notenverwaltung für **eine einzelne
Lehrkraft** an einer berufsbildenden Schule in Rheinland-Pfalz. Ersetzt eine
kommerzielle Lehrer-App im Funktionsbereich Notenverwaltung.

**Der Stand ist produktiv.** Die Anwendung läuft auf einem TrueNAS-SCALE-Server
und ist ausschließlich über das Tailnet des Betreibers erreichbar. Sie enthält
Klarnamen und Lichtbilder realer Schülerinnen und Schüler.

## Wenn Sie das Projekt übernehmen

**→ [`docs/uebergabe.md`](docs/uebergabe.md)** — wer was tun kann, wo die Daten
liegen, erste Schritte, laufende Pflichten.

Die Weiterentwicklung führt ein KI-Assistent aus, angeleitet vom Betreiber.
Dessen Arbeitsvorgaben stehen in **[`CLAUDE.md`](CLAUDE.md)** und haben
Vorrang vor allem außer der Spezifikation.

## Wegweiser

| Ich will … | Datei |
|---|---|
| das Projekt übernehmen | [`docs/uebergabe.md`](docs/uebergabe.md) |
| verstehen, wie Noten berechnet werden | [`docs/notenlogik.md`](docs/notenlogik.md) |
| sichern, wiederherstellen, aktualisieren | [`docs/betrieb.md`](docs/betrieb.md) |
| am Code arbeiten | [`docs/entwicklung.md`](docs/entwicklung.md) |
| die Anwendung neu aufsetzen | [`docs/inbetriebnahme-truenas.md`](docs/inbetriebnahme-truenas.md) |
| wissen, was sie leisten soll | [`notenverwaltung-spezifikation.md`](notenverwaltung-spezifikation.md) |
| wissen, was hier gilt | [`CLAUDE.md`](CLAUDE.md) |

## Was sie kann

Schuljahre mit zwei Halbjahren, Klassen, Kurse, Notengruppen mit Gewichten,
Kursteilnahmen. Noten in Serie eintragen — auf dem Telefon, mit sichtbarer
Speicherbestätigung. Klassenansicht mit Fotos, Schülerblatt, Kursübersicht als
Matrix mit Notenspiegel, Suche über alle Schuljahre. Sitzplan je Klasse, mit
Foto und Namen, druckbar. Fotoerfassung mit
Zuschnitt im Browser. Halbjahres- und Jahresnoten, jeweils überschreibbar.
Export nach XLSX und Markdown. Endgültiges Löschen von Schülern und
Schuljahren.

Was bewusst **nicht** gebaut wurde, steht in
[`docs/entwicklung.md`](docs/entwicklung.md#bewusste-auslassungen) — von der
Authentifizierung bis zur Punkteeingabe. Diese Liste ist wichtiger als die
obige: Sie erklärt, was nicht ergänzt werden soll.

## Aufbau

Python 3.11, FastAPI, Jinja2 serverseitig gerendert, htmx für die
Interaktivität. SQLite mit SQLAlchemy und Alembic. Kein Node, kein npm, kein
Build-Schritt fürs Frontend. Zwei Container: die Anwendung und ein
Tailscale-Sidecar, dessen Netz-Namespace sie mitbenutzt.

```
app/grading/    Notenlogik — rein rechnerisch, ohne ORM, ohne Web
app/services/   Geschäftslogik
app/db/         Modelle, Engine, Sitzungen
app/web/        Router, Templates, statische Dateien
scripts/        Sicherung, Schemaprüfung, Entwicklungsdaten
tests/          427 Tests
```

## Schnellstart für die Entwicklung

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
mkdir -p data
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/alembic upgrade head
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/python scripts/seed_dev.py
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/uvicorn app.web.app:app --reload
.venv/bin/pytest
```

Das Seed-Skript erzeugt erfundene Namen und Platzhalterbilder. Gegen den
produktiven Bestand wird nicht entwickelt.
