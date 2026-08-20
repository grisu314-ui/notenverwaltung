# Betrieb

Alle Befehle laufen als `root` auf dem TrueNAS (`sudo -i`). Dockge startet und
stoppt nur den Stack; eine Kommandozeile hat es nicht.

Neuaufbau von Grund auf: `inbetriebnahme-truenas.md`.

## Sicherung

Läuft nächtlich per Cron:

```
0 2 * * * docker exec notenverwaltung python scripts/backup.py /sicherungen --aufbewahren 31
```

Von Hand anstoßen:

```bash
docker exec notenverwaltung python scripts/backup.py /sicherungen --aufbewahren 31
```

Das Skript verwendet **`VACUUM INTO`**, nie eine Dateikopie, öffnet die Quelle
schreibgeschützt und liest die fertige Kopie zur Prüfung noch einmal. Bei
einem Fehlschlag ist der Rückgabewert ungleich 0, damit Cron es meldet.

> **Warum kein `cp`:** Bei einer Datenbank im WAL-Modus liegen die jüngsten
> Änderungen in der `-wal`-Datei. Eine Kopie nur der `.db` verliert sie — im
> Test kam dabei eine Datei heraus, in der eine Sekunden zuvor geschriebene
> Tabelle vollständig fehlte. Nachgestellt in `tests/test_backup.py`.

Ergebnis sind Dateien `notenverwaltung-JJJJ-MM-TT-HHMMSS.db` in
`/mnt/Daten-Z1/apps/notenverwaltung/sicherungen`. Ältere als die letzten 31
werden entfernt.

Gelegentlich nachsehen, dass dort frische Dateien liegen. Eine Sicherung, die
seit Wochen nicht mehr läuft, merkt sonst niemand.

## Wiederherstellung

**Einmal durchgespielt haben, bevor man sie braucht.** Wer das nicht selbst
gemacht hat, hat keine Sicherung.

```bash
# 1. Stack in Dockge stoppen
# 2. Reste des alten Standes wegräumen -- sie gehören nicht zur Sicherung
rm -f /mnt/Daten-Z1/apps/notenverwaltung/daten/notenverwaltung.db-wal \
      /mnt/Daten-Z1/apps/notenverwaltung/daten/notenverwaltung.db-shm

# 3. Sicherung an ihren Platz kopieren
cp /mnt/Daten-Z1/apps/notenverwaltung/sicherungen/notenverwaltung-JJJJ-MM-TT-HHMMSS.db \
   /mnt/Daten-Z1/apps/notenverwaltung/daten/notenverwaltung.db
chown 1000:1000 /mnt/Daten-Z1/apps/notenverwaltung/daten/notenverwaltung.db

# 4. Stack starten
```

Das `cp` ist hier richtig: Die Sicherung ist eine ruhende Datei und die
Anwendung ist gestoppt. Verboten ist `cp` nur auf die **laufende** Datenbank.

Schritt 2 nicht überspringen. Bleiben `-wal` und `-shm` des alten Standes
liegen, mischt SQLite sie in die wiederhergestellte Datei.

## Testumgebung

Ein zweiter Stack neben dem produktiven, mit eigenem Verzeichnisbaum und
eigenem Tailnet-Namen. Damit lässt sich eine neue Version vollständig
ausprobieren, ohne den laufenden Betrieb oder den echten Datenbestand zu
berühren.

**Der Test bekommt einen eigenen Quellbaum.** Der produktive bleibt auf `main`
und wird nicht auf einen Zweig umgestellt: Er liegt eine Ebene über `daten/`
und `sicherungen/`, und die nächste Version soll von dort aus gebaut werden
können, ohne dass jemand erst den Zweig zurückstellen muss.

```bash
sudo git clone https://github.com/grisu314-ui/notenverwaltung.git /mnt/Daten-Z1/apps/notenverwaltung-dev
cd /mnt/Daten-Z1/apps/notenverwaltung-dev
sudo git checkout ZU-TESTENDER-ZWEIG

sudo mkdir -p daten sicherungen tailscale
sudo chown -R 1000:1000 daten sicherungen
# tailscale/ gehört root -- tailscaled läuft im Container als root

docker build -t notenverwaltung:TEST-TAG .
```

**Ohne das Zielverzeichnis am Ende legt `git clone` ein eigenes Unterverzeichnis
nach dem Repository-Namen an** (`notenverwaltung/` statt der aktuellen
Arbeitsverzeichnisses) — passiert leicht, wenn eine mehrzeilige Eingabe beim
Einfügen abreißt. Kein Schaden, nur ein `cd notenverwaltung` zusätzlich; die
Pfade zu `daten/`, `sicherungen/` und `tailscale/` ändern sich dadurch nicht,
sie hängen nicht vom Quellbaum ab.

Damit sieht der Testbaum genauso aus wie der produktive: Quellbaum in der
Wurzel, `daten/`, `sicherungen/` und `tailscale/` darunter. Das dritte
Verzeichnis wird leicht vergessen — es steht als Volume in der `compose.yaml`
und nimmt den Knotenzustand des Sidecars auf.

Die Datenverzeichnisse stehen in `.dockerignore`; das Image enthält nie eine
Datenbank, gleich aus welchem Baum gebaut wird.

### Was gegenüber dem produktiven Stack anders sein muss

Keine zweite Compose-Datei im Quellbaum, sondern eine Kopie der produktiven
mit sechs geänderten Werten — eine mitgepflegte zweite Datei läuft
erfahrungsgemäß auseinander:

| Stelle | produktiv | Test |
|---|---|---|
| alle drei Pfade | `…/notenverwaltung/…` | `…/notenverwaltung-dev/…` |
| `container_name` (Sidecar) | `notenverwaltung-tailscale` | `notenverwaltung-dev-tailscale` |
| `hostname`, `TS_HOSTNAME` | `notenverwaltung` | `notenverwaltung-dev` |
| `TS_AUTHKEY` in `.env` | der produktive Schlüssel | **eigener** Schlüssel |
| `container_name` (App) | `notenverwaltung` | `notenverwaltung-dev` |
| `image:` | der produktive Tag | z. B. `notenverwaltung:sitzplan-test` |

Damit entsteht ein zweiter Tailnet-Knoten; beide sind nebeneinander
erreichbar. **Keine zweite Cron-Sicherung einrichten** — der bestehende
Eintrag zeigt auf die produktiven Pfade, und die Testdaten sind nichts wert.

**Das produktive `daten/` wird in den Test-Stack nie eingehängt.** Solange die
Pfade getrennt sind, kann der Testcontainer den echten Bestand nicht anfassen.

### Womit die Testdatenbank gefüllt wird

Zwei verschiedene Fragen, zwei verschiedene Wege:

*Funktioniert die neue Funktion?* — mit erfundenen Namen und
Platzhalterbildern. Das Skript bricht ab, wenn die Datenbank nicht leer ist.

```bash
docker run --rm \
    -v /mnt/Daten-Z1/apps/notenverwaltung-dev/daten:/daten \
    --entrypoint alembic \
    notenverwaltung:TEST-TAG upgrade head
docker run --rm \
    -v /mnt/Daten-Z1/apps/notenverwaltung-dev/daten:/daten \
    --entrypoint python \
    notenverwaltung:TEST-TAG scripts/seed_dev.py
```

*Läuft die Migration auf meinem echten Bestand?* — mit einer Kopie, gezogen
über `scripts/backup.py` (also `VACUUM INTO`, nie `cp`). Danach liegen im
Test-Verzeichnis **echte Namen und Lichtbilder**: dieselbe Behandlung wie
produktiv, und nach dem Probelauf wieder löschen.

```bash
# die jüngste Sicherung heißt notenverwaltung-JJJJ-MM-TT-HHMMSS.db
sudo cp /mnt/Daten-Z1/apps/notenverwaltung/sicherungen/notenverwaltung-JJJJ-MM-TT-HHMMSS.db \
        /mnt/Daten-Z1/apps/notenverwaltung-dev/daten/notenverwaltung.db
sudo chown 1000:1000 /mnt/Daten-Z1/apps/notenverwaltung-dev/daten/notenverwaltung.db
# migrieren wie oben, dann den Test-Stack starten und ansehen
```

Erst wenn das sauber läuft, den nächsten Abschnitt gegen den produktiven
Stack fahren.

## Neue Version einspielen

**Die Reihenfolge ist nicht beliebig: erst sichern, dann migrieren, dann
starten.** Bei einer Version mit Schemaänderung vorher den vorigen Abschnitt
durchlaufen — einmal in der Testumgebung, gegen eine Kopie.

```bash
# der produktive Quellbaum, auf main
cd /mnt/Daten-Z1/apps/notenverwaltung
git pull
docker build -t notenverwaltung:$(date +%Y-%m-%d) .

# Stack in Dockge stoppen

# Sicherung mit dem ALTEN Image, gegen die unveränderte Datei
docker run --rm \
    -v /mnt/Daten-Z1/apps/notenverwaltung/daten:/daten \
    -v /mnt/Daten-Z1/apps/notenverwaltung/sicherungen:/sicherungen \
    --entrypoint python \
    notenverwaltung:ALTER-TAG scripts/backup.py /sicherungen

# Migration mit dem NEUEN Image
docker run --rm \
    -v /mnt/Daten-Z1/apps/notenverwaltung/daten:/daten \
    --entrypoint alembic \
    notenverwaltung:NEUER-TAG upgrade head

# Tag in der compose.yaml in Dockge ändern, Stack starten
```

**Der Container migriert nie von selbst.** Passt das Schema nicht zum
Programm, startet er nicht und schreibt den Grund ins Protokoll
(`docker logs notenverwaltung`). Das ist beabsichtigt: Eine automatische
Migration würde den produktiven Bestand mit Klarnamen und Lichtbildern
umbauen, ohne dass jemand sie auf einer Kopie durchgespielt hat.

Bei einer Migration, die mehr als eine Spalte hinzufügt, gehört ein Probelauf
dazu: die frische Sicherung an einen anderen Ort kopieren,
`NOTENVERWALTUNG_DB` darauf zeigen lassen, migrieren, ansehen.

### Zurück auf die vorige Version

Ohne Schemaänderung: Tag in der `compose.yaml` zurückstellen, Stack neu
starten. Fertig — deshalb wird mit Datums-Tags gebaut und nicht mit `latest`.

Mit Schemaänderung genügt das nicht: Das alte Programm verweigert den Start
gegen das neue Schema. Dann erst die Sicherung zurückspielen, dann den Tag
zurückstellen.

Alte Images aufräumen, aber nicht zu früh:

```bash
docker images notenverwaltung
docker rmi notenverwaltung:ALTER-TAG
```

## Endgültiges Löschen

Über `/verwaltung` lassen sich ein **Schüler** oder ein **Schuljahr**
vollständig entfernen — die Pflicht aus Abschnitt 11 der Spezifikation.

Zwei Schritte: Eine Bestätigungsseite zählt auf, was verschwindet (Noten,
Fotos, Historieneinträge, Kursteilnahmen, Festsetzungen), und erst eine zweite
Anfrage mit dem eingetippten Namen löscht. Der Vergleich ist tolerant gegen
fehlende Umlautpunkte — geprüft wird die Absicht, nicht die Tippgenauigkeit.

Ins Protokoll gehen nur ID und Anzahlen, **nie der Name**.

**Die Daten verlassen wirklich die Datei.** `DELETE` gibt in SQLite nur Seiten
frei; danach laufen `VACUUM` **und** `PRAGMA wal_checkpoint(TRUNCATE)`. Beides
ist nötig: `VACUUM` allein schreibt die neue Datei im WAL-Modus *durch* die
`-wal`-Datei, in der der alte Inhalt bis zum Checkpoint lesbar bleibt.
Gemessen, nicht angenommen — `tests/test_loeschen.py` legt ein Foto mit
erkennbarer Bytefolge an und sucht danach in den Rohdateien.

**Was das Löschen nicht erreicht: die Sicherungen.** Ein gelöschter Schüler
steht im Stand von gestern Nacht weiterhin drin und verschwindet dort erst,
wenn die 14 aufbewahrten Stände durchgelaufen sind. Die Bestätigungsseite sagt
das. Wer sofortige Löschung braucht, muss die Sicherungsdateien von Hand
entfernen.

Schlägt das Verdichten fehl — realistischer Fall: das Sicherungsskript läuft
gerade —, sind die Zeilen gelöscht, die Bytes aber nicht. Dann steht das so in
der Rückmeldung; nachholen lässt es sich mit `VACUUM;` und
`PRAGMA wal_checkpoint(TRUNCATE);` in `sqlite3` bei gestoppter Anwendung.

## Export

Über `/verwaltung` zwei Downloads, beide über den **gesamten** Datenbestand:
XLSX mit einem Blatt je Kurs, und Markdown. Der Export entsteht im
Arbeitsspeicher, wird direkt ausgeliefert und nirgends abgelegt.

**Er enthält Klarnamen.**

## Speicherbestätigung — Abnahmetest von Hand

Das stille Verwerfen einer Note bei Verbindungsabbruch ist der gravierendste
denkbare Fehler dieser Anwendung. Die Eingabemaske zeigt „gespeichert" mit
Uhrzeit erst, wenn der Server nach erfolgreichem Schreiben geantwortet hat,
und rendert die Bestätigung aus dem gespeicherten Datensatz, nicht aus der
Anfrage.

**Automatisierte Tests können den entscheidenden Fall nicht prüfen** — was der
Browser bei abgerissener Verbindung anzeigt. Dafür dieser Durchlauf, **nach
jeder Änderung an der Eingabemaske zu wiederholen**:

1. Eingabemaske einer Leistung auf dem Handy öffnen, eine Note auswählen.
   → Die Zeile zeigt „gespeichert" mit Uhrzeit.
2. **Flugmodus einschalten**, bei einem anderen Schüler eine Note auswählen.
   → Die Zeile zeigt „speichert …" und **bekommt keine Bestätigung**.
   Je nach Gerät wird sie sofort rot („NICHT gespeichert – keine Verbindung")
   oder erst nach 30 Sekunden („NICHT gespeichert – keine Antwort").
3. Seite zu verlassen versuchen.
   → Der Browser fragt nach.
4. Flugmodus aus, Seite neu laden.
   → Die erste Note steht da, die zweite nicht — und das war vorher sichtbar.

Ohne Schritt 2 und 3 gilt eine Änderung an der Eingabemaske nicht als
abgenommen.

> **Beide Ausgänge von Schritt 2 sind richtig.** Nicht jedes Gerät meldet den
> Verbindungsverlust: Ein Android-Telefon hält die Anfrage im Flugmodus offen
> und schickt sie nach, sobald das Netz wieder da ist — beobachtet im
> Schulbetrieb. Deshalb steht in `base.html` eine Zeitgrenze von 30 Sekunden;
> danach meldet htmx `htmx:timeout`, und die Zeile wird rot. Der Wert ist so
> gewählt, dass man im Klassenraum die Position wechseln kann, bevor er greift.
>
> Was in **keinem** Fall passieren darf: eine grüne Bestätigung ohne
> Serverantwort. Nur darauf kommt es an. Kommt die Note nach dem Wiedereinschalten
> doch noch an, ist das in Ordnung — sie war vorher nie als gespeichert
> ausgewiesen.

Was Schritt 4 **nicht** beweist: dass die zweite Note dauerhaft verloren ist.
Hält das Gerät die Anfrage offen, wird sie beim Wiederverbinden nachgeholt.
Entscheidend ist allein, dass bis zur Serverantwort nichts als gespeichert
angezeigt wurde.

Fällt JavaScript ganz aus, bleibt jede Zeile ein gewöhnliches Formular mit
Absendeknopf. Auch ein JS-Fehler kann damit keine Note still verschlucken.

### Der Sitzplan hat denselben Weg

Ein verlorener Sitzplatz wiegt weit weniger als eine verlorene Note, die
Bauart ist aber dieselbe: Der Server antwortet mit dem gespeicherten Stand,
und `sitzplan.js` deckt nur ab, was keine Antwort ist. Nach einer Änderung am
Sitzplan derselbe Durchlauf, verkürzt:

1. Einen Schüler auf einen Platz setzen. → Über dem Raster steht
   „gespeichert", der Schüler sitzt dort.
2. **Flugmodus einschalten**, einen weiteren Schüler setzen. → Rote Meldung
   „NICHT gespeichert – keine Verbindung".
3. Flugmodus aus, Seite neu laden. → Der erste sitzt, der zweite nicht.

Ohne JavaScript bleibt jeder Platz ein gewöhnlicher Link und jede Zuweisung
ein Formular mit Absendeknopf.

## Störungssuche

| Fehlerbild | Ursache | Abhilfe |
|---|---|---|
| `unable to open database file` | `daten/` gehört nicht UID 1000 | `chown -R 1000:1000 …/daten` |
| Container startet nicht, Protokoll nennt eine ausstehende Migration | neues Image, altes Schema | Migration ausführen, siehe oben |
| Container startet nicht, Protokoll nennt eine fehlende Datenbank | Datei weg oder falscher Pfad | Sicherung zurückspielen |
| Anwendung im Tailnet nicht erreichbar | Sidecar läuft nicht | `docker logs notenverwaltung-tailscale`, siehe Inbetriebnahme |

Protokolle:

```bash
docker logs notenverwaltung --tail 50
docker logs notenverwaltung-tailscale --tail 50
```
