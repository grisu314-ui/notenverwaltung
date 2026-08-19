# Übernahme

Für jemanden, der dieses Projekt weiterführt. Zuerst lesen, dann alles andere.

## Was das ist

Eine Webanwendung zur Notenverwaltung für **eine einzige Lehrkraft** an einer
berufsbildenden Schule in Rheinland-Pfalz. Sie läuft in zwei Containern auf
einem TrueNAS-SCALE-Server im Haus des Betreibers und ist ausschließlich über
dessen Tailnet erreichbar.

Sie ist **produktiv** und enthält Klarnamen und Lichtbilder realer
Schülerinnen und Schüler. Das ist die wichtigste Eigenschaft dieses Projekts:
Es gibt keinen Testbetrieb mit unwichtigen Daten, und ein Fehler in der
Notenberechnung fällt erst auf, wenn eine falsche Note im Zeugnis steht.

## Was Sie brauchen

| Zugang | Wofür |
|---|---|
| SSH oder Konsole auf dem TrueNAS, mit `sudo` | Bauen, Migrieren, Sichern |
| Dockge auf dem TrueNAS | Stack starten und stoppen |
| Tailscale-Konto des Betreibers | Knoten freigeben, ACLs, Auth-Keys |
| Das GitHub-Repository | Quellcode |

Ohne den Tailscale-Zugang ist die Anwendung nicht erreichbar — es gibt keinen
zweiten Weg hinein. Das ist Absicht.

## Wo die Daten liegen

Alles unter `/mnt/Daten-Z1/apps/notenverwaltung` auf dem NAS:

| Verzeichnis | Inhalt | Eigentümer |
|---|---|---|
| `daten/` | `notenverwaltung.db` — **der gesamte Datenbestand**, Noten und Fotos | 1000:1000 |
| `sicherungen/` | die nächtlichen Kopien | 1000:1000 |
| `tailscale/` | Knotenzustand des Sidecars | root:root |
| (Wurzel) | der Quellbaum, zugleich Git-Arbeitsverzeichnis | root:root |

Eine einzige SQLite-Datei. Kein zweiter Speicherort, keine Dateien im
Dateisystem, keine externen Dienste. Fotos liegen als BLOB in derselben Datei
— dadurch ist jede Sicherung in sich konsistent.

## Die ersten Schritte

1. `docs/entwicklung.md` lesen und die Tests lokal zum Laufen bringen. Das ist
   der schnellste Weg, dem Code zu vertrauen: 376 Tests, keine Attrappen für
   die Datenbank, jeder Test baut sein Schema über die echte Migration auf.
2. `docs/notenlogik.md` lesen. Das ist der fachliche Kern und der einzige
   Teil, den man nicht aus dem Code erschließen sollte.
3. Eine Sicherung ziehen und **die Wiederherstellung einmal durchspielen**
   (`docs/betrieb.md`). Wer das nicht selbst gemacht hat, hat keine Sicherung.
4. `notenverwaltung-spezifikation.md` überfliegen — sie beschreibt den
   umgesetzten Stand, die Abweichungsliste am Ende erklärt die Entwicklung
   dahin.

## Laufende Pflichten

| Wann | Was |
|---|---|
| täglich, automatisch | Cron zieht um 2 Uhr eine Sicherung, 14 Stände Aufbewahrung |
| gelegentlich | prüfen, dass in `sicherungen/` frische Dateien liegen |
| bei jeder neuen Version | Reihenfolge einhalten: **erst sichern, dann migrieren, dann starten** |
| ein- bis zweimal im Jahr | Abhängigkeiten aktualisieren, Tests laufen lassen |
| nach jeder Änderung an der Eingabemaske | Speicherbestätigung von Hand prüfen (`docs/betrieb.md`) |

## Was Sie nicht tun sollten

- **Keine Authentifizierung nachrüsten.** Nicht vergessen, sondern
  entschieden: Nicht geschriebener Auth-Code kann keine Lücke haben. Der
  Zugangsschutz sind die Tailscale-ACLs.
- **Kein `cp` auf die laufende Datenbank.** Im WAL-Modus entsteht dabei ein
  inkonsistenter Stand — im schlimmsten Fall eine Datei ohne die letzten
  Eintragungen. Sichern nur über `scripts/backup.py`.
- **Keine automatische Migration beim Start.** Der Container prüft das Schema
  und startet lieber nicht, als den produktiven Bestand ungefragt umzubauen.
- **Kein `git clean -xfd` im Arbeitsverzeichnis auf dem NAS.** Der Quellbaum
  liegt eine Ebene über `daten/` und `sicherungen/`; `-x` löscht ignorierte
  Dateien, und das sind genau diese beiden.
- **Keine Performance-Optimierung ohne gemessenen Anlass.** Ein Nutzer, ein
  paar hundert Schüler. Indizes, Caches und Pagination lösen hier kein
  Problem, sondern schaffen eins.
- **Nicht gegen den produktiven Bestand entwickeln.** Dafür gibt es ein
  Seed-Skript mit erfundenen Namen.

## Wo es weitergeht

| Datei | Inhalt |
|---|---|
| `docs/notenlogik.md` | Die fachlichen Regeln der Notenberechnung |
| `docs/betrieb.md` | Sichern, wiederherstellen, aktualisieren, löschen |
| `docs/entwicklung.md` | Code-Landkarte, Tests, Migrationen, Konventionen |
| `docs/inbetriebnahme-truenas.md` | Neuaufbau von Grund auf |
| `notenverwaltung-spezifikation.md` | Was die Anwendung leisten soll |
| `CLAUDE.md` | Arbeitsvorgaben — geschrieben für einen KI-Assistenten, aber die kürzeste Beschreibung der Projektdisziplin |
