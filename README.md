# Notenverwaltung

Selbst gehostete Webanwendung zur Notenverwaltung für **eine einzelne
Lehrkraft** an einer berufsbildenden Schule in Rheinland-Pfalz. Ersetzt eine
kommerzielle Lehrer-App im Funktionsbereich Notenverwaltung.

**Der Stand ist produktiv.** Die Anwendung läuft auf einem TrueNAS-SCALE-Server
und ist ausschließlich über das Tailnet des Betreibers erreichbar, hinter einer
Passwortabfrage (siehe „Zugang & Passwort ändern"). Sie enthält
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
Foto und Namen, druckbar, mit der Mitarbeitsnote des Tages — einzeln über
den Platz oder als Schnelleingabe unter jedem Schüler. Neue Kurse
starten mit drei Notengruppen. Schüleranzahl und Kopienbedarf auf einen Blick. Fotoerfassung mit
Zuschnitt im Browser. Halbjahres- und Jahresnoten, jeweils überschreibbar.
Export nach XLSX und Markdown. Endgültiges Löschen von Schülern und
Schuljahren.

Was bewusst **nicht** gebaut wurde, steht in
[`docs/entwicklung.md`](docs/entwicklung.md#bewusste-auslassungen) — von der
Authentifizierung in der Anwendung bis zur Punkteeingabe. Diese Liste ist wichtiger als die
obige: Sie erklärt, was nicht ergänzt werden soll.

## Aufbau

Python 3.11, FastAPI, Jinja2 serverseitig gerendert, htmx für die
Interaktivität. SQLite mit SQLAlchemy und Alembic. Kein Node, kein npm, kein
Build-Schritt fürs Frontend. Drei Container: ein Tailscale-Sidecar als Knoten im
Tailnet, in dessen Netz-Namespace eine Caddy-Pforte mit Passwortabfrage, und
dahinter die Anwendung in einem internen Netz ohne Ausgang.

```
Tailnet ──► tailscale + pforte (Caddy :8000, Basic Auth)
                  │
                  ▼  Netz „intern" (internal: true)
            notenverwaltung :8000
```

```
app/grading/    Notenlogik — rein rechnerisch, ohne ORM, ohne Web
app/services/   Geschäftslogik
app/db/         Modelle, Engine, Sitzungen
app/web/        Router, Templates, statische Dateien
scripts/        Sicherung, Schemaprüfung, Entwicklungsdaten
tests/          530 Tests
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

## Zugang & Passwort ändern

Vor der Anwendung steht eine **Pforte**: ein Caddy-Container, der Benutzer und
Passwort verlangt (HTTP Basic Auth). Die Anwendung selbst hat weiterhin kein
Login. Die Adresse bleibt `http://notenverwaltung:8000`; der Browser fragt
beim ersten Aufruf nach Benutzer und Passwort.

Benutzer und Passwort stehen **nicht** im Repository, sondern in der `.env`
neben der Compose-Datei — in Dockge im Stack-Verzeichnis, üblicherweise
`/opt/stacks/notenverwaltung/.env`. Das Passwort selbst steht nirgends, nur
sein Hash. Vorlage: [`.env.example`](.env.example).

**Passwort ändern** — in der TrueNAS-Shell, als root:

```bash
# 1. Hash erzeugen. Fragt das Passwort zweimal ab; es landet nicht in der
#    Shell-Historie. Ausgabe: eine Zeile, die mit $2a$14$ beginnt.
docker run --rm -it caddy:2.11.4-alpine caddy hash-password

# 2. In die .env eintragen -- der Hash in EINFACHEN Anführungszeichen:
#      PFORTE_USER=lehrer
#      PFORTE_HASH='$2a$14$...'
nano /opt/stacks/notenverwaltung/.env

# 3. Die Pforte neu erzeugen. `restart` genügt NICHT: Umgebungsvariablen
#    werden nur beim Erzeugen des Containers gelesen.
cd /opt/stacks/notenverwaltung
docker compose up -d pforte

# 4. Prüfen, dass der Hash vollständig angekommen ist:
docker exec notenverwaltung-pforte printenv PFORTE_HASH
```

Die einfachen Anführungszeichen sind nicht verhandelbar: Ohne sie liest
Compose `$2a`, `$14` usw. als Variablen, ersetzt sie durch nichts, und kein
Passwort passt mehr. `docker compose config` zeigt den Hash übrigens mit
`$$` statt `$` — das ist nur die Darstellung, kein Fehler. Maßgeblich ist
Schritt 4.

In Dockge tut *Deployen* dasselbe wie Schritt 3.

**Bekannte Grenzen**, in Kauf genommen:

- kein zweiter Faktor;
- keine Sperre nach Fehlversuchen — geschützt wird das dadurch, dass nur
  Geräte im Tailnet die Pforte überhaupt erreichen;
- kein Abmelden: Der Browser hält die Anmeldung, bis er geschlossen wird;
- das Passwort geht bei jeder Anfrage mit, nur Base64-kodiert. Verschlüsselt
  ist es durch das Tailnet, nicht durch TLS.

Aufbau, Abnahme und Störungssuche: [`docs/inbetriebnahme-truenas.md`](docs/inbetriebnahme-truenas.md).
