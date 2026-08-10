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
| Kurs-/Fachübersicht | 5.3 | offen |
| Fotoerfassung | 7 | offen |
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

## Layout des Tabellenexports (Abschnitt 8, O-6)

Noch nicht gebaut, hier festgehalten:

- Kopfbereich mit Klasse und Kurs.
- Pro Zeile ein Schüler.
- Oberhalb der ersten Schülerzeile mehrere Beschriftungszeilen, die Notenart
  und Notengruppe kennzeichnen. Der Text dieser Zellen wird um 90° gedreht.
- Zwischen zwei Notengruppen jeweils eine leere Spalte Abstand, vor den
  Jahresnoten ebenfalls.

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
sichtbar wäre. Das endgültige Löschen mit Inhalt gehört in die Löschfunktion
nach Abschnitt 11 und erhält dort eine Bestätigung mit Angabe der betroffenen
Datensätze.

Ein Schüler, der die Klasse verlässt, wird **nicht** gelöscht, sondern auf
inaktiv gesetzt; seine Noten bleiben erhalten.

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
