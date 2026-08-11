# Inbetriebnahme auf TrueNAS SCALE

Diese Anleitung beschreibt den vollständigen Weg von der Quelle bis zum
laufenden Stack in Dockge. Sie ergänzt den Abschnitt „Betrieb im Container"
in `README.md` um das, was auf TrueNAS anders ist.

Vorausgesetzt: TrueNAS SCALE mit Docker (ab 24.10 „Electric Eel"), Dockge als
App, Shell-Zugang.

**Alle Befehle dieser Anleitung laufen als `root`.** Am einfachsten einmal zu
Beginn umschalten und in derselben Sitzung bleiben:

```bash
sudo -i
docker version
docker compose version
```

Der Grund ist nicht Bequemlichkeit: `docker` braucht ohnehin root, und `git`
verweigert die Arbeit, sobald Arbeitsbaum und aufrufender Benutzer nicht
zusammenpassen (siehe „Störungssuche", *dubious ownership*). Ein Verzeichnis,
in dem mal `admin` und mal `root` gearbeitet hat, ist die Ursache dieses
Fehlers. Wer lieber als `admin` angemeldet bleibt, stellt **jedem** Befehl
`sudo` voran — auch den `git`-Befehlen, nicht nur den `docker`-Befehlen.

---

## Warum hier gebaut wird und nicht auf dem Pi

TrueNAS SCALE gibt es nur für x86-64, der Raspberry Pi ist `aarch64`. Ein auf
dem Pi gebautes Image startet auf TrueNAS **nicht** — Fehlerbild
`exec format error`. Es gibt keinen Grund, den Umweg über eine Registry oder
einen Multi-Arch-Build unter Emulation zu gehen: Der Docker-Daemon auf dem NAS
baut das Image in ein paar Minuten selbst.

Der Pi bleibt als Teststand nützlich. Dort wird dasselbe Repository
unabhängig für `arm64` gebaut; im Dockerfile ist nichts architekturabhängig.
Bedingung ist ein **64-bit-Betriebssystem** auf dem Pi (`uname -m` muss
`aarch64` melden) — auf `armv7l` fehlt für `pydantic-core` ein fertiges Wheel.

**Gebaut wird in der Shell, nicht in Dockge.** Dockge führt `docker compose`
in seinem eigenen Container aus; ein Build-Kontext müsste dort unter
identischem Pfad sichtbar sein. Diese Zusatzbedingung muss nach jedem
Dockge-Update wieder stimmen. Außerdem beherrscht Dockge kein
`docker compose run`, das für das erstmalige Anlegen der Datenbank und für
Migrationen gebraucht wird — die Shell brauchen Sie also ohnehin. Dockge
startet und stoppt den Stack, mehr nicht.

---

## Schritt 1 — Datasets und Rechte

Drei Verzeichnisse. Der Stack verwendet **keine benannten Docker-Volumes**,
sondern ausschließlich absolute Pfade auf dem NAS — damit liegt jeder Zustand
an einer Stelle, die man sehen, sichern und in einen Snapshot nehmen kann.

```bash
mkdir -p /mnt/Daten-Z1/apps/notenverwaltung/daten
mkdir -p /mnt/Daten-Z1/apps/notenverwaltung/sicherungen
mkdir -p /mnt/Daten-Z1/apps/notenverwaltung/tailscale

chown -R 1000:1000 /mnt/Daten-Z1/apps/notenverwaltung/daten \
                   /mnt/Daten-Z1/apps/notenverwaltung/sicherungen
chown -R root:root /mnt/Daten-Z1/apps/notenverwaltung/tailscale
chmod 700          /mnt/Daten-Z1/apps/notenverwaltung/tailscale
```

| Verzeichnis | Inhalt | Eigentümer |
|---|---|---|
| `daten/` | die SQLite-Datei | **1000:1000** |
| `sicherungen/` | die Sicherungskopien | **1000:1000** |
| `tailscale/` | Knotenzustand des Sidecars | **root:root**, Modus 700 |

Die **Anwendung** läuft als UID/GID 1000, nicht als root. Gehört `daten/`
einem anderen Benutzer, startet der Container zwar, kann aber nicht schreiben;
das Fehlerbild ist `unable to open database file`.

Der **Tailscale-Sidecar** läuft dagegen als root — er braucht `NET_ADMIN`.
Sein Verzeichnis deshalb nicht auf 1000 setzen. In ihm liegt der
Knotenschlüssel: Bleibt es erhalten, wird der Auth-Key nur beim allerersten
Start gebraucht. `chmod 700`, weil das ein Anmeldegeheimnis ist.

> Die SQLite-Datei gehört auf ein **lokales** Dataset, nie auf eine SMB- oder
> NFS-Freigabe (Spezifikation 2, Punkt 2). Netzwerkdateisysteme setzen die
> Sperren nicht zuverlässig um, die SQLite für WAL braucht.

---

## Schritt 2 — Quelle auf das NAS

Der Quellbaum kommt in das Dataset `/mnt/Daten-Z1/apps/notenverwaltung`, also
**eine Ebene über** `daten/` und `sicherungen/`.

`git clone` verweigert das: Das Zielverzeichnis ist nicht leer, weil die
beiden Unterverzeichnisse aus Schritt 1 bereits darin liegen. Der Weg für ein
vorhandenes Verzeichnis ist deshalb:

```bash
cd /mnt/Daten-Z1/apps/notenverwaltung
git init
git remote add origin https://github.com/grisu314-ui/notenverwaltung.git
git fetch origin
git checkout -b main origin/main
```

Später aktualisieren mit `git pull` wie gewohnt.

> **Vorsicht mit `git clean -xfd` in diesem Verzeichnis.** Der Schalter `-x`
> löscht auch die ignorierten Dateien — und ignoriert sind hier ausgerechnet
> `daten/` und `sicherungen/`. Ein `git clean -xfd` in diesem Arbeitsbaum
> löscht damit die produktive Datenbank **und sämtliche Sicherungen** in einem
> Zug. `git clean -fd` ohne `-x` ist ungefährlich, `git reset --hard` ebenso;
> beide fassen ignorierte Dateien nicht an.
>
> Wer diesen Schalter nie tippt, hat kein Problem. Wer sichergehen will, legt
> den Quellbaum stattdessen in ein Unterverzeichnis `quelle/` — dann liegen
> Daten und Arbeitsbaum getrennt und dieser Absatz entfällt.

`daten/` und `sicherungen/` stehen in `.gitignore` und in `.dockerignore`.
Damit taucht der produktive Bestand weder in `git status` auf noch im
Build-Kontext, den `docker build` an den Daemon schickt. Einmal nachsehen —
jetzt, solange dort noch keine echten Daten liegen:

```bash
git status --short      # daten/ und sicherungen/ dürfen NICHT auftauchen
git clean -nd           # muss leer bleiben
```

Zeigt die erste Zeile `?? daten/`, greift die Ignorierung nicht und Sie
arbeiten mit einem Stand vor dieser Änderung. Dann erst `git pull`.

Wollen Sie keinen Quellcode auf dem NAS, siehe „Variante ohne Bauen auf dem
NAS" am Ende.

---

## Schritt 3 — Image bauen

```bash
cd /mnt/Daten-Z1/apps/notenverwaltung
git pull
docker build -t notenverwaltung:$(date +%Y-%m-%d) .
docker images notenverwaltung
```

**Datum als Tag, nie `latest`.** Der Tag ist gleichzeitig die Rollback-Marke:
Ein Zurück auf die vorige Version ist eine Zeile in der Compose-Datei und ein
Neustart des Stacks — solange das alte Image noch da ist. Mit `latest`
überschreibt sich der Stand selbst und genau das geht nicht mehr.

Bauen Sie mehrmals am selben Tag, hängen Sie eine laufende Nummer an:
`notenverwaltung:2026-08-11b`.

Im Image ist ausschließlich Code. `.dockerignore` schließt `.env`, `daten/`,
`sicherungen/` und `*.db` aus, und das Dockerfile kopiert ohnehin nur `app`,
`migrations`, `scripts`, `alembic.ini` und das Startskript. Es enthält keine
Daten und kein Geheimnis.

Der Build-Kontext ist hier das ganze Dataset. Ohne die beiden Einträge in
`.dockerignore` würde `docker build` die produktive Datenbank und sämtliche
Sicherungen einlesen und an den Daemon schicken — langsam und unnötig.

---

## Schritt 4 — Stack in Dockge anlegen

Dockge baut nicht — es startet und stoppt nur, was in Schritt 3 gebaut wurde.
Die passende Compose-Datei liegt im Repository:
**`docker-compose.truenas.yml`**. Sie unterscheidet sich von
`docker-compose.yml` in zwei Punkten: fertiges Image statt `build:`, und alle
Volumes als absolute Pfade auf dem NAS statt eines benannten Docker-Volumes.

In Dockge einen neuen Stack `notenverwaltung` anlegen und den Inhalt in den
Editor kopieren:

```bash
cat /mnt/Daten-Z1/apps/notenverwaltung/docker-compose.truenas.yml
```

Die Datei steht bewusst **nur einmal** im Projekt, statt hier noch einmal
abgedruckt zu werden — zwei Kopien laufen auseinander, und eine veraltete
Compose-Datei bindet im Zweifel das falsche Verzeichnis ein.

**Zwei Werte sind einzutragen:**

1. `tailscale/tailscale:VERSION` — der Platzhalter steht absichtlich so da:
   Der Stack startet nicht, bis eine Version eingetragen ist. `latest` wäre
   die schlechtere Wahl, der Sidecar tauscht sich sonst irgendwann unbemerkt
   aus. Sinnvoll ist die Version, die Ihr bestehender Tailscale-Container auf
   dem NAS bereits verwendet:

   ```bash
   docker ps --filter ancestor=tailscale/tailscale --format '{{.Image}}'
   ```

2. `notenverwaltung:JJJJ-MM-TT` — der Tag aus Schritt 3. Genau so, wie
   `docker images notenverwaltung` ihn anzeigt.

### Die Volumes

Alle drei sind **absolute Pfade auf dem NAS**, kein benanntes Volume, kein
`volumes:`-Block am Dateiende:

```yaml
      - /mnt/Daten-Z1/apps/notenverwaltung/tailscale:/var/lib/tailscale
      - /mnt/Daten-Z1/apps/notenverwaltung/daten:/daten
      - /mnt/Daten-Z1/apps/notenverwaltung/sicherungen:/sicherungen
```

Links der Pfad auf dem NAS, rechts der Pfad im Container — die rechte Seite
ist fest und darf nicht geändert werden: `/daten` steht so im Image
(`NOTENVERWALTUNG_DB=/daten/notenverwaltung.db`), `/var/lib/tailscale` steht
in `TS_STATE_DIR`.

Ein benanntes Volume für den Tailscale-Zustand täte es technisch auch, läge
dann aber unter `/var/lib/docker/volumes/…` — unsichtbar, außerhalb Ihrer
Snapshots und beim Aufräumen leicht mit weggeworfen. Ein absoluter Pfad ist
hier die bessere Wahl, und Dockge kommt damit ohnehin am besten zurecht.

`pull_policy: never` bleibt stehen. Ohne diese Zeile würde Compose bei einem
vertippten Tag versuchen, ein fremdes Image gleichen Namens aus dem Netz zu
holen; mit ihr scheitert der Start stattdessen sichtbar. Meldet Ihre
Compose-Version die Zeile als unbekannt, kann sie ersatzlos entfallen — ein
lokal vorhandenes Image wird auch ohne sie nicht neu geholt.

### Die `.env` daneben

Im selben Stack-Verzeichnis eine Datei `.env`:

```
TS_AUTHKEY=tskey-auth-...
```

Bietet Dockges Editor keine `.env` an, legen Sie sie per Shell an — das
Stack-Verzeichnis liegt dort, wo Dockge konfiguriert ist, üblicherweise
`/opt/stacks/notenverwaltung/`.

Der Schlüssel gehört dem Tailscale-Sidecar, nicht der Anwendung. **Die
Anwendung hat kein einziges Geheimnis** und liest genau eine
Umgebungsvariable, den Datenbankpfad, und der steht fest im Image.

Empfehlenswert ist ein **einmalig verwendbarer** Auth-Key aus der
Tailscale-Konsole. Nach der ersten Anmeldung liegt der Knotenzustand in
`/mnt/Daten-Z1/apps/notenverwaltung/tailscale`; der Schlüssel wird dann nicht
mehr gebraucht und darf ablaufen. Ein dauerhaft gültiger Key, der als Datei
auf dem NAS liegt, ist ein dauerhaft gültiges Anmeldegeheimnis.

Solange die `compose.yaml` `${TS_AUTHKEY:?…}` enthält, muss die Variable
allerdings bei **jedem** Start gesetzt sein, auch wenn Tailscale sie längst
nicht mehr braucht. Die `.env` bleibt also liegen. Wer das nicht will, ändert
den Eintrag nach der ersten erfolgreichen Anmeldung auf `${TS_AUTHKEY:-}` —
dann startet der Stack auch ohne Schlüssel, und ein verlorener Knotenzustand
fällt erst beim Neuanmelden auf.

---

## Schritt 5 — Datenbank einmalig anlegen

**Der Container startet ohne vorhandene Datenbank absichtlich nicht.** Vor dem
ersten Start deshalb einmal:

```bash
docker run --rm \
    -v /mnt/Daten-Z1/apps/notenverwaltung/daten:/daten \
    --entrypoint alembic \
    notenverwaltung:2026-08-11 upgrade head
```

Das läuft ohne Compose und ohne den Tailscale-Sidecar. Danach steht
`/mnt/Daten-Z1/apps/notenverwaltung/daten/notenverwaltung.db` bereit.

Prüfen, dass die Datei UID 1000 gehört:

```bash
ls -l /mnt/Daten-Z1/apps/notenverwaltung/daten/
```

---

## Schritt 6 — Starten und erreichen

Stack in Dockge starten. Danach:

1. In der Tailscale-Konsole erscheint ein neuer Knoten `notenverwaltung`.
   Freigeben, falls Ihr Tailnet Geräte manuell genehmigt.
2. In den Tailscale-ACLs festlegen, welche Geräte diesen Knoten erreichen
   dürfen. Das ist der eigentliche Grund für den eigenen Sidecar-Knoten
   statt der Mitbenutzung des vorhandenen Tailscale-Containers.
3. Aufrufen: `http://notenverwaltung:8000/` von einem Gerät im Tailnet.

Wenn nichts kommt, zuerst das Protokoll ansehen:

```bash
docker logs notenverwaltung
docker logs notenverwaltung-tailscale
```

---

## Schritt 7 — Sicherung einrichten

Nächtlich um 2 Uhr, als Cron-Eintrag auf dem TrueNAS-Host (Systemeinstellungen
→ Erweitert → Cron-Jobs, oder `crontab -e` als root):

```
0 2 * * * docker exec notenverwaltung python scripts/backup.py /sicherungen --aufbewahren 14
```

`docker exec` mit festem Containernamen statt `docker compose exec`: Der
Cron-Lauf braucht so kein Arbeitsverzeichnis und keinen Pfad zur
Compose-Datei. Das Skript gibt bei Fehlschlag einen Rückgabewert ≠ 0 zurück,
damit Cron es meldet.

Gesichert wird über `VACUUM INTO`, nie über eine Dateikopie, und die Kopie
wird nach dem Schreiben geöffnet und geprüft. Details in `README.md`.

### Wiederherstellung einmal von Hand durchspielen

Abschnitt 2.5 der Spezifikation verlangt das, und zwar **bevor** echte Daten
im System sind:

```bash
# Stack in Dockge stoppen, dann:
cp /mnt/Daten-Z1/apps/notenverwaltung/sicherungen/notenverwaltung-JJJJ-MM-TT-HHMMSS.db \
   /mnt/Daten-Z1/apps/notenverwaltung/daten/notenverwaltung.db
chown 1000:1000 /mnt/Daten-Z1/apps/notenverwaltung/daten/notenverwaltung.db
# Stack wieder starten
```

Das `cp` ist hier richtig: Die Sicherung ist eine ruhende Datei und die
Anwendung ist gestoppt. Verboten ist `cp` nur auf die **laufende** Datenbank.

Achten Sie darauf, dass neben der wiederhergestellten Datei keine alten
`.db-wal`- und `.db-shm`-Dateien liegenbleiben — die gehören zum vorigen
Stand. Vor dem `cp` entfernen.

---

## Aktualisieren auf eine neue Version

Die Reihenfolge ist nicht beliebig: **erst sichern, dann migrieren, dann
starten.**

```bash
# 1. Neue Quelle holen und bauen
cd /mnt/Daten-Z1/apps/notenverwaltung
git pull
docker build -t notenverwaltung:2026-09-01 .

# 2. Stack in Dockge stoppen

# 3. Sicherung ziehen -- mit dem ALTEN Image, gegen die unveränderte Datei
docker run --rm \
    -v /mnt/Daten-Z1/apps/notenverwaltung/daten:/daten \
    -v /mnt/Daten-Z1/apps/notenverwaltung/sicherungen:/sicherungen \
    --entrypoint python \
    notenverwaltung:2026-08-11 scripts/backup.py /sicherungen

# 4. Migration mit dem NEUEN Image
docker run --rm \
    -v /mnt/Daten-Z1/apps/notenverwaltung/daten:/daten \
    --entrypoint alembic \
    notenverwaltung:2026-09-01 upgrade head

# 5. Tag in der compose.yaml auf 2026-09-01 ändern, Stack starten
```

**Der Container migriert nie von selbst.** Ändert eine neue Version das
Schema, prüft er das beim Start, startet **nicht** und schreibt den Grund ins
Protokoll (`docker logs notenverwaltung`). Das ist beabsichtigt: Eine
automatische Migration würde den produktiven Bestand mit Klarnamen und
Lichtbildern umbauen, ohne dass jemand sie auf einer Kopie durchgespielt hat.

Bei einer Migration, die mehr als eine Spalte hinzufügt, gehört ein Probelauf
dazu: die frische Sicherung an einen anderen Ort kopieren,
`NOTENVERWALTUNG_DB` darauf zeigen lassen, migrieren, ansehen — erst dann
Schritt 4.

### Zurück auf die vorige Version

Solange die Migration **keine** Schemaänderung enthielt: Tag in der
`compose.yaml` zurückstellen, Stack neu starten. Fertig.

Enthielt sie eine Schemaänderung, genügt das nicht — das alte Programm kann
mit dem neuen Schema nichts anfangen und verweigert den Start. Dann die
Sicherung aus Schritt 3 zurückspielen (siehe „Wiederherstellung") und danach
den Tag zurückstellen.

Alte Images aufräumen, aber nicht zu früh:

```bash
docker images notenverwaltung
docker rmi notenverwaltung:2026-06-01
```

---

## Störungssuche

| Fehlerbild | Ursache | Abhilfe |
|---|---|---|
| `exec format error` | Image für die falsche Architektur, z. B. vom Pi | Auf dem NAS neu bauen |
| `destination path … already exists and is not an empty directory` | `git clone` in das Dataset, in dem `daten/` und `sicherungen/` liegen | `git init` + `git fetch` statt `clone`, siehe Schritt 2 |
| `fatal: detected dubious ownership in repository` | Der Arbeitsbaum gehört einem anderen Benutzer als dem, der `git` aufruft | Als `root` weiterarbeiten (`sudo -i`) oder jedem `git` ein `sudo` voranstellen — siehe unten |
| `unable to open database file` | Verzeichnis gehört nicht UID 1000, oder es fehlt | `chown -R 1000:1000 …` |
| Container startet nicht, Protokoll nennt eine ausstehende Migration | Neues Image, altes Schema | Migration ausführen (siehe „Aktualisieren") |
| `TS_AUTHKEY fehlt` | `.env` fehlt oder liegt nicht neben der `compose.yaml` | `.env` im Stack-Verzeichnis anlegen |
| Compose will `notenverwaltung` aus dem Netz ziehen | Tag vertippt, Image nicht vorhanden | `docker images notenverwaltung`, Tag berichtigen |
| Knoten erscheint nicht im Tailnet | Auth-Key abgelaufen oder verbraucht | Neuen Key erzeugen, `.env` ändern, Stack neu starten |
| Knoten meldet sich bei **jedem** Neustart neu an | `tailscale/` wird nicht eingehängt oder gehört UID 1000 statt root | Pfad in der Compose-Datei prüfen, `chown -R root:root tailscale` |
| Stack startet in Dockge nicht, ohne brauchbare Meldung | verschiedene | In der Shell nachstellen, siehe unten |
| Seite lädt, zeigt aber keine Uhrzeiten | — | Tritt nicht auf; `tzdata` ist im Image fest enthalten |

### Der Stack startet in Dockge nicht

Dockges Oberfläche zeigt nicht immer die eigentliche Fehlermeldung. Der erste
Schritt ist deshalb immer, denselben Stack in der Shell zu starten — dort
steht im Klartext, woran es liegt:

```bash
cd /opt/stacks/notenverwaltung      # Pfad, den Dockge für Stacks verwendet
docker compose config               # prüft die Datei, ohne etwas zu starten
docker compose up -d
docker compose logs --tail 50
```

`docker compose config` ist die schnellste Prüfung: Es löst `${TS_AUTHKEY}`
auf, meldet unbekannte Schlüssel und druckt die Datei so, wie Compose sie
tatsächlich versteht. Läuft der Stack von der Shell aus, aber nicht aus
Dockge heraus, liegt es an Dockge und nicht an dieser Compose-Datei.

Die vier häufigsten Ursachen, in dieser Reihenfolge:

1. **Ein Platzhalter steht noch drin** — `VERSION` oder `JJJJ-MM-TT`. Der
   Stack startet dann absichtlich nicht.
2. **`TS_AUTHKEY` kommt nicht an.** Symptom: `required variable TS_AUTHKEY is
   missing`. Die `.env` muss im selben Verzeichnis liegen wie die
   `compose.yaml` des Stacks, nicht im Projektverzeichnis. Prüfen mit
   `docker compose config | grep TS_AUTHKEY`.
3. **Das Image gibt es lokal nicht** unter genau diesem Tag. Prüfen mit
   `docker images notenverwaltung`; der Tag muss zeichengenau stimmen.
4. **`pull_policy` wird nicht verstanden** — nur bei alten Compose-Versionen.
   Zeile entfernen, siehe Schritt 4.

Verzeichnisse, die es noch nicht gibt, sind **keine** Ursache: Docker legt
einen fehlenden Bind-Mount-Pfad selbst an — allerdings als root, und dann
kann die Anwendung nicht hineinschreiben. Deshalb Schritt 1 vor dem ersten
Start, nicht danach.

### `detected dubious ownership in repository`

Git arbeitet nicht in einem Arbeitsbaum, der einem anderen Benutzer gehört als
dem, der es aufruft. Der typische Auslöser hier: Schritt 1 (`mkdir`, `chown`)
lief als `root`, danach wurde als `admin` weitergearbeitet.

Nachgemessen mit git 2.43, damit die Empfehlung nicht auf Vermutung beruht:

| Arbeitsbaum gehört | git läuft als | Ergebnis |
|---|---|---|
| `root` | `root` | geht |
| `root` | `admin` | **Fehler** |
| `admin` | `admin` | geht |
| `admin` | `root` (Anmeldung als root) | **Fehler** |
| `root` oder `admin` | `sudo git …`, aufgerufen von `admin` | geht |

Die letzte Zeile ist der Ausweg: `sudo` setzt `SUDO_UID`, und git akzeptiert
dann sowohl den aufrufenden Benutzer als auch `root` als Eigentümer.

**Empfehlung:** einmal `sudo -i` und den ganzen Ablauf als `root` machen.

**Was Sie nicht tun sollten:**

- `git config --global --add safe.directory …` — der Vorschlag aus Gits
  Fehlermeldung. Er schaltet die Prüfung ab, statt die Ursache zu beheben,
  und er gilt **pro Benutzer**: Als `admin` eingetragen, hilft er beim
  nächsten `sudo git pull` nicht, weil `root` seine eigene Konfiguration
  liest. Nachgemessen.
- `chown -R admin /mnt/Daten-Z1/apps/notenverwaltung` — **das zerstört die
  Rechte auf `daten/` und `sicherungen/`.** Beide müssen UID 1000 gehören,
  sonst startet der Container zwar, kann aber nicht schreiben. Wenn schon
  umschreiben, dann ohne `-R` auf dem Elternverzeichnis und mit `-R` nur auf
  `.git` — und danach `chown -R 1000:1000` auf die beiden Datenverzeichnisse
  zur Kontrolle wiederholen.

Ist es schon passiert, richtet das den Stand wieder her:

```bash
sudo -i
cd /mnt/Daten-Z1/apps/notenverwaltung
chown -R root:root .git
chown root:root .
chown -R 1000:1000 daten sicherungen
ls -ld . .git daten sicherungen
git status --short
```

---

## Variante ohne Bauen auf dem NAS

Wenn kein Quellcode auf das NAS soll, bauen Sie auf einem **x86-64**-Rechner
(Notebook, VM) und übertragen das fertige Image direkt — ohne Registry, ohne
Konto, ohne öffentliches Artefakt:

```bash
docker build -t notenverwaltung:2026-08-11 .
docker save notenverwaltung:2026-08-11 | ssh root@truenas 'docker load'
```

Alles ab Schritt 4 bleibt unverändert.

Eine Registry (Docker Hub) brauchen Sie für diesen Aufbau nicht. Falls Sie
später doch eine wollen: privates Repository, und der Build muss auf x86-64
laufen — nicht auf dem Pi.

---

## Was hier bewusst nicht passiert

- **Kein automatisches Update, kein Watchtower.** Ein Image, das sich nachts
  selbst austauscht, kann bei einer Schemaänderung nur zwei Dinge tun:
  falsch migrieren oder nicht mehr starten.
- **Keine automatische Migration beim Start.** Siehe oben.
- **Kein veröffentlichter Port, kein Reverse Proxy, kein TLS.** Der Zugang
  läuft ausschließlich über das Tailnet; die Begründung dieser bewussten
  Abweichung von Abschnitt 2, Punkt 7 steht in `README.md`.
- **Keine Authentifizierung in der Anwendung.** Wer den Knoten erreicht, darf
  alles. Die Zugangsbeschränkung liegt in den Tailscale-ACLs. Das ist
  beabsichtigt und keine Lücke — aber es heißt, dass die ACLs die einzige
  Grenze sind. Behandeln Sie sie entsprechend.
