# Inbetriebnahme auf TrueNAS SCALE

Der vollständige Weg von der Quelle bis zum laufenden Stack in Dockge.
Erprobt — die Anleitung ist einmal von Anfang bis Ende durchgelaufen.

Für den **laufenden** Betrieb — Sicherung, Wiederherstellung, Update — siehe
[`betrieb.md`](betrieb.md).

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

### Wo läuft welcher Schritt?

**Dockge hat keine Kommandozeile.** Alles, was in dieser Anleitung als
`bash`-Block steht, gehört in die TrueNAS-Shell. In Dockge passiert nur
zweierlei: die Compose-Datei eintragen und auf *Deployen* bzw. *Stoppen*
drücken.

| Schritt | Wo |
|---|---|
| 1 Verzeichnisse und Rechte | TrueNAS-Shell |
| 2 Quelle holen | TrueNAS-Shell |
| 3 Image bauen | TrueNAS-Shell |
| 4 Datenbank anlegen | TrueNAS-Shell |
| 5 Stack eintragen | **Dockge** |
| 6 Deployen | **Dockge** |
| 7 Sicherung einrichten | TrueNAS-Shell (Cron) |
| Migration beim Update | TrueNAS-Shell |

**Die Reihenfolge ist nicht beliebig.** Wird vor Schritt 4 deployt, findet der
Container keine Datenbank und beendet sich sofort wieder.

---

## Gebaut wird auf dem NAS, in der Shell

**Nicht in Dockge**: Dockge führt `docker compose` in seinem eigenen Container
aus, ein Build-Kontext müsste dort unter identischem Pfad sichtbar sein. Es
beherrscht außerdem kein `docker compose run`, das zum Anlegen der Datenbank
und für Migrationen gebraucht wird. Dockge startet und stoppt den Stack, mehr
nicht.

**Nicht auf einem anderen Rechner**, jedenfalls nicht auf einem mit anderer
Architektur: TrueNAS SCALE gibt es nur für x86-64. Ein anderswo gebautes Image
— etwa auf einem Raspberry Pi (`aarch64`) — scheitert hier mit
`exec format error`.

---

## Schritt 1 — Datasets und Rechte

Vier Verzeichnisse. Der Stack verwendet **keine benannten Docker-Volumes**,
sondern ausschließlich absolute Pfade auf dem NAS — damit liegt jeder Zustand
an einer Stelle, die man sehen, sichern und in einen Snapshot nehmen kann.

```bash
mkdir -p /mnt/Daten-Z1/apps/notenverwaltung/daten
mkdir -p /mnt/Daten-Z1/apps/notenverwaltung/sicherungen
mkdir -p /mnt/Daten-Z1/apps/notenverwaltung/tailscale
mkdir -p /mnt/Daten-Z1/apps/notenverwaltung/pforte

chown -R 1000:1000 /mnt/Daten-Z1/apps/notenverwaltung/daten \
                   /mnt/Daten-Z1/apps/notenverwaltung/sicherungen
chown -R root:root /mnt/Daten-Z1/apps/notenverwaltung/tailscale \
                   /mnt/Daten-Z1/apps/notenverwaltung/pforte
chmod 700          /mnt/Daten-Z1/apps/notenverwaltung/tailscale \
                   /mnt/Daten-Z1/apps/notenverwaltung/pforte
```

| Verzeichnis | Inhalt | Eigentümer |
|---|---|---|
| `daten/` | die SQLite-Datei | **1000:1000** |
| `sicherungen/` | die Sicherungskopien | **1000:1000** |
| `tailscale/` | Knotenzustand des Sidecars | **root:root**, Modus 700 |
| `pforte/` | Zustand der Caddy-Pforte | **root:root**, Modus 700 |

Die **Anwendung** läuft als UID/GID 1000, nicht als root. Gehört `daten/`
einem anderen Benutzer, startet der Container zwar, kann aber nicht schreiben;
das Fehlerbild ist `unable to open database file`.

Der **Tailscale-Sidecar** läuft dagegen als root — er braucht `NET_ADMIN`.
Sein Verzeichnis deshalb nicht auf 1000 setzen. In ihm liegt der
Knotenschlüssel: Bleibt es erhalten, wird der Auth-Key nur beim allerersten
Start gebraucht. `chmod 700`, weil das ein Anmeldegeheimnis ist.

Die **Pforte** (Caddy) läuft ebenfalls als root. In `pforte/` legt sie ihren
Zustand ab, darunter eine Kopie ihrer Konfiguration **mit dem Passwort-Hash**
— deshalb auch hier `chmod 700`. Das Caddyfile selbst liegt nicht dort,
sondern im Quellbaum (`caddy/Caddyfile`) und kommt mit Schritt 2.

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

`daten/`, `sicherungen/`, `tailscale/` und `pforte/` stehen in `.gitignore`
und in `.dockerignore`.
Damit taucht der produktive Bestand weder in `git status` auf noch im
Build-Kontext, den `docker build` an den Daemon schickt. Einmal nachsehen —
jetzt, solange dort noch keine echten Daten liegen:

```bash
git status --short      # daten/, sicherungen/, tailscale/, pforte/ dürfen NICHT auftauchen
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
`sicherungen/`, `tailscale/`, `pforte/` und `*.db` aus, und das Dockerfile kopiert ohnehin nur `app`,
`migrations`, `scripts`, `alembic.ini` und das Startskript. Es enthält keine
Daten und kein Geheimnis.

Der Build-Kontext ist hier das ganze Dataset. Ohne die beiden Einträge in
`.dockerignore` würde `docker build` die produktive Datenbank und sämtliche
Sicherungen einlesen und an den Daemon schicken — langsam und unnötig.

---

## Schritt 4 — Datenbank einmalig anlegen (TrueNAS-Shell)

**Vor** dem ersten Deploy in Dockge, nicht danach: Der Container startet ohne
vorhandene Datenbank absichtlich nicht.

Dieser Befehl läuft in der **TrueNAS-Shell**, nicht in Dockge — Dockge hat
keine Kommandozeile und kann kein `docker run`:

```bash
docker run --rm \
    -v /mnt/Daten-Z1/apps/notenverwaltung/daten:/daten \
    --entrypoint alembic \
    notenverwaltung:2026-08-11 upgrade head
```

Der Tag muss der aus Schritt 3 sein. Der Befehl braucht weder Compose noch den
Tailscale-Sidecar; er hängt nur das Datenverzeichnis ein und legt die Datei an.

Prüfen — die Datei muss existieren und UID 1000 gehören:

```bash
ls -l /mnt/Daten-Z1/apps/notenverwaltung/daten/
```

Erwartet: `notenverwaltung.db`, Eigentümer `1000 1000`. Steht dort `root`,
lief der Befehl gegen ein anderes Verzeichnis oder Schritt 1 wurde
übersprungen — dann `chown 1000:1000` nachziehen.

---

## Schritt 5 — Stack in Dockge anlegen

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

1. `tailscale/tailscale:VERSION` — **beim ersten Mal `latest` eintragen.**
   Das läuft, und Sie kommen ohne Umweg zu einem laufenden Stack.

   Der Grund für den Platzhalter: Dieser Aufbau setzt voraus, dass das Image
   von selbst startet und dabei `TS_AUTHKEY` auswertet — das macht das
   Programm `containerboot`, das erst in neueren Tailscale-Images steckt.
   Ältere Images führen nur ein blankes `/bin/sh` aus, das sofort endet; der
   Stack läuft dann nie an (siehe „Störungssuche"). Eine geratene
   Versionsnummer trifft diesen Fall leicht.

   Die Version Ihres **bestehenden** Tailscale-Containers ist dabei kein
   guter Anhaltspunkt — sie kann Jahre alt sein und trotzdem laufen, weil
   dieser Container anders gestartet wird.

   **Sobald der Stack läuft, die Version festnageln.** Sie am laufenden
   Container ablesen und eintragen:

   ```bash
   docker exec notenverwaltung-tailscale tailscale version | head -1
   ```

   Aus `1.90.2` wird `image: tailscale/tailscale:v1.90.2`, dann neu
   deployen. Damit bleibt der Sidecar auf einem Stand, der nachweislich
   funktioniert hat, statt sich beim nächsten Pull unbemerkt auszutauschen.
   `latest` ist der Weg zum ersten Start, nicht der Dauerzustand.

2. `notenverwaltung:JJJJ-MM-TT` — der Tag aus Schritt 3. Genau so, wie
   `docker images notenverwaltung` ihn anzeigt.

### Die Volumes

Alle sind **absolute Pfade auf dem NAS**, kein benanntes Volume, kein
`volumes:`-Block am Dateiende:

```yaml
      # tailscale
      - /mnt/Daten-Z1/apps/notenverwaltung/tailscale:/var/lib/tailscale
      # pforte
      - /mnt/Daten-Z1/apps/notenverwaltung/caddy:/etc/caddy:ro
      - /mnt/Daten-Z1/apps/notenverwaltung/pforte/daten:/data
      - /mnt/Daten-Z1/apps/notenverwaltung/pforte/config:/config
      # notenverwaltung
      - /mnt/Daten-Z1/apps/notenverwaltung/daten:/daten
      - /mnt/Daten-Z1/apps/notenverwaltung/sicherungen:/sicherungen
```

Links der Pfad auf dem NAS, rechts der Pfad im Container — die rechte Seite
ist fest und darf nicht geändert werden: `/daten` steht so im Image
(`NOTENVERWALTUNG_DB=/daten/notenverwaltung.db`), `/var/lib/tailscale` steht
in `TS_STATE_DIR`, `/etc/caddy`, `/data` und `/config` erwartet das
Caddy-Image.

`caddy/` ist das Verzeichnis **aus dem Quellbaum** — das Caddyfile kommt mit
`git pull` und liegt nicht als zweite Kopie im Dockge-Verzeichnis. Eingehängt
wird der Ordner, nicht die einzelne Datei; das empfiehlt die Doku des
Caddy-Images, weil manche Editoren eine Datei beim Speichern ersetzen statt
sie zu überschreiben.

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

Im selben Stack-Verzeichnis eine Datei `.env`. Vorlage im Quellbaum:
`.env.example`.

```
TS_AUTHKEY=tskey-auth-...
PFORTE_USER=lehrer
PFORTE_HASH='$2a$14$...'
```

Den Hash für `PFORTE_HASH` erzeugen — das Passwort wird abgefragt und landet
nicht in der Shell-Historie:

```bash
docker run --rm -it caddy:2.11.4-alpine caddy hash-password
```

**Der Hash steht in einfachen Anführungszeichen.** Er enthält `$`, und ohne
die Anführungszeichen ersetzt Compose `$2a`, `$14` usw. durch leere
Variablen. Die Pforte startet dann zwar, aber kein Passwort passt. Wie man
es prüft und später ändert: README, „Zugang & Passwort ändern".

Bietet Dockges Editor keine `.env` an, legen Sie sie per Shell an — das
Stack-Verzeichnis liegt dort, wo Dockge konfiguriert ist, üblicherweise
`/opt/stacks/notenverwaltung/`.

Der Schlüssel gehört dem Tailscale-Sidecar, Benutzer und Hash gehören der
Pforte — nichts davon der Anwendung. **Die Anwendung hat kein einziges
Geheimnis** und liest genau eine
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

## Schritt 6 — Deployen und erreichen

Jetzt erst in Dockge auf **Deployen**. Danach:

1. In der Tailscale-Konsole erscheint ein neuer Knoten `notenverwaltung`.
   Freigeben, falls Ihr Tailnet Geräte manuell genehmigt.
2. In den Tailscale-ACLs festlegen, welche Geräte diesen Knoten erreichen
   dürfen. Das ist der eigentliche Grund für den eigenen Sidecar-Knoten
   statt der Mitbenutzung des vorhandenen Tailscale-Containers.
3. Aufrufen: `http://notenverwaltung:8000/` von einem Gerät im Tailnet. Der
   Browser fragt nach Benutzer und Passwort der Pforte.

Wenn nichts kommt, zuerst das Protokoll ansehen:

```bash
docker logs notenverwaltung
docker logs notenverwaltung-pforte
docker logs notenverwaltung-tailscale
```

### Abnahme der Pforte

Einmal nach dem ersten Deploy und nach jeder Änderung an Compose-Datei oder
Caddyfile. Auf dem NAS:

```bash
cd /opt/stacks/notenverwaltung
docker compose config > /dev/null && echo "Datei in Ordnung"
docker exec notenverwaltung-pforte printenv PFORTE_HASH      # vollständig: $2a$14$…
docker logs notenverwaltung-pforte 2>&1 | grep '"level":"error"'   # keine Zeile
docker exec notenverwaltung python -c "import urllib.request as u; u.urlopen('https://example.org', timeout=5)"
docker ps --format '{{.Names}}\t{{.Ports}}'
```

Erwartet: Die Anwendung kommt **nicht** nach draußen (Fehlermeldung, meist
`Temporary failure in name resolution`). Bei `docker ps` steht an keinem der
drei Container ein veröffentlichter Port — ein solcher sähe aus wie
`0.0.0.0:8000->8000/tcp`. Ein nacktes `8000/tcp` an der Anwendung ist kein
veröffentlichter Port, sondern die `EXPOSE`-Angabe aus dem Dockerfile.

`docker compose config` zeigt den Hash mit `$$` statt `$`; das ist nur die
Darstellung. Maßgeblich ist `printenv`. Drei Warnungen im Protokoll der Pforte
sind normal: `admin endpoint disabled` sowie „HTTP/2" und „HTTP/3 skipped
because it requires TLS".

Von einem Gerät im Tailnet:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://notenverwaltung:8000/                       # 401
curl -s -o /dev/null -w '%{http_code}\n' -u lehrer:PASSWORT http://notenverwaltung:8000/    # 200
curl -m 5 http://notenverwaltung:2019/                                                       # keine Antwort
```

**Nicht `curl -I`:** Das schickt eine HEAD-Anfrage, und die beantwortet die
Anwendung mit `405`. Durch die Pforte ist man dann zwar gekommen, aber die
erwartete `200` erscheint nie.

Zum Schluss auf dem Telefon: Passwortabfrage, dann eine Note in einer
Serieneingabe eintragen und einen Platz im Sitzplan setzen. Beides muss
„gespeichert" zeigen — damit ist belegt, dass auch die htmx-Anfragen durch die
Pforte laufen.

---

## Schritt 7 — Sicherung einrichten

Damit ist die Inbetriebnahme fertig. Es fehlt noch der wichtigste
Dauerbetriebspunkt: der Cron-Eintrag für die nächtliche Sicherung und **die
einmal von Hand durchgespielte Wiederherstellung**. Beides steht in
[`betrieb.md`](betrieb.md) — der Wiederherstellungstest gehört gemacht,
solange noch keine echten Daten in der Datenbank stehen.

---

## Störungssuche

| Fehlerbild | Ursache | Abhilfe |
|---|---|---|
| `exec format error` | Image für die falsche Architektur, z. B. vom Pi | Auf dem NAS neu bauen |
| `destination path … already exists and is not an empty directory` | `git clone` in das Dataset, in dem `daten/` und `sicherungen/` liegen | `git init` + `git fetch` statt `clone`, siehe Schritt 2 |
| `fatal: detected dubious ownership in repository` | Der Arbeitsbaum gehört einem anderen Benutzer als dem, der `git` aufruft | Als `root` weiterarbeiten (`sudo -i`) oder jedem `git` ein `sudo` voranstellen — siehe unten |
| `unable to open database file` | Verzeichnis gehört nicht UID 1000, oder es fehlt | `chown -R 1000:1000 …` |
| Container startet nicht, Protokoll nennt eine ausstehende Migration | Neues Image, altes Schema | Migration ausführen, siehe [`betrieb.md`](betrieb.md) |
| `TS_AUTHKEY fehlt` | `.env` fehlt oder liegt nicht neben der `compose.yaml` | `.env` im Stack-Verzeichnis anlegen |
| Compose will `notenverwaltung` aus dem Netz ziehen | Tag vertippt, Image nicht vorhanden | `docker images notenverwaltung`, Tag berichtigen |
| Knoten erscheint nicht im Tailnet | Auth-Key abgelaufen oder verbraucht | Neuen Key erzeugen, `.env` ändern, Stack neu starten |
| Knoten meldet sich bei **jedem** Neustart neu an | `tailscale/` wird nicht eingehängt oder gehört UID 1000 statt root | Pfad in der Compose-Datei prüfen, `chown -R root:root tailscale` |
| `PFORTE_USER fehlt` oder `PFORTE_HASH fehlt` | Eintrag fehlt in der `.env` | Ergänzen, siehe Schritt 5 |
| Browser fragt immer wieder nach dem Passwort, obwohl es stimmt | Hash in der `.env` ohne einfache Anführungszeichen, von Compose zerlegt | `docker exec notenverwaltung-pforte printenv PFORTE_HASH` muss vollständig `$2a$14$…` zeigen. `.env` berichtigen, `docker compose up -d pforte` |
| `502 Bad Gateway` nach der Passworteingabe | Die Pforte läuft, die Anwendung nicht | `docker logs notenverwaltung` — meist eine ausstehende Migration oder die fehlende Datenbank |
| Nach der Passworteingabe lädt die Seite endlos | Das Caddyfile leitet an `notenverwaltung` statt an `anwendung` weiter; die Pforte ruft sich selbst auf | `caddy/Caddyfile` aus dem Repository wiederherstellen, `docker compose restart pforte` |
| Nicht erreichbar, obwohl alle drei Container `Up` zeigen | Der Sidecar wurde allein neu gestartet; die Pforte hängt noch in seinem alten, verwaisten Netz | `docker restart notenverwaltung-pforte` (nachgestellt) |
| Stack startet in Dockge nicht, ohne brauchbare Meldung | verschiedene | In der Shell nachstellen, siehe unten |

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
2. **`TS_AUTHKEY` kommt nicht an** (ebenso `PFORTE_USER`, `PFORTE_HASH`).
   Symptom: `required variable TS_AUTHKEY is missing`. Die `.env` muss im selben Verzeichnis liegen wie die
   `compose.yaml` des Stacks, nicht im Projektverzeichnis. Prüfen mit
   `docker compose config | grep TS_AUTHKEY`.
3. **Das Image gibt es lokal nicht** unter genau diesem Tag. Prüfen mit
   `docker images notenverwaltung`; der Tag muss zeichengenau stimmen.
4. **`pull_policy` wird nicht verstanden** — nur bei alten Compose-Versionen.
   Zeile entfernen, siehe Schritt 5.

Verzeichnisse, die es noch nicht gibt, sind **keine** Ursache: Docker legt
einen fehlenden Bind-Mount-Pfad selbst an — allerdings als root, und dann
kann die Anwendung nicht hineinschreiben. Deshalb Schritt 1 vor dem ersten
Start, nicht danach.

### `cannot join network namespace of container … is restarting`

```
Error response from daemon: cannot join network namespace of container:
Container 5073a0… is restarting, wait until the container is running
 ✓ Container notenverwaltung-tailscale   Started
 ⠿ Container notenverwaltung-pforte      Starting
```

Diese Meldung ist eine **Folge, nicht die Ursache**. Die Pforte hängt per
`network_mode: service:tailscale` im Netz des Sidecars. (Bis Version 1.3 der
Spezifikation hing dort die Anwendung selbst, und die Meldung nannte den
Container `notenverwaltung`.) Läuft der Sidecar
nicht, gibt es kein Netz zum Beitreten. Dass Dockge daneben `Started` anzeigt,
täuscht: Der Container wurde gestartet, beendet sich sofort wieder und wird
von `restart: unless-stopped` erneut gestartet — eine Schleife.

**Reparieren lässt sich nur der Sidecar.** Der entscheidende Befehl ist sein
Protokoll:

```bash
docker logs notenverwaltung-tailscale --tail 50
docker ps -a --filter name=notenverwaltung
```

Was dort typischerweise steht, und was es bedeutet:

| Im Protokoll | Ursache | Abhilfe |
|---|---|---|
| **gar nichts**, `docker ps -a` zeigt `Restarting (0)` und als Kommando `"/bin/sh"` | **Das Tailscale-Image ist zu alt.** Ohne `containerboot` startet nur eine Shell, die sofort endet — Rückgabewert 0, kein Protokoll | Aktuelle Version eintragen, siehe Schritt 5 |
| `invalid key`, `unauthorized`, `key expired` | Auth-Key abgelaufen, schon verbraucht oder falsch kopiert | Neuen Key erzeugen, `.env` ändern, neu deployen |
| `wgengine`, `tun`, `/dev/net/tun` | Das TUN-Gerät fehlt auf dem Host | `ls -l /dev/net/tun` — fehlt es, `modprobe tun` und den Stack neu deployen |
| `permission denied` auf `/var/lib/tailscale` | Zustandsverzeichnis gehört nicht root | `chown -R root:root …/tailscale` |
Der Rückgabewert in `docker ps -a` trennt die Fälle: `Restarting (0)` heißt,
der Container ist **ordentlich beendet** worden — dann lief kein Dienst, das
ist der Fall „Image zu alt". Ein Wert ungleich 0 heißt, tailscaled ist
angelaufen und dann gescheitert; dann steht der Grund im Protokoll.

Solange der Sidecar nicht dauerhaft läuft, ist die zweite Meldung ohne
Aussagekraft. Erst wenn `docker ps` ihn als `Up` zeigt, lohnt der Blick auf
`docker logs notenverwaltung-pforte` und `docker logs notenverwaltung`.

Zum Aufräumen zwischen zwei Versuchen — in der TrueNAS-Shell:

```bash
cd /opt/stacks/notenverwaltung
docker compose down
docker compose up -d
```

### Die Anwendung startet nicht, das Protokoll nennt eine fehlende Datenbank

```bash
docker logs notenverwaltung --tail 20
```

Sagt es `Die Datenbank … gibt es nicht`, wurde **Schritt 4 übersprungen**. Das
ist kein Fehler des Stacks: Der Container legt die Datenbank absichtlich nicht
selbst an. Schritt 4 in der TrueNAS-Shell nachholen und in Dockge neu
deployen.

### `detected dubious ownership in repository`

Git arbeitet nicht in einem Arbeitsbaum, der einem anderen Benutzer gehört als
dem, der es aufruft. Der typische Auslöser hier: Schritt 1 (`mkdir`, `chown`)
lief als `root`, danach wurde als `admin` weitergearbeitet.

**Abhilfe:** einmal `sudo -i` und den ganzen Ablauf als `root` machen. Wer als
`admin` angemeldet bleibt, stellt jedem Befehl `sudo` voran — `sudo` setzt
`SUDO_UID`, und git akzeptiert dann sowohl den aufrufenden Benutzer als auch
`root` als Eigentümer (nachgemessen mit git 2.43).

**Was Sie nicht tun sollten:**

- `git config --global --add safe.directory …` — der Vorschlag aus Gits
  Fehlermeldung. Er schaltet die Prüfung ab, statt die Ursache zu beheben,
  und gilt **pro Benutzer**: Als `admin` eingetragen, hilft er beim nächsten
  `sudo git pull` nicht, weil `root` seine eigene Konfiguration liest.
- `chown -R admin /mnt/Daten-Z1/apps/notenverwaltung` — **das zerstört die
  Rechte auf `daten/` und `sicherungen/`.** Beide müssen UID 1000 gehören,
  sonst startet der Container zwar, kann aber nicht schreiben.

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

