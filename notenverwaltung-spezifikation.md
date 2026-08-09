# Notenverwaltung – Projektspezifikation

**Version:** 1.0 · **Stand:** 09.08.2026
**Zweck:** Übergabedokument an das Entwicklungsprojekt. Beschreibt, *was* gebaut wird, nicht *wie*.
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
| Sprache | Python |
| Datenbank | SQLite |
| ORM / Migrationen | SQLAlchemy + Alembic |
| Deployment | Docker, ein Container für die App |
| Host | TrueNAS SCALE, Custom App via Docker-Compose-YAML |
| Reverse Proxy / TLS | Traefik (vorhanden) |
| Authentifizierung | Authelia Forward Auth (vorhanden) |
| Netzzugang | ausschließlich über Tailscale, keine Portfreigabe |

### Daraus folgende harte Anforderungen

1. **Die Anwendung implementiert keine eigene Benutzerverwaltung, kein Login, kein Session-Handling, kein Passwort-Reset.** Authentifizierung geschieht vollständig vorgelagert durch Authelia. Die App vertraut dem vom Proxy gesetzten Identitäts-Header. Diese Auslassung ist beabsichtigt und darf nicht „der Vollständigkeit halber" nachgerüstet werden.
2. **Die SQLite-Datei liegt auf einem lokalen ZFS-Dataset**, niemals auf einer SMB- oder NFS-Freigabe. App-Container und Datenbankdatei müssen auf demselben Host laufen.
3. `PRAGMA foreign_keys = ON` bei **jeder** Verbindung. SQLite hat Fremdschlüssel standardmäßig deaktiviert; ohne dieses Pragma entstehen verwaiste Noten beim Löschen von Klassen oder Kursen.
4. WAL-Modus aktivieren, `busy_timeout` setzen.
5. **Backup-Skript** als Teil der Lieferung: `VACUUM INTO` in ein Snapshot-Dataset, per Cron. Kein `cp` auf die laufende Datenbank. Ein dokumentierter, einmal durchgespielter **Restore-Test** gehört zur Abnahme.
6. Die App bindet nur an das Docker-interne Netz; nach außen ist ausschließlich Traefik erreichbar.
7. **HTTPS mit gültigem Zertifikat ist zwingend**, nicht optional — siehe Abschnitt 7 (Kamerazugriff funktioniert nur im Secure Context).

---

## 3. Datenmodell

### 3.1 Entitäten

**Schuljahr**
`id`, `bezeichnung` (z. B. „2026/27"), `beginn`, `ende`, `ist_aktiv`

**Halbjahr**
`id`, `schuljahr_id`, `nummer` (1 oder 2), `beginn`, `ende`

**Klasse**
`id`, `schuljahr_id`, `bezeichnung`, `notiz`
Eine Klasse gehört zu genau einem Schuljahr.

**Schüler**
`id`, `vorname`, `nachname`, `klasse_id`, `listennummer` (optional), `foto` (BLOB, nullable), `foto_geaendert_am`, `notiz`, `ist_aktiv`

- `ist_aktiv = false` statt Löschen, wenn ein Schüler die Klasse verlässt. Noten bleiben erhalten.
- Ein Schüler gehört zu genau einer Klasse pro Schuljahr.

**Kurs**
`id`, `klasse_id`, `fach` (Bezeichnung), `notenschluessel_id` (Standard für neue Leistungen), `notiz`

- Eine Klasse enthält mehrere Kurse. Ein Kurs gehört zu genau einer Klasse.
- „Kurs" entspricht hier faktisch „Fach in dieser Klasse".

**Kursteilnahme** (n:m, Schüler ↔ Kurs)
`kurs_id`, `schueler_id`, `ist_aktiv`

- Beim Anlegen eines Kurses werden standardmäßig alle aktiven Schüler der Klasse eingetragen.
- Das explizite Zwischenmodell ist nötig, weil nicht jeder Schüler jeden Kurs seiner Klasse besucht (Differenzierung, Wahlpflicht, Zusatzqualifikation). Ohne dieses Modell entstehen später falsche Klassendurchschnitte.

**Notengruppe**
`id`, `kurs_id`, `halbjahr_id`, `bezeichnung` (z. B. „Klassenarbeiten", „Tests", „Mitarbeit"), `gewicht` (Dezimal), `reihenfolge`

- Gewichte werden **pro Kurs und Halbjahr** definiert.
- Gewichte müssen sich nicht auf 100 summieren; es wird normalisiert (siehe 4.4).

**Leistung** (eine Bewertungssituation, z. B. „2. Klassenarbeit")
`id`, `notengruppe_id`, `bezeichnung`, `datum`, `notenschluessel_id` (nullable, sonst Kurs-Standard), `max_punkte` (nullable), `gewicht` (Standard 1.0), `notiz`

**Note** (die Bewertung eines Schülers zu einer Leistung)
`id`, `leistung_id`, `schueler_id`, `eingabeart` (`note` | `punkte`), `punkte` (nullable), `notenwert` (Dezimal, kanonisch), `status` (`gewertet` | `nicht_gewertet` | `nicht_erbracht`), `notiz`, `erstellt_am`, `geaendert_am`

**Notenschlüssel**
`id`, `bezeichnung`, `typ` (`ihk` | `rlp_standard` | `benutzerdefiniert`), `schwellen` (JSON: Prozentgrenze → Notenwert)

**Notenüberschreibung** (manuelle pädagogische Festsetzung)
`id`, `schueler_id`, `kurs_id`, `bezugszeitraum` (`halbjahr_1` | `halbjahr_2` | `jahr`), `notenwert`, `begruendung`, `erstellt_am`

- Fachlich zwingend: Die Endnote ist eine pädagogische Entscheidung der Lehrkraft, keine reine Rechenoperation. Der berechnete Wert bleibt sichtbar, die Überschreibung tritt daneben. Der berechnete Wert wird **nie** überschrieben, sondern nur überlagert.

### 3.2 Änderungshistorie

Jede Änderung an einer `Note` (Wert, Status, Löschung) wird in einer Tabelle `note_historie` mitgeschrieben: `note_id`, `alter_wert`, `neuer_wert`, `zeitpunkt`. Ohne Aufwand für eine UI — reines Anhängen. Grund: Bei Nachfragen zu einer Zeugnisnote ist die Frage „was stand da vorher" sonst nicht beantwortbar.

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
- Bei Rückumrechnung eines berechneten Durchschnitts auf eine Tendenznote wird auf den nächstgelegenen Tabellenwert gerundet.

### 4.2 Notenschlüssel

Zwei Schlüssel sind vorzusehen, weiterer benutzerdefinierter Schlüssel optional.

**IHK-Schlüssel (bundeseinheitlich, für IHK-Prüfungen und prüfungsnahe Leistungen)**

| ab Prozent | Note |
|---|---|
| 92 | 1 |
| 81 | 2 |
| 67 | 3 |
| 50 | 4 |
| 30 | 5 |
| 0 | 6 |

**RLP-Standardschlüssel (allgemeiner Schulnotenschlüssel, 1–6 mit Tendenzen)**

Die Prozentgrenzen sind vom Auftraggeber vor Implementierung festzulegen (siehe Abschnitt 9, offener Punkt O-1). Bis dahin: linearer Schlüssel mit Bestehensgrenze 50 % als Platzhalter, Grenzen in der Oberfläche editierbar.

**Anforderung:** Notenschlüssel sind Datensätze, keine Konstanten im Code. Die Prozentgrenzen müssen in der Oberfläche editierbar sein, ohne Deployment.

### 4.3 Eingabe

Pro Leistung wählbar:

- **Direkte Notenvergabe:** Auswahl aus 1+ … 6.
- **Punktevergabe:** Eingabe erreichter Punkte, `max_punkte` an der Leistung hinterlegt. Prozentwert → Notenschlüssel → Notenwert. **Sowohl Punkte als auch resultierender Notenwert werden gespeichert**, damit eine nachträgliche Änderung des Notenschlüssels nachvollziehbar bleibt und neu berechnet werden kann.

**Status einer Note:**
- `gewertet` — normal
- `nicht_gewertet` — Leistung existiert, geht nicht in die Berechnung ein (z. B. entschuldigt gefehlt). Wird angezeigt, aber aus allen Mittelwerten ausgeschlossen.
- `nicht_erbracht` — geht als 6 (6,0) in die Berechnung ein.

Die Unterscheidung zwischen „nicht gewertet" und „fehlt" ist zwingend. Ein fehlender Wert darf **niemals** implizit als 0 oder als 6 behandelt werden.

### 4.4 Berechnung der Halbjahresnote

Zweistufig:

1. **Gruppenmittel:** Für jede Notengruppe der gewichtete Mittelwert der zugehörigen Noten mit Status `gewertet` oder `nicht_erbracht`, unter Berücksichtigung des `gewicht`-Feldes je Leistung.
2. **Gesamtmittel:** Gewichteter Mittelwert der Gruppenmittel nach `gewicht` der Notengruppen.

**Normalisierung:** Enthält eine Notengruppe keine einzige gewertete Note, wird sie aus der Berechnung entfernt und die Gewichte der verbleibenden Gruppen auf ihre Summe normalisiert. Beispiel: Gruppen 50/30/20, „Tests" (30) ist leer → Berechnung mit 50/20, normalisiert auf 71,4 % / 28,6 %.

Ohne diese Regel produziert die erste Klassenarbeit des Halbjahres eine systematisch verzerrte Zwischennote.

**Rundung:** Der berechnete Wert wird auf zwei Nachkommastellen angezeigt (z. B. 2,43). Zusätzlich wird die daraus resultierende **ganze Notenstufe** ausgewiesen. Die Rundungsschwelle ist konfigurierbar, Vorgabe: kaufmännisch auf die nächste ganze Note (2,49 → 2; 2,50 → 3).

### 4.5 Berechnung der Jahresnote

**Wichtiger fachlicher Hinweis — hier weicht die Vorgabe von der Rechtslage ab:**

Die ursprüngliche Anforderung lautete „Jahresnote = Mittel aus den beiden Halbjahresnoten". Die Schulordnung für die öffentlichen berufsbildenden Schulen in Rheinland-Pfalz sieht vor, dass die Einzelnote für ein Lernfeld/Fach „aufgrund der Leistungen während des ganzen Schuljahres **unter stärkerer Berücksichtigung der Leistungen im letzten Schulhalbjahr**" festgesetzt wird. Ein arithmetisches Mittel 50/50 bildet das nicht ab.

**Umsetzung:**
- Die Gewichtung der beiden Halbjahre ist **konfigurierbar** (Vorgabe z. B. 40 % / 60 % zugunsten des zweiten Halbjahres), einstellbar pro Kurs.
- Es wird sowohl das reine Mittel als auch der gewichtete Wert angezeigt, damit die Lehrkraft beide sieht.
- Die manuelle Überschreibung (siehe 3.1) hat in jedem Fall Vorrang und ist der eigentliche Weg zur Zeugnisnote.

**Zweiter rechtlicher Hinweis:** § 53 der Schulordnung RLP kennt ein sechsstufiges Notensystem; Tendenzen („3+") sind darin für Zeugnisnoten nicht vorgesehen. Konsequenz für die Anwendung: Tendenzen sind für **Einzelleistungen und interne Zwischenstände** zulässig und gewünscht, die ausgewiesene **Halbjahres- und Jahresnote muss aber als ganze Notenstufe** darstellbar sein. Beide Werte nebeneinander anzeigen.

### 4.6 Verbindliche Testfälle

Diese Fälle sind als Unit-Tests zu implementieren:

| Nr. | Szenario | Erwartung |
|---|---|---|
| T-1 | Gruppe „KA" (Gew. 50) mit 2,0 und 3,0; Gruppe „Mitarbeit" (Gew. 50) mit 1,0 | 2,00 → Note 2 |
| T-2 | Wie T-1, Gruppe „Tests" (Gew. 30) zusätzlich, aber leer | Ergebnis identisch zu T-1 (Normalisierung) |
| T-3 | Eine Note mit Status `nicht_gewertet` | Note wird angezeigt, ändert das Ergebnis nicht |
| T-4 | Eine Note mit Status `nicht_erbracht` | geht als 6,0 ein |
| T-5 | Punkteeingabe 45 von 50, IHK-Schlüssel | 90 % → Note 2 |
| T-6 | Punkteeingabe 46 von 50, IHK-Schlüssel | 92 % → Note 1 (Grenzfall exakt auf der Schwelle) |
| T-7 | Kurs ohne jede Note | keine Berechnung, keine Division durch null, leere Anzeige |
| T-8 | Halbjahresnoten 2,0 und 3,0, Gewichtung 40/60 | 2,60 → Note 3 |
| T-9 | Manuelle Überschreibung auf 2 bei berechnet 2,60 | Anzeige „2 (berechnet 2,60)" |
| T-10 | Notenschlüssel wird nachträglich geändert | alle punktebasierten Noten des Kurses werden neu berechnet, notenbasierte bleiben unverändert |

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
- Rechte Spalten: Gruppenmittel, Gesamtmittel, ganze Notenstufe.
- Fußzeile: Klassendurchschnitt je Leistung, Notenverteilung.
- Umschaltung zwischen Halbjahr 1, Halbjahr 2 und Jahresansicht.

### 5.4 Noteneingabe (Serieneingabe)

- Eine Leistung auswählen, dann alle Teilnehmer nacheinander durchgehen, ohne Seitenwechsel.
- Auf dem Handy bedienbar: große Eingabeflächen, Weiter-Sprung nach Eingabe.
- Bei Punkteeingabe wird die resultierende Note direkt neben dem Feld angezeigt.

### 5.5 Verwaltung

Schuljahre, Halbjahre, Klassen, Kurse, Notengruppen mit Gewichten, Notenschlüssel, Kursteilnahmen.

---

## 6. Sortierung und Namensanzeige

- Sortierung nach Vorname oder Nachname umschaltbar, Einstellung persistiert.
- Anzeigeformat konfigurierbar: „Vorname Nachname" oder „Nachname, Vorname".
- Sortierung muss deutsche Umlaute korrekt einordnen (Ä wie A). Reine ASCII-Sortierung ist nicht akzeptabel.

---

## 7. Fotoerfassung

Ablauf auf dem Android-Gerät:

1. Schaltfläche „Foto aufnehmen" in der Schülerbearbeitung.
2. Öffnet direkt die Kamera. Umsetzung über `<input type="file" accept="image/*" capture="environment">`.
3. Nach der Aufnahme: **Zuschneiden im Browser** (quadratisch, mit verschiebbarem und skalierbarem Ausschnitt).
4. Speichern.

### Technische Randbedingungen

- **Der Kamerazugriff funktioniert nur im Secure Context.** Die Anwendung muss über HTTPS mit gültigem Zertifikat erreichbar sein — auch innerhalb des Tailnets. Über Traefik mit einem echten Zertifikat auf einen erreichbaren Hostnamen lösen; ein selbstsigniertes Zertifikat oder Zugriff per IP-Adresse führt zu schwer diagnostizierbarem Fehlverhalten.
- Bild wird clientseitig auf max. **512 × 512 px** verkleinert und als JPEG (Qualität ~80) hochgeladen. Kein Upload von Originalen aus der Handykamera.
- **Speicherung als BLOB in der SQLite-Datenbank**, nicht als Datei im Dateisystem. Begründung: Ein einziges Backup-Artefakt, garantiert konsistent zum Datenbankstand. Bei der genannten Bildgröße und wenigen hundert Schülern bleibt die Datenbank im niedrigen zweistelligen MB-Bereich.
- Serverseitige Prüfung: nur JPEG/PNG, Größenlimit, Neucodierung des Bildes beim Empfang (verwirft eingebettete Metadaten und potenziell manipulierte Dateiinhalte).

---

## 8. Export

**Textexport (Pflicht):** Alle Noten als strukturierter Text (Markdown oder CSV), je Fach ein Abschnitt.

**Tabellenexport (empfohlen):** Eine Tabellendatei mit **einem Blatt pro Fach**, jeweils alle Noten der Kursteilnehmer, Gruppenmittel, Halbjahres- und Jahresnote.

Einschätzung zum Aufwand: Der Tabellenexport ist mit `openpyxl` (XLSX) oder `odfpy` (ODS) kein nennenswerter Mehraufwand gegenüber dem Textexport — im Wesentlichen dieselbe Datenaufbereitung mit anderem Schreibziel. Die im Vorfeld geäußerte Sorge, das könne „deutlich komplizierter" werden, trifft nicht zu. **Empfehlung: direkt umsetzen.** XLSX wird von LibreOffice Calc problemlos gelesen.

Der Export enthält Klarnamen. Er wird nicht automatisch irgendwohin geschrieben, sondern nur auf ausdrückliche Anforderung erzeugt und heruntergeladen.

---

## 9. Offene Punkte

Diese Punkte sind vor bzw. während der Umsetzung vom Auftraggeber zu klären. Für die mit **(L)** markierten gilt: Referenzverhalten ist die Lehrmeister-App — dort nachsehen und das Verhalten nachbauen.

| Nr. | Offene Frage |
|---|---|
| O-1 | **Prozentgrenzen des RLP-Standardschlüssels.** Welche Grenzen gelten an der eigenen Schule bzw. laut Fachkonferenzbeschluss? Linear oder mit Knick? Gibt es Tendenzgrenzen oder nur ganze Noten? |
| O-2 | **(L)** Wie behandelt Lehrmeister leere Notengruppen bei der Gewichtung — Normalisierung wie in 4.4 oder anders? |
| O-3 | **(L)** Welche Rundungsregel und welche Schwelle verwendet Lehrmeister für die Zeugnisnote? |
| O-4 | **(L)** Wie rechnet Lehrmeister „Mitarbeit als Punktesystem" in eine Note um? Wird diese Funktion überhaupt benötigt? |
| O-5 | **(L)** Wie stellt Lehrmeister den Halbjahresübergang dar — bleiben die Noten aus Halbjahr 1 in Halbjahr 2 sichtbar? |
| O-6 | **(L)** Layout des Excel-Exports in Lehrmeister als Vorlage. |
| O-7 | Gewichtung Halbjahr 1 zu Halbjahr 2 für die Jahresnote (siehe 4.5) — welcher Wert wird als Vorgabe gesetzt? |
| O-8 | Werden Kurse benötigt, die klassenübergreifend sind (Schüler aus mehreren Klassen in einem Kurs)? Das Datenmodell in 3.1 unterstützt das bewusst **nicht**. Falls doch nötig, muss `Kurs.klasse_id` entfallen. |

**Hinweis zur Recherche:** Die Hilfeartikel von Lehrmeister (Kategorien & Gewichtung, Berechnung & Prognosen, Halbjahre, Notensystem ändern, Sortierung & Namensanzeige, Daten als Excel speichern) sind über die Website nur innerhalb einer JavaScript-Anwendung abrufbar und waren extern nicht auslesbar. Die Inhalte müssen daher direkt in der installierten App eingesehen werden. Die Artikelüberschriften decken sich mit den oben markierten offenen Punkten.

---

## 10. Nicht-funktionale Anforderungen

- **Bedienbarkeit auf dem Smartphone im Unterricht ist der Maßstab**, nicht die Desktop-Ansicht. Eingabeflächen groß genug für Bedienung im Stehen.
- Antwortzeiten unkritisch (ein Nutzer, Datenbestand im MB-Bereich). Keine Optimierung ohne gemessenen Anlass.
- Fehlerverhalten: Beim Speichern einer Note muss eindeutig erkennbar sein, ob gespeichert wurde. Stilles Verwerfen bei Verbindungsabbruch ist der gravierendste denkbare Fehler dieser Anwendung.
- Keine externen CDNs, keine Telemetrie, keine Analytics. Alle Assets werden mit ausgeliefert. Die Anwendung darf keine ausgehenden Verbindungen aufbauen.
- Abhängigkeiten werden mit gepinnten Versionen geführt; ein Aktualisierungspfad ist zu dokumentieren.

---

## 11. Datenschutzrahmen (zur Kenntnis des Entwicklungsprojekts)

Die Anwendung verarbeitet Klarnamen und Lichtbilder von Schülerinnen und Schülern. Der Betrieb auf privateigenen Geräten unterliegt in Rheinland-Pfalz § 55 Abs. 3 der Schulordnung für die öffentlichen berufsbildenden Schulen: Er setzt die Genehmigung der Schulleitung im Einzelfall voraus, das Einverständnis zur Kontrolle des Geräts unter denselben Bedingungen wie bei Dienstgeräten, sowie die Wahrung der Belange des Datenschutzes.

Für das Entwicklungsprojekt folgt daraus konkret:

- Eine **Löschfunktion** pro Schüler und pro Schuljahr, die Noten, Foto und Historie vollständig entfernt, ist Pflichtbestandteil.
- Der Datenbestand muss **exportierbar** sein (Abschnitt 8), damit kein Lock-in entsteht.
- Es dürfen keine Daten die Anwendung verlassen außer durch den ausdrücklich ausgelösten Export.

Die Klärung der Genehmigung liegt beim Auftraggeber und ist keine Aufgabe des Entwicklungsprojekts.
