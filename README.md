# Notenverwaltung

Selbst gehostete Webanwendung zur Notenverwaltung für eine Lehrkraft.
Maßgeblich ist `notenverwaltung-spezifikation.md`, Arbeitsvorgaben stehen in
`CLAUDE.md`.

## Stand der Umsetzung

| Bereich | Spezifikation | Stand |
|---|---|---|
| Projektstruktur, Datenmodell | 3 | umgesetzt |
| Notenlogik | 4 | umgesetzt in `app/grading/` |
| Web-Fundament, Sortierung, Einstellungen | 5, 6, 10 | umgesetzt (Schritt 5a) |
| Verwaltungsoberfläche | 5.5 | umgesetzt (Schritt 5b) |
| Klassen- und Schüleransicht, Suche | 5.1, 5.2 | umgesetzt (Schritt 5c) |
| Serieneingabe von Noten, Änderungshistorie | 5.4, 3.2 | umgesetzt (Schritt 5d) |
| Kurs-/Fachübersicht | 5.3 | umgesetzt (Schritt 5e) |
| Fotoerfassung | 7 | umgesetzt (Schritt 5f) |
| Export | 8, 11 | umgesetzt |
| Backup-Skript, Docker | 2, 2.5 | umgesetzt, Image noch nicht gebaut |
| Löschfunktion | 11 | umgesetzt |
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

## Festlegungen zur Notenlogik (Abschnitt 4)

Entscheidungen des Auftraggebers. Umgesetzt in `app/grading/`.

### Abweichungen von Abschnitt 4.4

- **Die Berechnung ist einstufig, nicht zweistufig.** Die Spezifikation
  beschreibt erst ein Mittel je Notengruppe und dann ein Mittel dieser
  Gruppenmittel; damit hinge die Wirkung einer Gruppe nicht davon ab, wie
  viele Noten sie enthält. Gewünscht ist das Gegenteil — viele kleine Noten
  dürfen stärker wiegen. Gerechnet wird deshalb:

  ```
  Halbjahresnote = Σ(notenwert × gruppengewicht × leistungsgewicht)
                   ─────────────────────────────────────────────────
                   Σ(gruppengewicht × leistungsgewicht)
  ```

  Gruppengewichte behalten ihre Wirkung: Eine Note in einer mit 70
  gewichteten Gruppe zählt mehr als eine in einer mit 30 gewichteten. Neu ist
  nur, dass eine Gruppe mit vier Noten bei gleichem Gruppengewicht eine
  Gruppe mit einer Note überwiegt. Diese Rechnung trifft den in Testfall T-1
  genannten Erwartungswert 2,00 exakt, was die zweistufige Regel nicht tut.

- **Eine Nachkommastelle statt zwei.** 4.4 nennt zwei (z. B. 2,43).

- **Gleichstand geht immer zur besseren Note**, nicht kaufmännisch. 4.4 nennt
  ausdrücklich 2,49 → 2 und 2,50 → 3; hier wird **2,50 zur 2**.

  Beachten: Die ganze Notenstufe wird aus dem auf eine Stelle gerundeten Wert
  gebildet, damit angezeigte Zahl und Note nie widersprüchlich sind. Durch
  diese zweifache Rundung liegt die tatsächliche Grenze zur nächsten Note
  nicht bei einem Rohwert von 2,50, sondern erst oberhalb von 2,55: 2,54 wird
  zu 2,5 und damit zur 2, erst 2,56 wird zu 2,6 und damit zur 3.

- **Keine Rückrechnung eines Durchschnitts auf eine Tendenznote.** Die Tabelle
  aus 4.1 dient nur der Eingabe und Anzeige einzelner Noten.

### Weitere Festlegungen

- **Gewichtung der Halbjahre für die Jahresnote: 50/50**, pro Kurs änderbar
  (`kurs.gewicht_halbjahr_1` / `_2`, Vorgabe in `app/db/models.py`).
- **Die Gewichtung wirkt auf die beiden Halbjahres*noten*, nicht auf die
  Rohdurchschnitte.** Maßgeblich ist die festgesetzte Halbjahresnote aus
  `notenueberschreibung`. Ist ein Halbjahr noch nicht festgesetzt, wird für
  dieses Halbjahr der berechnete Wert herangezogen.
- **Keine Jahresnote, solange ein Halbjahr keine berechenbare Halbjahresnote
  hat.** Der praktische Fall ist der Januar: Halbjahr 2 ist leer. Dann wird
  keine Jahresnote angezeigt — kein Rückfall auf die einzelne Halbjahresnote.
  Das ist konsistent mit Testfall T-7 (keine Note ⇒ keine Berechnung, leere
  Anzeige).
- **Eine Notenüberschreibung ist immer eine ganze Notenstufe 1 bis 6**, nie
  eine Tendenz. Grund: § 53 SchulO laut Abschnitt 4.5; die Überschreibung ist
  der Weg zur Zeugnisnote. Prüfung gehört in die Service-Schicht, das Schema
  erzwingt es nicht.
- **Leere Notengruppe: kein Gewicht** (O-2). Sie fällt aus der Berechnung;
  bei der einstufigen Rechnung geschieht das von selbst, weil sie weder in
  Zähler noch Nenner auftaucht.
- **Noten aus Halbjahr 1 bleiben in Halbjahr 2 sichtbar** (O-5). Betrifft die
  Ansichten, Abschnitt 5.

## Export (Abschnitt 8, O-6)

Über `/verwaltung` zwei Downloads, beide über **den gesamten Datenbestand** —
alle Schuljahre, alle Klassen, alle Kurse. Das erfüllt zugleich die Forderung
aus Abschnitt 11, dass der Bestand exportierbar sein muss, damit kein Lock-in
entsteht.

- **XLSX**, ein Blatt je Kurs, im Layout aus O-6: Kopfbereich mit Klasse und
  Kurs, je Zeile ein Schüler, darüber drei um 90° gedrehte Beschriftungszeilen
  für Halbjahr, Notengruppe mit Gewicht und Leistung mit Datum. Zwischen zwei
  Notengruppen und vor den Jahresnoten je eine leere Spalte. Die Namensspalte
  und die Beschriftungen bleiben beim Scrollen stehen.
- **Markdown**, ein Abschnitt je Kurs.

Beide Formate werden aus demselben Modell erzeugt wie die Kursübersicht am
Bildschirm. Zwei getrennte Rechenwege für dieselben Noten laufen früher oder
später auseinander, und es fällt erst auf, wenn jemand die Zahlen vergleicht.

**Bewusste Abweichung von Abschnitt 8: keine Gruppenmittel** — dieselbe
Begründung wie bei der Kursübersicht.

Eine Notengruppe ohne Leistungen bekommt keine Spalte; sie wäre eine
Überschrift über nichts und würde die Abstandsspalte zur nächsten Gruppe
auffressen. In der Gruppenliste über der Tabelle steht sie mit dem Zusatz
„ohne Leistungen".

Der Export entsteht **im Arbeitsspeicher** und wird direkt ausgeliefert: keine
temporäre Datei, kein Zeitplan, kein Ablageort. Der Dateiname wird in der
Anwendung gebildet und enthält keine gespeicherten Daten — kein Name aus einem
Excel-Import kann den Header aufbrechen. **Der Export enthält Klarnamen.**

## Betrieb im Container

> **Für TrueNAS SCALE mit Dockge gibt es eine eigene Schritt-für-Schritt-Anleitung:
> [`TRUENAS.md`](TRUENAS.md)** und dazu die passende Compose-Datei
> `docker-compose.truenas.yml` (ohne Build-Schritt). Dieser Abschnitt
> beschreibt den allgemeinen Aufbau und die Variante mit `docker compose
> build`, wie sie auf dem Raspberry Pi als Teststand verwendet wird.

Aufbau: ein eigener **Tailscale-Container** als Sidecar, die Anwendung teilt
sich dessen Netz-Namespace. Sie veröffentlicht damit keinen eigenen Port und
ist außerhalb des Tailnets nicht erreichbar (Spezifikation 2, Punkt 6). Ein
eigener Tailnet-Knoten hat den praktischen Vorteil, dass sich in den
Tailscale-ACLs genau für diesen Knoten festlegen lässt, welche Geräte ihn
erreichen dürfen.

**Vor dem ersten Start anzupassen** in `docker-compose.yml`:

1. Die beiden Pfade unter `volumes` auf Ihre Datasets. Die SQLite-Datei gehört
   auf ein **lokales** Dataset, nie auf eine SMB- oder NFS-Freigabe.
2. Eine Datei `.env` neben der Compose-Datei mit `TS_AUTHKEY=tskey-...`.
   Sie ist in `.gitignore` eingetragen. Der Schlüssel gehört dem
   Tailscale-Container, nicht der Anwendung — die hat kein einziges Geheimnis
   und liest genau eine Umgebungsvariable, den Datenbankpfad.
3. Das Tailscale-Image auf die Version festnageln, die Ihr bestehender
   Container verwendet.

```bash
docker compose build
docker compose up -d
```

**Die Datenbank beim ersten Mal anlegen** (der Container startet ohne sie
nicht):

```bash
docker compose run --rm --entrypoint "" notenverwaltung alembic upgrade head
```

### Rechte auf dem Dataset

Die Anwendung läuft als UID/GID 1000, nicht als root. Gehört das
Datenverzeichnis einem anderen Benutzer, startet der Container zwar, kann aber
nicht schreiben. Das Fehlerbild ist `unable to open database file`. Abhilfe:

```bash
chown -R 1000:1000 /mnt/Daten-Z1/apps/notenverwaltung/daten /mnt/Daten-Z1/apps/notenverwaltung/sicherungen
```

### Aktualisieren

**Der Container migriert die Datenbank nicht von selbst.** Ändert eine neue
Version das Schema, prüft er das beim Start, startet **nicht** und schreibt
den Grund ins Protokoll. Das ist beabsichtigt: eine automatische Migration
würde den produktiven Bestand mit Klarnamen und Lichtbildern umbauen, ohne
dass jemand sie auf einer Kopie durchgespielt hat.

Ablauf beim Update — erst sichern, dann migrieren:

```bash
docker compose pull ; docker compose build
docker compose run --rm --entrypoint "" notenverwaltung \
    python scripts/backup.py /sicherungen
docker compose run --rm --entrypoint "" notenverwaltung alembic upgrade head
docker compose up -d
```

Bei einer Migration, die mehr als eine Spalte hinzufügt, gehört zusätzlich ein
Probelauf auf einer Kopie dazu: die frische Sicherung an einen anderen Ort
kopieren, `NOTENVERWALTUNG_DB` darauf zeigen lassen, migrieren, ansehen.

## Sicherung und Wiederherstellung

```bash
docker compose exec notenverwaltung python scripts/backup.py /sicherungen --aufbewahren 14
```

Das Skript verwendet **`VACUUM INTO`**, nie eine Dateikopie. Der Grund ist
nicht theoretisch: Ein `cp` der `.db`-Datei einer laufenden Anwendung im
WAL-Modus liefert einen inkonsistenten Stand — im Test in
`tests/test_backup.py` fehlt in der so entstandenen Kopie eine Tabelle, die
Sekunden vorher geschrieben wurde, vollständig.

Weitere Eigenschaften:

- Die Quelle wird **nur lesend** geöffnet. Ein vertippter Pfad schlägt fehl,
  statt still eine leere Datenbank anzulegen.
- Nach dem Schreiben wird die Kopie geöffnet und mit `integrity_check` und
  `foreign_key_check` geprüft. Eine Sicherung, die niemand liest, ist keine.
- Die letzten 14 Stände bleiben, ältere werden entfernt. Fremde Dateien im
  Verzeichnis bleiben unangetastet.
- Rückgabewert ≠ 0 bei Fehlschlag, damit Cron es meldet.

Per Cron auf dem TrueNAS-Host, zum Beispiel nächtlich um 2 Uhr:

```
0 2 * * * docker compose -f /pfad/zu/docker-compose.yml exec -T notenverwaltung python scripts/backup.py /sicherungen --aufbewahren 14
```

### Wiederherstellen

```bash
docker compose down
cp /mnt/Daten-Z1/apps/notenverwaltung/sicherungen/notenverwaltung-JJJJ-MM-TT-HHMMSS.db \
   /mnt/Daten-Z1/apps/notenverwaltung/daten/notenverwaltung.db
chown 1000:1000 /mnt/Daten-Z1/apps/notenverwaltung/daten/notenverwaltung.db
docker compose up -d
```

Das `cp` ist hier zulässig und richtig: Die Sicherung ist eine ruhende Datei,
und die Anwendung ist gestoppt. Verboten ist `cp` nur auf die **laufende**
Datenbank.

> **Abnahme:** Abschnitt 2.5 der Spezifikation verlangt einen einmal von Hand
> durchgespielten Wiederherstellungstest. Der automatische Test in
> `tests/test_backup.py` deckt Sichern und Zurücklesen ab, aber nicht Ihre
> echten Pfade und Rechte. Spielen Sie den Ablauf oben einmal mit einer
> echten Sicherung durch, bevor Sie sich darauf verlassen.

## Einrichtung ohne Container (Entwicklung)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Python 3.11 oder neuer (die Anwendung verwendet `enum.StrEnum`). Der Container
verwendet 3.11, weil die Anwendung genau dagegen getestet ist.

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

Entwicklungsdaten einspielen (erfundene Namen, erzeugte Platzhalterbilder,
bricht bei einer nicht leeren Datenbank ab):

```bash
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/python scripts/seed_dev.py
```

**Entwicklung, Tests und Migrationsproben laufen ausschließlich gegen diese
Entwicklungsdatenbank.** Die produktive Datei enthält Klarnamen und Lichtbilder
und wird im Entwicklungsprozess nicht angefasst. Eine Migration wird vor dem
produktiven Lauf auf einer Kopie des produktiven Bestands durchgespielt — die
Kopie über `VACUUM INTO` erzeugen, nie über `cp` auf die laufende Datei.

## Fotoerfassung

Auf der Schülerbearbeitung: „Foto aufnehmen" öffnet über
`<input type="file" accept="image/*" capture="environment">` die Kamera,
danach wird im Browser quadratisch zugeschnitten und als 512 × 512 JPEG
hochgeladen.

**Zuschneiden ohne Fremdbibliothek und ohne Pinch-Zoom.** Ziehen verschiebt
das Bild, ein Schieberegler ändert die Größe. Grund: Im Unterricht wird das
Telefon einhändig gehalten, und ein Regler ist so bedienbar, zwei Finger sind
es nicht.

**Serverseitig wird jedes Bild neu kodiert**, nicht durchgereicht. Das ist es,
was eingebettete Metadaten und in eine gültige Bilddatei geschmuggelte Inhalte
entfernt:

| Prüfung | Grenze |
|---|---|
| Dateigröße | 2 MB, geprüft vor dem Dekodieren |
| Typ | aus den Bytes, **nicht** aus dem gemeldeten Typ; nur JPEG und PNG |
| Bildpunkte | 40 Millionen — ein 20-kB-PNG kann sonst zu Gigapixeln aufgehen |
| Ausgabe | RGB, höchstens 512 × 512, JPEG Qualität 80, ohne EXIF |

Die EXIF-Orientierung wird angewendet, **bevor** die Metadaten verworfen
werden — sonst liegt ein Hochkantfoto quer. Transparenz wird auf Weiß
gelegt statt auf Schwarz.

Der vom Client gelieferte Dateiname wird nirgends verwendet; gespeichert wird
ein BLOB.

Größenordnung: ein Platzhalterbild wiegt rund 7 kB, ein echtes Porträt eher
40 bis 60 kB. Bei dreihundert Schülern bleibt die Datenbank damit im niedrigen
zweistelligen MB-Bereich, wie in Abschnitt 7 der Spezifikation geschätzt.

**Offen bis zum Test am Gerät:** ob `capture` ohne HTTPS greift. Falls nicht,
öffnet sich statt der Kamera der normale Auswahldialog, in dem die Kamera-App
als Quelle wählbar ist — ein Tipper mehr, kein Ausfall.

## Speicherbestätigung — Abnahmetest von Hand

Abschnitt 10 der Spezifikation nennt das stille Verwerfen einer Note beim
Verbindungsabbruch den gravierendsten denkbaren Fehler dieser Anwendung. Die
Eingabemaske ist danach gebaut: Eine Zeile zeigt „gespeichert" mit Uhrzeit
**erst dann**, wenn der Server nach erfolgreichem Schreiben geantwortet hat.
Die Bestätigung wird aus dem gespeicherten Datensatz gerendert, nicht aus der
Anfrage.

**Automatisierte Tests können den entscheidenden Fall nicht prüfen** — was der
Browser bei abgerissener Verbindung anzeigt. Dafür dieser Durchlauf, der nach
jeder Änderung an der Eingabemaske zu wiederholen ist:

1. Eingabemaske einer Leistung auf dem Handy öffnen, eine Note auswählen.
   → Die Zeile zeigt „gespeichert" mit Uhrzeit.
2. **Flugmodus einschalten**, bei einem anderen Schüler eine Note auswählen.
   → Die Zeile wird rot und zeigt „NICHT gespeichert – keine Verbindung".
3. Seite zu verlassen versuchen.
   → Der Browser fragt nach, ob die Seite wirklich verlassen werden soll.
4. Flugmodus aus, Seite neu laden.
   → Die erste Note steht da, die zweite nicht — und das war vorher sichtbar.

Ohne Schritt 2 und 3 gilt eine Änderung an der Eingabemaske nicht als
abgenommen.

Fällt JavaScript ganz aus, bleibt jede Zeile ein gewöhnliches Formular mit
Absendeknopf; die Seite lädt neu und zeigt den gespeicherten Stand. Auch ein
JS-Fehler kann damit keine Note still verschlucken.

## Kursübersicht — bewusste Abweichung von 5.3

Die Spezifikation nennt in 5.3 eine Spalte „Gruppenmittel". **Die gibt es
nicht.** Seit die Berechnung einstufig ist, kommt ein Mittel je Notengruppe
darin nicht mehr vor, und das Gesamtmittel ist ausdrücklich *nicht* der
gewichtete Mittelwert solcher Gruppenmittel. Eine Spalte, die zum Nachrechnen
einlädt und dabei nicht aufgeht, richtet mehr Schaden an als Nutzen.

Sichtbar bleibt die **Gruppengewichtung**, wie in 5.3 gefordert.

### Notenspiegel

Unter der Matrix steht je Leistung eine Zeile mit Durchschnitt und der
Verteilung auf die Notenstufen 1 bis 6:

- Tendenznoten zählen zu ihrer ganzen Stufe — 2+ und 2− stehen beide in
  Spalte 2.
- `nicht erbracht` zählt als 6, in Durchschnitt **und** Verteilung.
- `nicht gewertet` fällt aus beidem heraus und steht in einer eigenen Spalte.
  Sonst sähe eine Klassenarbeit mit vielen Entschuldigten besser aus, als sie
  war.

Der Durchschnitt einer Leistung ist ein schlichtes Mittel über die
Teilnehmer; das Leistungsgewicht wirkt nur innerhalb der Note eines einzelnen
Schülers, nicht zwischen Schülern.

Die Übersicht ist nur lesend. Jede Spaltenüberschrift verlinkt in die
Serieneingabe.

## Änderungshistorie

Jede Änderung an einer Note — Wert, Status, Löschung — wird in
`note_historie` angehängt, in derselben Transaktion wie die Änderung selbst.
Es gibt dafür bewusst keine Oberfläche (Spezifikation 3.2); die Tabelle
beantwortet die Frage „was stand da vorher", wenn sie gestellt wird:

```sql
SELECT * FROM note_historie WHERE schueler_id = ? ORDER BY zeitpunkt;
```

Der Eintrag zu einer gelöschten Note überlebt die Note — deshalb trägt
`note_id` keinen Fremdschlüssel.

## Suche

Das Suchfeld im Kopfbereich sucht über **alle Klassen und alle Schuljahre**,
auch nach ehemaligen Schülern.

Die Suche läuft bewusst nicht über SQL `LIKE`: SQLite ignoriert dort die
Groß- und Kleinschreibung nur bei ASCII-Zeichen und kennt keine Umlaute.
Stattdessen werden die Schüler geladen und in Python mit derselben
Normalisierung gefiltert, die auch die Sortierung verwendet — „ozturk" findet
damit „Öztürk", „strasser" findet „Straßer". Die Fotospalte ist `deferred` und
wird dabei nicht mitgeladen.

## Löschen in der Verwaltung

In der Verwaltung lässt sich **nur löschen, was leer ist** — eine Notengruppe
ohne Leistungen, ein Kurs ohne Notengruppen, eine Klasse ohne Schüler und
Kurse, ein Schuljahr ohne Klassen, ein Schüler ohne Noten.

Grund: Die Fremdschlüssel im Schema löschen kaskadierend. Ein Knopf
„Notengruppe löschen" nähme sonst im Zweifel dreißig Noten mit, ohne dass das
sichtbar wäre. Das endgültige Löschen mit Inhalt läuft über die Löschfunktion
nach Abschnitt 11 (siehe unten).

Ein Schüler, der die Klasse verlässt, wird **nicht** gelöscht, sondern auf
inaktiv gesetzt; seine Noten bleiben erhalten.

## Löschfunktion (Abschnitt 11)

Endgültig löschen lassen sich zwei Dinge: ein **Schüler** mit allem, was an
ihm hängt, und ein **Schuljahr** mit allem darunter. Die Einstiege stehen
unten auf der jeweiligen Verwaltungsseite.

Der Ablauf hat zwei Schritte:

1. Eine Bestätigungsseite zählt auf, was verschwindet — Noten, Fotos,
   Einträge der Änderungshistorie, Kursteilnahmen, festgesetzte Noten, jeweils
   mit Anzahl. Gelöscht wird hier noch nichts.
2. Erst wenn der Name des Schülers bzw. die Bezeichnung des Schuljahres
   eingetippt wurde, entfernt die zweite Anfrage die Daten. Der Vergleich
   nutzt dieselbe Normalisierung wie die Sortierung: „Anne Ozturk" genügt für
   „Änne Öztürk". Geprüft wird die Absicht, nicht die Tippgenauigkeit.

Ins Protokoll gehen nur die ID und die Anzahlen — **nie der Name**. Eine
Protokollzeile mit Klarnamen würde genau das aufbewahren, was der Vorgang
entfernen soll.

### Die Daten verlassen wirklich die Datei

`DELETE` gibt in SQLite die Seiten nur frei; die Bytes eines gelöschten
Lichtbilds stehen danach weiter in der Datei. Nach dem Löschen läuft deshalb
`VACUUM` **und** `PRAGMA wal_checkpoint(TRUNCATE)`.

Beides ist nötig. `VACUUM` allein schreibt die neue Datei im WAL-Modus *durch*
die `-wal`-Datei, in der der alte Inhalt bis zum nächsten Checkpoint lesbar
bleibt. Gemessen, nicht angenommen: `tests/test_loeschen.py` legt ein Foto mit
einer erkennbaren Bytefolge an und sucht danach in den Rohdateien —
`test_vacuum_allein_laesst_die_fotobytes_im_wal_stehen` hält den Zwischenstand
fest, `test_nach_dem_verdichten_sind_die_fotobytes_aus_der_datei_verschwunden`
das Ergebnis.

Das Verdichten läuft **nach** dem Commit. Kommt `VACUUM` nicht an seine Sperre
— realistischer Fall: das Sicherungsskript läuft gerade —, sind die Zeilen
gelöscht, die Bytes aber nicht. Dann steht das so in der Rückmeldung und der
Grund im Protokoll; als schlichtes „Gelöscht." gemeldet wäre es eine falsche
Zusage. Ein späterer Lauf des Sicherungsskripts hat darauf keinen Einfluss;
zum Nachholen genügt `VACUUM;` gefolgt von `PRAGMA wal_checkpoint(TRUNCATE);`
in `sqlite3` auf der Datei — bei gestoppter Anwendung.

### Was das Löschen nicht erreicht

**Die Sicherungen.** Ein gelöschter Schüler steht im Stand von gestern Nacht
weiterhin drin und verschwindet dort erst, wenn die aufbewahrten Sicherungen
durchgelaufen sind (Aufbewahrung siehe „Sicherung und Wiederherstellung").
Die Bestätigungsseite sagt das ausdrücklich. Wer sofortige Löschung braucht,
muss die betroffenen Sicherungsdateien von Hand entfernen.

## Anwendung starten

```bash
NOTENVERWALTUNG_DB=data/dev.db .venv/bin/uvicorn app.web.app:app --reload
```

Im Betrieb läuft die Anwendung in einem Container, der über Tailscale
erreichbar ist. **Die Anwendung hat keine eigene Authentifizierung**, liest
keinen Identitäts-Header und kennt keine Sitzungen — der Zugang wird
vollständig davor geregelt. Das ist beabsichtigt und keine Lücke.

### Kein TLS — bewusste Abweichung von Abschnitt 2, Punkt 7

Die Spezifikation verlangt HTTPS mit gültigem Zertifikat. Das entfällt auf
Entscheidung des Betreibers: Der Zugriff läuft ausschließlich durch den
Tailscale-Tunnel, der Verkehr ist damit ohnehin verschlüsselt.

**Offener technischer Punkt für Abschnitt 7.** Browser beurteilen einen
„Secure Context" am URL-Schema, nicht an der tatsächlichen Transportsicherheit;
`http://…` im Tailnet gilt ihnen als unsicher. Sicher ist: `getUserMedia`
verlangt einen Secure Context. Ob das auch für
`<input type="file" capture="environment">` gilt — den in Abschnitt 7
beschriebenen Weg —, ist nicht geklärt und wird beim Bau der Fotoerfassung am
Zielgerät ausprobiert. Falls `capture` ignoriert wird, gibt es zwei Auswege
ohne eigene Domain: ein Datei-Feld ohne `capture` (Kamera wird im
Auswahldialog gewählt) oder ein Zertifikat über `tailscale cert` für den
`*.ts.net`-Namen.

## Mitgelieferte Fremddateien

`app/web/static/htmx.min.js` — htmx 2.0.10, Lizenz 0BSD. Kein CDN, kein npm im
Build. Aktualisierung von Hand:

```bash
curl -sS -o /tmp/htmx.tgz https://registry.npmjs.org/htmx.org/-/htmx.org-<version>.tgz
tar -xzf /tmp/htmx.tgz -C /tmp package/dist/htmx.min.js
cp /tmp/package/dist/htmx.min.js app/web/static/htmx.min.js
```

Danach die Version hier im README anpassen.

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

## Offene Punkte aus Abschnitt 9 der Spezifikation

**Alle acht sind geklärt.** O-2, O-3, O-5 und O-6 stehen weiter oben bei den
fachlichen Festlegungen; hier die verbleibenden vier:

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

Die mit **(L)** markierten Punkte wurden nicht anhand der Lehrmeister-App
beantwortet, sondern vom Auftraggeber direkt entschieden.
