# Auftrag: Zugangsschutz per Caddy-Pforte (Infrastruktur, nicht Anwendung)

> **Umgesetzt am 24.09.2026** (Spezifikation 1.4, Abschnitt 2). Maßgeblich sind
> jetzt `docker-compose.truenas.yml`, `docker-compose.yml` und `caddy/Caddyfile`,
> nicht die Auszüge unten. Abweichungen, alle nachgemessen:
>
> - **3.2:** `reverse_proxy anwendung:8000` statt `notenverwaltung:8000`. In der
>   Pforte löst `notenverwaltung` über das geteilte `/etc/hosts` des Sidecars
>   auf den Sidecar selbst auf; die Anfrage hing. `anwendung` ist ein Netz-Alias
>   der Anwendung im Netz `intern`.
> - **3.1:** Auch `docker-compose.truenas.yml` (der produktive Stack) ist
>   angepasst, dort mit absoluten Pfaden: `caddy/` aus dem Quellbaum,
>   Caddy-Zustand unter `pforte/` statt benannter Volumes.
> - **5, Punkt 1:** `docker compose config` zeigt den Hash mit `$$`; geprüft wird
>   mit `docker exec notenverwaltung-pforte printenv PFORTE_HASH`.
> - **5, Punkt 4:** `curl -I` ergibt `405` (die Anwendung beantwortet HEAD
>   nicht); geprüft wird mit GET. Anleitung: `docs/inbetriebnahme-truenas.md`,
>   „Abnahme der Pforte".
> - **6:** Die ersetzte Festlegung stand in Abschnitt 2 der Spezifikation
>   („Zugangsschutz über Tailscale-ACLs"), nicht in Abschnitt 6; Authelia war
>   schon seit Version 1.1 gestrichen.
 
## Hinweis zur Spezifikation – bitte zuerst lesen
 
Die Spezifikation verbietet, in der **Anwendung** ein Login-System o. ä. einzubauen.
Dieser Auftrag verstößt nicht dagegen: Die Passwortabfrage wird **ausschließlich auf
Infrastrukturebene** (vorgeschalteter Reverse-Proxy im Compose-Stack) umgesetzt.
 
- **Am Anwendungscode (Python/FastAPI/Templates) wird nichts geändert.**
- Die Entscheidung ist vom Eigentümer getroffen und ersetzt in der Spezifikation die
  bisherige Festlegung „Authentifizierung wird an Authelia delegiert“ (siehe Abschnitt 6).
## 1. Ziel
 
Drei Schutzebenen, alle ohne Zugriff von außen:
 
1. **Tailscale** – nur Geräte im Tailnet erreichen den Stack. Kein veröffentlichter Port,
   kein Funnel, kein öffentlicher Reverse-Proxy. **Bleibt unverändert.**
2. **Caddy-Pforte (neu)** – HTTP Basic Auth vor der Anwendung.
3. **Netzwerktopologie (neu)** – die Anwendung hängt **nicht mehr** im Netz des
   Tailscale-Sidecars, sondern nur in einem internen Docker-Netz. Aus dem Tailnet ist sie
   ausschließlich über die Pforte erreichbar. Ausgehende Verbindungen der Anwendung sind
   technisch unterbunden (`internal: true`) – passend zu „keine externen Verbindungen“.
Die Adresse für den Nutzer bleibt `http://notenverwaltung:8000`.
 
## 2. Zielbild
 
```
Tailnet ──► [tailscale-Sidecar-Netz]  Caddy :8000  (basic_auth)
                                          │
                                          ▼  Netz „intern“ (internal: true)
                                  notenverwaltung :8000
```
 
## 3. Änderungen im Detail
 
### 3.1 `docker-compose.yml`
 
- Service `tailscale`: unverändert, zusätzlich
  `networks: [default, intern]` (default = Internet nur für Tailscale selbst).
- **Neuer Service `pforte`:**
  - `image: caddy:2.11.4-alpine` (feste Version, **nicht** `latest`)
  - `container_name: notenverwaltung-pforte`
  - `network_mode: service:tailscale`
  - Volumes: `./caddy:/etc/caddy` (**Ordner** einbinden, nicht die Einzeldatei – Empfehlung
    der Image-Doku), `caddy-daten:/data`, `caddy-config:/config`
  - `environment`: `PFORTE_USER`, `PFORTE_HASH` aus `.env` (siehe 3.3)
  - `depends_on: [tailscale, notenverwaltung]`
  - `restart: unless-stopped`
  - **Keine** `ports:`, **kein** `cap_add`.
- Service `notenverwaltung`:
  - `network_mode: service:tailscale` **entfernen**
  - `networks: [intern]` hinzufügen
  - Volumes und alles andere unverändert.
- Top-Level:
```yaml
  networks:
    intern:
      internal: true
  volumes:
    tailscale-zustand:
    caddy-daten:
    caddy-config:
```
- Die bestehenden Kommentare im Compose-File an die neue Topologie anpassen
  (insbesondere „Kein ports-Eintrag und keiner möglich …“ gilt jetzt für die Pforte;
  ergänzen: **Ein `ports:`-Eintrag am tailscale- oder pforte-Service würde die Anwendung
  im LAN öffnen – niemals hinzufügen.**)
### 3.2 Neue Datei `caddy/Caddyfile`
 
```
{
    admin off        # Admin-API abschalten (sonst ggf. aus dem Tailnet erreichbar)
    auto_https off   # kein ACME, keine ausgehenden Zertifikatsabfragen
}
 
:8000 {
    basic_auth {
        {$PFORTE_USER} {$PFORTE_HASH}
    }
    reverse_proxy notenverwaltung:8000
}
```
 
- `admin off` ist Pflicht. Folge: Konfigurationsänderungen nur per Container-Neustart
  (`docker compose restart pforte`), nicht per `caddy reload`.
- Direktivname `basic_auth` gegen die Doku der verwendeten Caddy-Version prüfen
  (älterer Name: `basicauth`).
### 3.3 Geheimnisse – nicht ins Repository
 
- `PFORTE_USER` und `PFORTE_HASH` gehören in die bestehende `.env` (dort liegt bereits
  `TS_AUTHKEY`). Sicherstellen, dass `.env` in `.gitignore` steht.
- `.env.example` (falls vorhanden, sonst anlegen) um beide Variablen mit Platzhaltern
  ergänzen.
- Hash erzeugen: `docker run --rm -it caddy:2.11.4-alpine caddy hash-password`
- **Achtung `$`:** bcrypt-Hashes enthalten `$`. In `.env` den Wert in **einfache
  Anführungszeichen** setzen, damit Compose nicht interpoliert:
  `PFORTE_HASH='$2a$14$....'`
  Mit `docker compose config` prüfen, dass der Hash vollständig ankommt.
### 3.4 Anwendung – nur prüfen, nicht ändern
 
- Prüfen (Dockerfile/CMD), dass uvicorn auf `0.0.0.0:8000` lauscht. Bei `127.0.0.1`
  wäre die Anwendung für die Pforte nicht erreichbar → **melden, nicht eigenmächtig ändern.**
- Prüfen, ob die Anwendung irgendwo ausgehende Verbindungen braucht (sollte laut
  Spezifikation nicht der Fall sein). Falls doch → melden.
## 4. Nicht Teil dieses Auftrags
 
- Keine Änderung am Anwendungscode, kein Login in der App.
- Keine Tailscale-ACLs, kein Tailscale Serve/Funnel, keine HTTPS-Zertifikate.
- Kein Authelia (mögliche spätere Ausbaustufe, erfordert HTTPS + Domain).
- Keine `ports:`-Einträge an irgendeinem Service.
- Dev-Umgebung (Port 8001, Projekt `notenverwaltung-dev`) nur anpassen, wenn sie bereits
  existiert – dann analog, mit eigenem Benutzer/Hash. Sonst nur in der Doku vermerken.
## 5. Abnahmekriterien
 
Auf TrueNAS bzw. von einem Tailnet-Gerät ausführen:
 
1. `docker compose config` läuft fehlerfrei, `PFORTE_HASH` vollständig.
2. `docker logs notenverwaltung-pforte` ohne Fehler.
3. `curl -I http://notenverwaltung:8000` → **401**.
4. `curl -I -u <user>:<passwort> http://notenverwaltung:8000` → **200** (bzw. Redirect der App).
5. Browser/Handy: Passwortabfrage, danach funktioniert die App vollständig (inkl. HTMX-Requests).
6. `docker exec notenverwaltung python -c "import urllib.request as u; u.urlopen('https://example.org', timeout=5)"`
   → **schlägt fehl** (kein Internet aus der App).
7. `sudo docker ps --format '{{.Names}}\t{{.Ports}}'` → bei keinem der drei Container
   veröffentlichte Ports.
8. `curl -I http://notenverwaltung:2019` aus dem Tailnet → **keine Antwort** (Admin-API aus).
## 6. Dokumentation
 
- Spezifikation: Festlegung „Authentifizierung an Authelia delegiert“ ersetzen durch:
  „Zugangsschutz auf Infrastrukturebene: Tailscale (nur Tailnet) + Caddy-Pforte mit
  HTTP Basic Auth im selben Compose-Stack. Die Anwendung selbst hat weiterhin keine
  Authentifizierung und keine Netzwerkverbindung nach außen.“
- README: Abschnitt „Zugang & Passwort ändern“ (Hash erzeugen, `.env` anpassen,
  `docker compose up -d pforte`).
- Bekannte Grenzen dokumentieren: kein zweiter Faktor, keine Sperre nach Fehlversuchen,
  kein Abmelden (Browser schließen).
## 7. Rückfall
 
Bei Problemen: vorheriges `docker-compose.yml` aus Git wiederherstellen,
`docker compose up -d`. Daten-Volumes sind von der Änderung nicht betroffen.
 
