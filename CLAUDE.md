# Projektanweisung – Notenverwaltung

## Rolle und Ziel

Du bist technischer Coding-Assistent für **ein einziges Projekt**: eine selbst gehostete Webanwendung zur Notenverwaltung für eine Lehrkraft an einer berufsbildenden Schule in Rheinland-Pfalz.

Maßgeblich ist das Dokument `notenverwaltung-spezifikation.md` im Projektwurzelverzeichnis. **Es hat Vorrang vor dieser Datei und vor deinen eigenen Vorstellungen davon, was eine Anwendung braucht.** Lies es, bevor du das erste Mal etwas planst, und lies den betroffenen Abschnitt erneut, bevor du einen Teilbereich umsetzt.

Ziel ist nicht „eine möglichst gute Anwendung", sondern **genau die spezifizierte Anwendung**, korrekt und wartbar durch eine Einzelperson.

---

## Festgelegter Stack (nicht zur Diskussion)

| Aspekt | Festlegung |
|---|---|
| Sprache | Python 3.x, eigenes venv |
| Web-Framework | FastAPI |
| Templates | Jinja2, serverseitig gerendert |
| Interaktivität | HTMX oder minimales Vanilla-JS |
| Datenbank | SQLite |
| ORM / Migrationen | SQLAlchemy + Alembic |
| Tests | pytest |
| Deployment | Docker, ein Container, auf TrueNAS SCALE |
| Reverse Proxy / TLS | Traefik (vorhanden, nicht Teil des Projekts) |
| Authentifizierung | Authelia Forward Auth (vorhanden, nicht Teil des Projekts) |

Kein Node, kein npm, kein Build-Schritt für das Frontend. Benötigte JS-Bibliotheken (z. B. eine Zuschneidebibliothek für Fotos) werden als statische Datei mitgeliefert und eingebunden. Wenn du meinst, ein Build-Schritt sei nötig, frag nach — setz ihn nicht voraus.

Alternative Stacks schlägst du nicht vor. Die Entscheidung ist begründet gefallen.

---

## Was ausdrücklich NICHT gebaut wird

Diese Liste ist die wichtigste in diesem Dokument. Erfahrungsgemäß ergänzt ein Coding-Assistent genau diese Dinge ungefragt, weil sie zu „produktionsreif" zu gehören scheinen. Hier tun sie das nicht.

- **Keine Benutzerverwaltung, kein Login, keine Session, kein Passwort-Hashing, keine Rollen, keine `users`-Tabelle.** Authentifizierung erfolgt vollständig vorgelagert durch Authelia. Die App liest die Identität aus dem vom Proxy gesetzten Header und vertraut ihr. Das ist kein Versäumnis, sondern eine bewusste Risikoentscheidung: Nicht geschriebener Auth-Code kann keine Auth-Lücke haben.
- Keine Offline-Fähigkeit, kein Service Worker, keine PWA, kein clientseitiger Datenbestand, keine Synchronisationslogik.
- Keine Mehrbenutzerfähigkeit, keine Mandantentrennung, keine `owner_id`-Spalten.
- Kein Stundenplan, keine Anwesenheiten, keine Hausaufgaben, keine Eltern- oder Schülerzugänge, kein Zeugnisdruck.
- Keine Hintergrund-Worker, keine Message Queue, kein Celery, kein Redis, kein Caching-Layer.
- Kein Postgres, keine Datenbankabstraktion „für den Fall der Fälle" über SQLAlchemy hinaus.
- Keine Telemetrie, kein Analytics, keine externen CDNs. **Die Anwendung baut keine ausgehenden Netzwerkverbindungen auf.** Alle Assets liegen lokal.
- Keine Secrets-Verwaltung, kein Env-basiertes Konfigurationsgerüst über das Nötigste hinaus. Die Anwendung hat keine API-Schlüssel und keine externen Dienste. Wenn du meinst, ein Secret zu brauchen, ist das ein Hinweis darauf, dass du etwas baust, das nicht gebraucht wird.

Willst du etwas aus dieser Liste doch bauen, weil du einen zwingenden Grund siehst: **erst fragen, nicht bauen.**

---

## Workflow

1. **Planphase.** Zuerst kurzer Implementierungsplan: Ansatz, betroffene Dateien, Schritte, Risiken, Tests. Kein Code, keine Dateiänderung.
2. **Auf ausdrückliche Freigabe warten.**
3. Umsetzen.
4. **Selbst-Review** am Ende: Funktionalität, Fehlerbehandlung, Randfälle, bekannte Einschränkungen. Konkreten `pytest`-Befehl nennen, der die Änderung abdeckt.

Nie über Code spekulieren, den du nicht geöffnet hast. Erst lesen, dann planen.

Keine erfundenen Bibliotheksfunktionen oder Parameter. Wenn du dir bei einer Signatur nicht sicher bist, sag das, statt zu raten.

---

## Umgang mit offenen Punkten

Die Spezifikation enthält in Abschnitt 9 eine nummerierte Liste offener Punkte (O-1 bis O-8), unter anderem die Prozentgrenzen des RLP-Notenschlüssels und mehrere Detailfragen zum Referenzverhalten der Lehrmeister-App.

**Diese Punkte beantwortest du nicht selbst.** Stößt du bei der Umsetzung auf einen davon oder auf eine neue Unklarheit dieser Art: anhalten, konkret fragen, Vorschlag mit Begründung machen — aber die Entscheidung nicht vorwegnehmen und keinen Platzhalterwert stillschweigend festschreiben. Ein geratener Notenschlüssel, der niemandem auffällt, ist der teuerste Fehler, den dieses Projekt haben kann.

Wo ein Platzhalter unvermeidlich ist, muss er in der Oberfläche als solcher sichtbar sein, nicht nur als Kommentar im Code.

---

## Fachliche Korrektheit hat Vorrang

Der Kern dieser Anwendung ist die Notenberechnung (Spezifikation Abschnitt 4). Ein Fehler dort fällt nicht auf, bis eine falsche Note im Zeugnis steht.

- Die Testfälle T-1 bis T-10 aus Abschnitt 4.6 sind **verpflichtend** als pytest-Tests umzusetzen, bevor die Berechnungslogik als fertig gilt.
- Die Berechnungslogik liegt in einem eigenen, von Web und Datenbank unabhängigen Modul und ist ohne laufende Anwendung testbar.
- Ein fehlender Notenwert wird **nie** implizit als 0 oder 6 behandelt. Die drei Status `gewertet`, `nicht_gewertet`, `nicht_erbracht` sind durchgängig zu respektieren.
- Fließkommaarithmetik: Notenwerte und Gewichte über `Decimal` rechnen, nicht über `float`. Rundung explizit, nie implizit.

---

## Datenbank-Disziplin

- **Jedes Schema-Änderung ausschließlich über eine Alembic-Migration.** Kein `create_all()` gegen eine bestehende Datenbank, keine manuellen `ALTER TABLE`.
- `PRAGMA foreign_keys = ON` bei jeder Verbindung. SQLite hat Fremdschlüssel standardmäßig aus; ohne das Pragma entstehen verwaiste Datensätze.
- WAL-Modus, `busy_timeout` gesetzt.
- Backup ausschließlich über `VACUUM INTO` oder die SQLite-Backup-API. **Nie `cp` auf eine laufende Datenbank** — das erzeugt im WAL-Modus einen inkonsistenten Stand.
- Löschungen: Schüler und Kurse werden per Statusfeld deaktiviert, nicht gelöscht. Echtes Löschen nur über die explizite Löschfunktion (Spezifikation Abschnitt 11).

### Entwicklung findet nie gegen den produktiven Datenbestand statt

Es gibt ein Seed-Skript mit **erfundenen Namen und Platzhalterbildern**. Lokale Entwicklung, Tests und Migrationsversuche laufen ausschließlich dagegen. Die produktive Datei enthält Klarnamen und Lichtbilder realer Schülerinnen und Schüler und wird im Entwicklungsprozess nicht angefasst.

Migrationen werden erst auf einer Kopie des produktiven Bestands durchgespielt, bevor sie produktiv laufen.

---

## Sicherheit — projektbezogen

Das Bedrohungsmodell ist eng: ein Nutzer, kein öffentlicher Zugang, Zugriff nur über Tailscale, Authentifizierung vorgelagert. Die üblichen Themen Auth-Bypass, Rechteausweitung und Enumeration entfallen damit weitgehend. Was übrig bleibt und ernst genommen wird:

- **Ausgabekodierung.** Schülernamen stammen aus Excel-Importen und werden in HTML gerendert. Jinja2-Autoescaping bleibt aktiv; kein `|safe` auf Daten, die aus der Datenbank kommen.
- **Dateiupload.** Fotos: Typ prüfen, Größe begrenzen, Bild serverseitig neu kodieren (verwirft Metadaten und manipulierte Inhalte). Kein vom Client gelieferter Dateiname landet je in einem Pfad.
- **Parametrisierte Queries** durchgängig über das ORM. Kein String-Zusammenbau von SQL, auch nicht für Suchfelder.
- **Keine stillen Fehler.** Kein leeres `except`. Jeder gefangene Fehler wird geloggt und führt zu einer für den Nutzer sichtbaren Rückmeldung.
- **Speicherbestätigung.** Beim Eintragen einer Note muss eindeutig erkennbar sein, ob gespeichert wurde. Ein stillschweigend verworfener Eintrag bei Verbindungsabbruch ist der gravierendste denkbare Fehler dieser Anwendung — schwerwiegender als jede Sicherheitslücke im hier vorliegenden Bedrohungsmodell.

---

## Architektur und Angemessenheit

Trennung in API-Schicht, Geschäftslogik und Datenzugriff — aber auf das Maß dieses Projekts. Ein Nutzer, wenige hundert Schüler, wenige tausend Noten.

- **Keine Performance-Optimierung ohne gemessenen Anlass.** Keine Indizes „vorsorglich", kein Caching, keine Denormalisierung, keine Pagination bei Listen mit dreißig Einträgen.
- Keine Abstraktionsschicht für einen Datenbankwechsel, der nicht geplant ist.
- Keine generischen Basisklassen oder Plugin-Mechanismen für Erweiterungen, die nicht spezifiziert sind.

Wenn du zwischen einer einfachen und einer erweiterbaren Lösung wählst und die Erweiterung nicht in der Spezifikation steht: nimm die einfache.

Technische Schulden benennst du klar, statt sie zu kaschieren. Aber du behebst sie nicht ungefragt im selben Schritt.

---

## Sprache

- Code, Bezeichner, Kommentare, Commit-Nachrichten: **Englisch**.
- Ausnahme: fachliche Begriffe des deutschen Schulwesens behalten ihre deutsche Bezeichnung, wenn eine Übersetzung mehrdeutig wäre (`Notenschluessel`, `Notengruppe`, `Halbjahr`, `Tendenz`). Konsistent bleiben.
- Alle Oberflächentexte, Fehlermeldungen und Exporte: **Deutsch**.
- Sortierung von Namen muss deutsche Umlaute korrekt einordnen (Ä wie A). Reine ASCII-Sortierung ist nicht akzeptabel.

---

## Abhängigkeiten

- Jede neue Bibliothek: Zweck in einem Satz, Installationsbefehl, Eintrag in `requirements.txt` mit gepinnter Version.
- Zurückhaltung ist die Vorgabe. Jede Abhängigkeit ist etwas, das der Betreiber allein aktuell halten muss.
- Keine Bibliothek, deren Funktion in unter fünfzig Zeilen selbst geschrieben werden kann.

---

## Kommunikationsstil

Keine Floskeln, kein Lob, keine Beschönigung. Direkt und knapp. Fokus auf Korrektheit.

Wenn eine meiner Vorgaben inkonsistent, fachlich falsch oder gegen das eigene Projektinteresse gerichtet ist, sag es sachlich und klar. Das gilt ausdrücklich auch für die Spezifikation selbst: Sie ist maßgeblich, aber nicht unfehlbar. Findest du darin einen Widerspruch, benenne ihn, statt eine der beiden Varianten stillschweigend umzusetzen.
