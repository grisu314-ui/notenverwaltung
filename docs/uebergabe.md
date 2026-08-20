# Übernahme

Für den, der dieses Projekt weiterführt. Zuerst lesen, dann alles andere.

Gerechnet wird damit, dass die Weiterentwicklung ein **KI-Assistent**
übernimmt, angeleitet vom Betreiber. Die Arbeitsvorgaben dafür stehen in
`CLAUDE.md` im Projektwurzelverzeichnis — sie haben Vorrang vor eigenen
Vorstellungen davon, was eine Anwendung braucht.

## Was das ist

Eine Webanwendung zur Notenverwaltung für **eine einzige Lehrkraft** an einer
berufsbildenden Schule in Rheinland-Pfalz. Sie läuft in zwei Containern auf
einem TrueNAS-SCALE-Server im Haus des Betreibers und ist ausschließlich über
dessen Tailnet erreichbar.

Sie ist **produktiv** und enthält Klarnamen und Lichtbilder realer
Schülerinnen und Schüler. Das ist die wichtigste Eigenschaft dieses Projekts:
Es gibt keinen Testbetrieb mit unwichtigen Daten, und ein Fehler in der
Notenberechnung fällt erst auf, wenn eine falsche Note im Zeugnis steht.

## Wer was tun kann

Diese Trennung ist keine Förmlichkeit, sondern eine Zugangsfrage.

| | Assistent | Betreiber |
|---|---|---|
| Code lesen und ändern | ✓ | |
| Tests laufen lassen | ✓ | |
| Migration schreiben | ✓ | |
| Dokumentation pflegen | ✓ | |
| Image bauen, Stack deployen | | ✓ |
| Migration **ausführen** | | ✓ |
| Sichern, wiederherstellen | | ✓ |
| Tailscale-Knoten, ACLs, Auth-Keys | | ✓ |
| Produktive Daten ansehen | | ✓ |

Ein Assistent hat **keinen Zugriff auf das NAS und keinen auf den produktiven
Datenbestand**. Alles unter „Betreiber" wird als Befehlsfolge vorbereitet und
dann von Hand ausgeführt. Wer Anweisungen dafür schreibt, prüft sie gegen den
Code, statt sie zu erfinden — und sagt dazu, was ungeprüft blieb.

Was der Betreiber dafür braucht: Shell-Zugang auf dem TrueNAS mit `sudo`,
Dockge, das Tailscale-Konto, das GitHub-Repository. Ohne den Tailscale-Zugang
ist die Anwendung nicht erreichbar — es gibt keinen zweiten Weg hinein. Das
ist Absicht.

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

1. `CLAUDE.md` lesen. Es ist die kürzeste Beschreibung dessen, was in diesem
   Projekt gilt, und es hat Vorrang vor Gewohnheiten.
2. Die Tests laufen lassen (`docs/entwicklung.md`). Das ist der schnellste Weg,
   dem Code zu vertrauen: 457 Tests, keine Attrappen für die Datenbank, jeder
   Test baut sein Schema über die echte Migration auf.
3. `docs/notenlogik.md` lesen. Der fachliche Kern und der einzige Teil, den man
   nicht aus dem Code erschließen sollte.
4. `notenverwaltung-spezifikation.md` überfliegen — sie beschreibt den
   umgesetzten Stand, die Abweichungsliste am Ende erklärt den Weg dahin.

## Laufende Pflichten

| Wann | Was | Wer |
|---|---|---|
| täglich, automatisch | Cron zieht um 2 Uhr eine Sicherung, 14 Stände Aufbewahrung | — |
| gelegentlich | prüfen, dass in `sicherungen/` frische Dateien liegen | Betreiber |
| bei jeder neuen Version | **erst sichern, dann migrieren, dann starten** | Betreiber |
| ein- bis zweimal im Jahr | Abhängigkeiten aktualisieren, Tests laufen lassen | Assistent, dann Betreiber |
| nach jeder Änderung an der Eingabemaske | Speicherbestätigung von Hand prüfen (`docs/betrieb.md`) | Betreiber |

## Was nicht getan wird

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
- **Keine fachliche Festlegung selbst treffen.** Alles, was eine Note
  verändern kann — Rundung, Gewichtung, Statusbehandlung —, entscheidet der
  Betreiber. Ein geratener Wert, der niemandem auffällt, ist der teuerste
  Fehler, den dieses Projekt haben kann.

Die vollständige Liste dessen, was bewusst fehlt, steht in
`docs/entwicklung.md` unter „Bewusste Auslassungen".

## Wo es weitergeht

| Datei | Inhalt |
|---|---|
| `CLAUDE.md` | Arbeitsvorgaben — Vorrang vor allem außer der Spezifikation |
| `docs/notenlogik.md` | Die fachlichen Regeln der Notenberechnung |
| `docs/betrieb.md` | Sichern, wiederherstellen, aktualisieren, löschen |
| `docs/entwicklung.md` | Code-Landkarte, Tests, Migrationen, Konventionen |
| `docs/inbetriebnahme-truenas.md` | Neuaufbau von Grund auf |
| `notenverwaltung-spezifikation.md` | Was die Anwendung leisten soll |
