# Notenverwaltung – Projektspezifikation

**Version:** 1.1 · **Stand:** 19.08.2026
**Zweck:** Beschreibt, *was* gebaut wurde, nicht *wie*. Version 1.1 ist auf den
umgesetzten Stand nachgeführt; die Abweichungen gegenüber Version 1.0 stehen
gesammelt am Ende.
**Auftraggeber/Betreiber/Alleinnutzer:** eine Lehrkraft an einer berufsbildenden Schule (Rheinland-Pfalz).

---

## 1. Zielsetzung und Abgrenzung

Eine selbst gehostete Webanwendung zur Verwaltung von Schülernoten für **einen einzigen Nutzer**. Sie ersetzt eine kommerzielle Lehrer-App (Lehrmeister) im Funktionsbereich Notenverwaltung.

### Ausdrückliche Nicht-Ziele

Diese Funktionen werden **nicht** gebaut und sollen die Architektur nicht beeinflussen:

- Stundenplan, Vertretungsplan, Kalender
- Anwesenheiten, Fehlzeiten, Hausaufgaben-Tracking
- Eltern- oder Schülerzugänge, Kommunikationsfunktionen
- Mehrbenutzerbetrieb, Rollen- und Rechtekonzept
- Offline-Fähigkeit / PWA mit lokaler Datenhaltung / Synchronisation
- Zeugnisdruck oder Zeugnislayouts

Der letzte Punkt ist wichtig: **Es wird bewusst keine Offline-Fähigkeit gebaut.** Die Anwendung ist eine reine Server-Anwendung. Ist die Verbindung nach Hause unterbrochen, wird auf Papier notiert und nachgetragen. Diese Entscheidung ist getroffen und soll nicht durch Caching-Konstruktionen aufgeweicht werden.

---

## 2. Betriebsumgebung (feststehend)

| Aspekt | Festlegung |
|---|---|
| Sprache | Python 3.11 |
| Datenbank | SQLite |
| ORM / Migrationen | SQLAlchemy + Alembic |
| Deployment | Docker, ein Container für die App, ein Tailscale-Sidecar |
| Host | TrueNAS SCALE, Compose-Stack über Dockge |
| Netzzugang | ausschließlich über Tailscale, keine Portfreigabe |
| Authentifizierung | keine in der Anwendung; Zugangsschutz über Tailscale-ACLs |
| TLS | keines — siehe unten |

### Daraus folgende harte Anforderungen

1. **Die Anwendung implementiert keine eigene Benutzerverwaltung, kein Login, kein Session-Handling, kein Passwort-Reset.** Sie liest auch keinen Identitäts-Header. Der Zugang wird vollständig davor geregelt: Der Container hat keinen veröffentlichten Port, hängt im Netz-Namespace eines Tailscale-Sidecars und ist nur über den Tailnet-Namen erreichbar. Wer den Knoten erreicht, darf alles. Diese Auslassung ist beabsichtigt und darf nicht „der Vollständigkeit halber" nachgerüstet werden.
2. **Die SQLite-Datei liegt auf einem lokalen ZFS-Dataset**, niemals auf einer SMB- oder NFS-Freigabe. App-Container und Datenbankdatei müssen auf demselben Host laufen.
3. `PRAGMA foreign_keys = ON` bei **jeder** Verbindung. SQLite hat Fremdschlüssel standardmäßig deaktiviert; ohne dieses Pragma entstehen verwaiste Noten beim Löschen von Klassen oder Kursen.
4. WAL-Modus aktivieren, `busy_timeout` setzen.
5. **Backup-Skript** als Teil der Lieferung: `VACUUM INTO` in ein Snapshot-Dataset, per Cron. Kein `cp` auf die laufende Datenbank. Ein dokumentierter, einmal durchgespielter **Restore-Test** gehört zur Abnahme.
6. **Kein TLS.** Version 1.0 verlangte HTTPS mit gültigem Zertifikat, weil der Kamerazugriff einen Secure Context braucht. Der Betreiber hat entschieden, darauf zu verzichten: Der Verkehr läuft ohnehin verschlüsselt durch das Tailnet, und ein Zertifikat für einen internen Namen ist zusätzlicher Betriebsaufwand. Folge für Abschnitt 7 dort beschrieben.
7. **Die Anwendung baut keine ausgehenden Verbindungen auf.** Keine CDNs, keine Telemetrie; alle Assets liegen lokal.

---

## 3. Datenmodell

### 3.1 Entitäten

**Schuljahr**
`id`, `bezeichnung` (z. B. „2026/27"), `beginn`, `ende`, `ist_aktiv`

**Halbjahr**
`id`, `schuljahr_id`, `nummer` (1 oder 2), `beginn`, `ende`

Ein Schuljahr wird immer mit **beiden** Halbjahren angelegt. Ohne das zweite ist die Jahresnote unberechenbar, und nichts in der Oberfläche würde zeigen, warum.

**Klasse**
`id`, `schuljahr_id`, `bezeichnung`, `notiz`
Eine Klasse gehört zu genau einem Schuljahr.

**Schüler**
`id`, `vorname`, `nachname`, `klasse_id`, `listennummer` (optional), `foto` (BLOB, nullable), `foto_geaendert_am`, `notiz`, `ist_aktiv`

- `ist_aktiv = false` statt Löschen, wenn ein Schüler die Klasse verlässt. Noten bleiben erhalten.
- Ein Schüler gehört zu genau einer Klasse pro Schuljahr.

**Kurs**
`id`, `klasse_id`, `fach` (Bezeichnung), `gewicht_halbjahr_1`, `gewicht_halbjahr_2`, `notiz`

- Eine Klasse enthält mehrere Kurse. Ein Kurs gehört zu genau einer Klasse.
- „Kurs" entspricht hier faktisch „Fach in dieser Klasse".
- Die beiden Gewichte steuern die Jahresnote (4.5), Vorgabe 50/50.

**Kursteilnahme** (n:m, Schüler ↔ Kurs)
`kurs_id`, `schueler_id`, `ist_aktiv`

- Beim Anlegen eines Kurses werden alle aktiven Schüler der Klasse eingetragen; ein später angelegter Schüler kommt in die bestehenden Kurse.
- Das explizite Zwischenmodell ist nötig, weil nicht jeder Schüler jeden Kurs seiner Klasse besucht (Differenzierung, Wahlpflicht, Zusatzqualifikation). Ohne dieses Modell entstehen später falsche Klassendurchschnitte.

**Notengruppe**
`id`, `kurs_id`, `halbjahr_id`, `bezeichnung` (z. B. „Klassenarbeiten", „Tests", „Mitarbeit"), `gewicht` (Dezimal), `reihenfolge`

- Gewichte werden **pro Kurs und Halbjahr** definiert.
- Gewichte müssen sich nicht auf 100 summieren (siehe 4.4).

**Leistung** (eine Bewertungssituation, z. B. „2. Klassenarbeit")
`id`, `notengruppe_id`, `bezeichnung`, `datum`, `gewicht` (Standard 1.0), `notiz`

**Note** (die Bewertung eines Schülers zu einer Leistung)
`id`, `leistung_id`, `schueler_id`, `notenwert` (Dezimal, kanonisch, nullable), `status` (`gewertet` | `nicht_gewertet` | `nicht_erbracht`), `notiz`, `erstellt_am`, `geaendert_am`

- `notenwert` bleibt NULL bei `nicht_erbracht`. Die 6,0, die dieser Status beisteuert, entsteht in der Berechnung und wird nie gespeichert — sonst wäre eine spätere Statusänderung nicht mehr von einer echten 6 zu unterscheiden.

**Notenüberschreibung** (manuelle pädagogische Festsetzung)
`id`, `schueler_id`, `kurs_id`, `bezugszeitraum` (`halbjahr_1` | `halbjahr_2` | `jahr`), `notenwert`, `quelle`, `begruendung`, `erstellt_am`

- Fachlich zwingend: Die Endnote ist eine pädagogische Entscheidung der Lehrkraft, keine reine Rechenoperation. Der berechnete Wert bleibt sichtbar, die Überschreibung tritt daneben. Der berechnete Wert wird **nie** überschrieben, sondern nur überlagert.
- Die Tabelle wird nur angehängt, nie geändert. Gültig ist der jüngste Eintrag je (Schüler, Kurs, Bezugszeitraum); damit ergibt sich die Historie einer Zeugnisnote ohne Zusatzaufwand.

### 3.2 Änderungshistorie

Jede Änderung an einer `Note` — Wert, Status, Löschung — wird in `note_historie` angehängt: `note_id`, `schueler_id`, `leistung_id`, `aktion`, alter und neuer Wert, alter und neuer Status, `zeitpunkt`. Reines Anhängen, ohne eigene Oberfläche. Grund: Bei Nachfragen zu einer Zeugnisnote ist die Frage „was stand da vorher" sonst nicht beantwortbar.

`note_id` trägt **keinen** Fremdschlüssel: Der Eintrag zu einer gelöschten Note muss die Note überleben. `schueler_id` und `leistung_id` tragen einen, damit die Löschfunktion aus Abschnitt 11 die Historie mitnimmt.

---

## 4. Notenlogik

Dies ist der fachlich anspruchsvollste Teil und der einzige, für den **Unit-Tests verpflichtend** sind. Ein Fehler hier fällt nicht auf, bis die Note im Zeugnis steht.

### 4.1 Kanonische Notendarstellung

Intern wird jede Note als Dezimalwert gespeichert. Umrechnung Tendenznote → Dezimalwert:

| Note | Wert | Note | Wert | Note | Wert |
|---|---|---|---|---|---|
| 1+ | 0,7 | 3+ | 2,7 | 5+ | 4,7 |
| 1 | 1,0 | 3 | 3,0 | 5 | 5,0 |
| 1− | 1,3 | 3− | 3,3 | 5− | 5,3 |
| 2+ | 1,7 | 4+ | 3,7 | 6 | 6,0 |
| 2 | 2,0 | 4 | 4,0 | | |
| 2− | 2,3 | 4− | 4,3 | | |

- **Tendenzen existieren von 1+ bis 5−. Die Note 6 hat keine Tendenzen.**
- Der Wert 0,7 wird bei der Ausgabe als „1+" dargestellt, nicht als „0,7".
- Eine **Rückumrechnung** berechneter Durchschnitte auf eine Tendenznote findet nicht statt. Die Tabelle dient der Eingabe und der Anzeige einzelner Noten; Ergebnisse werden als Dezimalzahl und als ganze Notenstufe ausgewiesen (4.4).

### 4.2 Notenschlüssel — entfällt

Version 1.0 sah einen IHK- und einen RLP-Notenschlüssel als editierbare
Datensätze vor. Mit dem Wegfall der Punkteeingabe (4.3) gibt es keine
Prozentgrenzen und keine Umrechnung mehr. Die Abschnittsnummer bleibt
unbesetzt, damit die übrigen Nummern gültig bleiben.

### 4.3 Eingabe

Noten werden ausschließlich **direkt als Notenstufe mit Tendenz** eingetragen (Auswahl aus 1+ … 6). Eine Punkteeingabe mit Umrechnung über einen Notenschlüssel (4.2) gibt es nicht; die Umrechnung von Punkten in Noten findet außerhalb dieser Anwendung statt.

**Status einer Note:**

- `gewertet` — normal
- `nicht_gewertet` — Leistung existiert, geht nicht in die Berechnung ein (z. B. entschuldigt gefehlt). Wird angezeigt, aber aus allen Mittelwerten ausgeschlossen.
- `nicht_erbracht` — geht als 6 (6,0) in die Berechnung ein.

Die Unterscheidung zwischen „nicht gewertet" und „fehlt" ist zwingend. Ein fehlender Wert darf **niemals** implizit als 0 oder als 6 behandelt werden.

### 4.4 Berechnung der Halbjahresnote

**Einstufig.** Jede Note geht mit dem Produkt aus Gruppengewicht und Leistungsgewicht in ein einziges gewichtetes Mittel ein:

```
Halbjahresnote = Σ(notenwert × gruppengewicht × leistungsgewicht)
                 ─────────────────────────────────────────────────
                 Σ(gruppengewicht × leistungsgewicht)
```

Berücksichtigt werden Noten mit Status `gewertet` (mit ihrem Wert) und `nicht_erbracht` (mit 6,0). `nicht_gewertet` fällt heraus.

Damit hängt die Wirkung einer Notengruppe davon ab, wie viele Noten sie enthält: Vier Tests wiegen bei gleichem Gruppengewicht mehr als eine einzelne Klassenarbeit. Das ist gewollt.

Eine Notengruppe **ohne gewertete Note hat kein Gewicht** — sie taucht weder im Zähler noch im Nenner auf. Eine gesonderte Normalisierung ist dafür nicht nötig.

**Rundung:** Der berechnete Wert wird auf **eine** Nachkommastelle gerundet (z. B. 2,6). Daraus wird die **ganze Notenstufe** gebildet. Bei Gleichstand wird zur **besseren** Note gerundet, nicht kaufmännisch: 2,50 wird zur 2.

> Weil die ganze Note aus dem bereits gerundeten Wert entsteht, liegt die tatsächliche Grenze nicht bei einem Rohwert von 2,50, sondern oberhalb von 2,55: 2,54 wird zu 2,5 und damit zur 2, erst 2,56 wird zu 2,6 und damit zur 3.

### 4.5 Berechnung der Jahresnote

**Wichtiger fachlicher Hinweis — hier weicht die Umsetzung von der Rechtslage ab:**

Die Schulordnung für die öffentlichen berufsbildenden Schulen in Rheinland-Pfalz sieht vor, dass die Einzelnote für ein Lernfeld/Fach „aufgrund der Leistungen während des ganzen Schuljahres **unter stärkerer Berücksichtigung der Leistungen im letzten Schulhalbjahr**" festgesetzt wird. Ein arithmetisches Mittel 50/50 bildet das nicht ab.

**Umsetzung:**

- Die Gewichtung der beiden Halbjahre ist pro Kurs konfigurierbar (`kurs.gewicht_halbjahr_1` / `_2`), **Vorgabe 50/50**.
- Gewichtet werden die beiden **Halbjahresnoten**, nicht die Rohdurchschnitte. Maßgeblich ist die festgesetzte Halbjahresnote; ist ein Halbjahr nicht festgesetzt, zählt der berechnete Wert.
- Solange ein Halbjahr keine berechenbare Note hat, wird **keine** Jahresnote angezeigt — kein Rückfall auf das einzelne Halbjahr. Der praktische Fall ist der Januar.
- Die manuelle Überschreibung (3.1) hat in jedem Fall Vorrang und ist der eigentliche Weg zur Zeugnisnote. Dort wird die Anforderung der Schulordnung erfüllt, nicht in der Vorgabegewichtung.

**Zweiter rechtlicher Hinweis:** § 53 der Schulordnung RLP kennt ein sechsstufiges Notensystem; Tendenzen („3+") sind darin für Zeugnisnoten nicht vorgesehen. Konsequenz: Tendenzen sind für **Einzelleistungen und interne Zwischenstände** zulässig und gewünscht, die ausgewiesene **Halbjahres- und Jahresnote** wird zusätzlich als ganze Notenstufe dargestellt. Beide Werte stehen nebeneinander. Eine Überschreibung ist immer eine ganze Notenstufe 1 bis 6.

### 4.6 Verbindliche Testfälle

Diese Fälle sind als Unit-Tests implementiert (`tests/test_berechnung.py`):

| Nr. | Szenario | Erwartung |
|---|---|---|
| T-1 | Gruppe „KA" (Gew. 50) mit 2,0 und 3,0; Gruppe „Mitarbeit" (Gew. 50) mit 1,0 | 2,0 → Note 2 |
| T-2 | Wie T-1, Gruppe „Tests" (Gew. 30) zusätzlich, aber leer | Ergebnis identisch zu T-1 |
| T-3 | Eine Note mit Status `nicht_gewertet` | Note wird angezeigt, ändert das Ergebnis nicht |
| T-4 | Eine Note mit Status `nicht_erbracht` | geht als 6,0 ein |
| T-7 | Kurs ohne jede Note | keine Berechnung, keine Division durch null, leere Anzeige |
| T-8 | Halbjahresnoten 2,0 und 3,0, Gewichtung 40/60 | 2,6 → Note 3 |
| T-9 | Manuelle Überschreibung auf 2 bei berechnet 2,6 | Anzeige „2 (berechnet 2,6)" |

Die Nummerierung folgt Version 1.0. T-5, T-6 und T-10 prüften Punkteeingabe und Notenschlüssel und entfallen ersatzlos.

---

## 5. Ansichten

### 5.1 Klassenansicht

- Kachel- oder Listendarstellung aller aktiven Schüler der Klasse **mit Foto und Namen**.
- Umschaltbare Sortierung: **nach Vorname** oder **nach Nachname**. Die Einstellung wird persistiert.
- Klick auf einen Schüler öffnet die Schüleransicht.
- Einstieg zum Anlegen neuer Schüler inkl. Fotoerfassung.

### 5.2 Schüleransicht

- Erreichbar über ein **Suchfeld, das über die gesamte Datenbank sucht** — alle Klassen, alle Schuljahre, nicht nur die aktuelle Klasse. Suche über Vor- und Nachname, tolerant gegenüber Teilstrings.
- Zeigt: Foto, Vor- und Nachname, Klasse, Schuljahr.
- Zeigt **sämtliche Noten des Schülers**, gruppiert nach Kurs/Fach, innerhalb des Kurses nach Notengruppe, chronologisch.
- Pro Kurs: Halbjahresnote(n), Jahresnote, ggf. Überschreibung mit Begründung.

### 5.3 Kurs-/Fachübersicht

- Eine Übersichtsseite **pro Kurs** mit allen Noten aller Teilnehmer.
- Matrixdarstellung: Zeilen = Schüler, Spalten = Leistungen, gruppiert nach Notengruppe mit sichtbarer Gruppengewichtung.
- Rechte Spalten: Gesamtmittel als Dezimalwert und als ganze Notenstufe. **Kein Gruppenmittel** — bei einstufiger Berechnung (4.4) kommt ein solcher Zwischenwert nicht vor, und eine Spalte, die zum Nachrechnen einlädt und dabei nicht aufgeht, schadet mehr als sie nützt.
- Fußzeile: Klassendurchschnitt je Leistung, Notenverteilung auf die Stufen 1 bis 6.
- Umschaltung zwischen Halbjahr 1, Halbjahr 2 und Jahresansicht.
- Nur lesend; jede Spaltenüberschrift verlinkt in die Serieneingabe.

### 5.4 Noteneingabe (Serieneingabe)

- Eine Leistung auswählen, dann alle Teilnehmer nacheinander durchgehen, ohne Seitenwechsel.
- Auf dem Handy bedienbar: große Eingabeflächen.
- Jede Zeile bestätigt das Speichern sichtbar und erst nach der Antwort des Servers (siehe Abschnitt 10).

### 5.5 Verwaltung

Schuljahre, Halbjahre, Klassen, Kurse, Notengruppen mit Gewichten, Kursteilnahmen.

---

## 6. Sortierung und Namensanzeige

- Sortierung nach Vorname oder Nachname umschaltbar, Einstellung persistiert.
- Anzeigeformat konfigurierbar: „Vorname Nachname" oder „Nachname, Vorname".
- Sortierung muss deutsche Umlaute korrekt einordnen (Ä wie A). Reine ASCII-Sortierung ist nicht akzeptabel.

---

## 7. Fotoerfassung

Ablauf auf dem Android-Gerät:

1. Schaltfläche „Foto aufnehmen" in der Schülerbearbeitung.
2. Öffnet die Kamera. Umsetzung über `<input type="file" accept="image/*" capture="environment">`.
3. Nach der Aufnahme: **Zuschneiden im Browser** (quadratisch, verschiebbar, über einen Schieberegler skalierbar — kein Pinch-Zoom, weil das Telefon im Unterricht einhändig gehalten wird).
4. Speichern.

### Technische Randbedingungen

- **Ohne TLS ist kein Secure Context vorhanden** (Abschnitt 2). Der `capture`-Hinweis kann dadurch ignoriert werden; dann öffnet sich statt der Kamera der normale Auswahldialog, in dem die Kamera-App als Quelle wählbar ist. Ein Tipper mehr, kein Ausfall. Der Weg über `getUserMedia`, der zwingend HTTPS bräuchte, wird nicht verwendet.
- Bild wird clientseitig auf max. **512 × 512 px** verkleinert und als JPEG (Qualität ~80) hochgeladen. Kein Upload von Originalen aus der Handykamera.
- **Speicherung als BLOB in der SQLite-Datenbank**, nicht als Datei im Dateisystem. Begründung: Ein einziges Backup-Artefakt, garantiert konsistent zum Datenbankstand.
- Serverseitige Prüfung: nur JPEG/PNG, Größenlimit, Begrenzung der Bildpunkte, **Neucodierung** des Bildes beim Empfang. Das verwirft eingebettete Metadaten und potenziell manipulierte Dateiinhalte. Der vom Client gelieferte Dateiname wird nirgends verwendet.

---

## 8. Export

Beide Formate über die Verwaltung, jeweils über den **gesamten** Datenbestand — alle Schuljahre, alle Klassen, alle Kurse:

- **XLSX**, ein Blatt je Kurs. Kopfbereich mit Klasse und Kurs, je Zeile ein Schüler, darüber drei um 90° gedrehte Beschriftungszeilen für Halbjahr, Notengruppe mit Gewicht und Leistung mit Datum. Zwischen zwei Notengruppen und vor den Jahresnoten je eine leere Spalte. Namensspalte und Beschriftungen bleiben beim Scrollen stehen.
- **Markdown**, ein Abschnitt je Kurs.

Beide entstehen aus demselben Modell wie die Kursübersicht am Bildschirm; zwei getrennte Rechenwege für dieselben Noten laufen sonst auseinander.

Der Export entsteht im Arbeitsspeicher und wird direkt ausgeliefert — keine temporäre Datei, kein Ablageort, kein Zeitplan. **Er enthält Klarnamen.**

---

## 9. Geklärte Punkte

Die offenen Punkte aus Version 1.0 sind sämtlich entschieden:

| Nr. | Frage | Entscheidung |
|---|---|---|
| O-1 | Prozentgrenzen des RLP-Standardschlüssels | **Entfällt** — keine Punkteeingabe, kein Notenschlüssel |
| O-2 | Leere Notengruppen bei der Gewichtung | Kein Gewicht; fällt aus der Berechnung (4.4) |
| O-3 | Rundungsregel und Schwelle | Eine Nachkommastelle, Gleichstand zur besseren Note (4.4) |
| O-4 | „Mitarbeit als Punktesystem" | **Entfällt** mit der Punkteeingabe |
| O-5 | Noten aus Halbjahr 1 in Halbjahr 2 sichtbar | Ja |
| O-6 | Layout des Tabellenexports | Wie in Abschnitt 8 beschrieben |
| O-7 | Gewichtung der Halbjahre für die Jahresnote | 50/50, pro Kurs änderbar (4.5) |
| O-8 | Klassenübergreifende Kurse | **Nein** — `kurs.klasse_id` bleibt NOT NULL |

Die in Version 1.0 mit **(L)** markierten Punkte wurden nicht anhand der Lehrmeister-App beantwortet, sondern vom Auftraggeber direkt entschieden.

---

## 10. Nicht-funktionale Anforderungen

- **Bedienbarkeit auf dem Smartphone im Unterricht ist der Maßstab**, nicht die Desktop-Ansicht. Eingabeflächen groß genug für Bedienung im Stehen.
- Antwortzeiten unkritisch (ein Nutzer, Datenbestand im MB-Bereich). Keine Optimierung ohne gemessenen Anlass.
- Fehlerverhalten: Beim Speichern einer Note muss eindeutig erkennbar sein, ob gespeichert wurde. Stilles Verwerfen bei Verbindungsabbruch ist der gravierendste denkbare Fehler dieser Anwendung.
- Keine externen CDNs, keine Telemetrie, keine Analytics. Alle Assets werden mit ausgeliefert. Die Anwendung darf keine ausgehenden Verbindungen aufbauen.
- Abhängigkeiten werden mit gepinnten Versionen geführt; ein Aktualisierungspfad ist zu dokumentieren.

---

## 11. Datenschutzrahmen

Die Anwendung verarbeitet Klarnamen und Lichtbilder von Schülerinnen und Schülern. Der Betrieb auf privateigenen Geräten unterliegt in Rheinland-Pfalz § 55 Abs. 3 der Schulordnung für die öffentlichen berufsbildenden Schulen: Er setzt die Genehmigung der Schulleitung im Einzelfall voraus, das Einverständnis zur Kontrolle des Geräts unter denselben Bedingungen wie bei Dienstgeräten, sowie die Wahrung der Belange des Datenschutzes.

Daraus folgt konkret:

- Eine **Löschfunktion** pro Schüler und pro Schuljahr, die Noten, Foto und Historie vollständig entfernt, ist Pflichtbestandteil. Umgesetzt mit vorgeschalteter Zählung des Umfangs und getippter Bestätigung; die Daten werden anschließend auch physisch aus der Datei entfernt.
- Der Datenbestand muss **exportierbar** sein (Abschnitt 8), damit kein Lock-in entsteht.
- Es dürfen keine Daten die Anwendung verlassen außer durch den ausdrücklich ausgelösten Export.

Die Klärung der Genehmigung liegt beim Auftraggeber und ist keine Aufgabe des Entwicklungsprojekts.

---

## Änderungen gegenüber Version 1.0

Version 1.0 war das Übergabedokument an das Entwicklungsprojekt und beschrieb den Soll-Stand vor der Umsetzung. Version 1.1 beschreibt den gebauten Stand. Geändert wurde:

| Abschnitt | Änderung | Grund |
|---|---|---|
| 2 | Traefik und Authelia entfallen; Zugang allein über Tailscale | Beide wurden nicht eingesetzt; der Sidecar-Aufbau erfüllt die Anforderung direkt |
| 2 | **HTTPS-Pflicht gestrichen** | Entscheidung des Betreibers: Verkehr läuft verschlüsselt durch das Tailnet, ein internes Zertifikat wäre zusätzlicher Betriebsaufwand |
| 3.1 | Entität *Notenschlüssel* gestrichen; `max_punkte`, `punkte`, `eingabeart`, `notenschluessel_id` entfallen | Folge des Wegfalls der Punkteeingabe |
| 3.1 | `kurs.gewicht_halbjahr_1` / `_2` ergänzt, `notenueberschreibung.quelle` ergänzt | Umsetzung von O-7 und der Unterscheidung manueller von abgeleiteten Festsetzungen |
| 3.1 | `note.notenwert` ist nullable | Damit `nicht_erbracht` von einer echten 6 unterscheidbar bleibt |
| 4.2, 4.3 | Notenschlüssel und Punkteeingabe gestrichen | Entscheidung des Auftraggebers zu O-1: Noten werden direkt als Stufe mit Tendenz eingetragen, die Umrechnung aus Punkten geschieht außerhalb |
| 4.4 | Berechnung **einstufig** statt zweistufig | Gewollt ist, dass viele kleine Noten stärker wiegen. Die einstufige Rechnung trifft zudem den Erwartungswert aus T-1 exakt, die zweistufige nicht |
| 4.4 | Eine statt zwei Nachkommastellen | Entscheidung des Auftraggebers |
| 4.4 | Gleichstand zur besseren Note statt kaufmännisch | Entscheidung des Auftraggebers |
| 4.4 | Normalisierung leerer Gruppen entfällt als eigene Regel | Bei einstufiger Rechnung ergibt sie sich von selbst |
| 4.1 | Rückumrechnung auf Tendenznoten gestrichen | Ergebnisse werden als Dezimalwert und ganze Stufe gezeigt |
| 4.5 | Vorgabegewichtung 50/50 statt 40/60 | Entscheidung des Auftraggebers zu O-7; die Rechtslage wird über die Überschreibung erfüllt |
| 4.6 | T-5, T-6, T-10 gestrichen | Prüften Punkteeingabe und Notenschlüssel |
| 5.3 | Spalte „Gruppenmittel" gestrichen | Existiert bei einstufiger Berechnung nicht |
| 5.4 | Anzeige der Note neben dem Punktefeld gestrichen | Kein Punktefeld mehr |
| 7 | Secure-Context-Anforderung durch den beschriebenen Rückfallweg ersetzt | Folge des TLS-Verzichts |
| 8 | Export konkretisiert, XLSX verbindlich statt empfohlen | Umsetzung von O-6 |
| 9 | Offene Punkte durch die getroffenen Entscheidungen ersetzt | Alle acht geklärt |
