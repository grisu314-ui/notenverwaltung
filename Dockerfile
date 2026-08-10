# Ein Container für die Anwendung (Spezifikation Abschnitt 2).
#
# Python 3.11, weil die Anwendung genau dagegen entwickelt und getestet ist.
# Kein Node, kein Build-Schritt: das Frontend besteht aus mitgelieferten
# statischen Dateien.

FROM python:3.11-slim-bookworm

# tzdata ist nicht optional: die Anwendung rechnet gespeicherte UTC-Zeiten
# über zoneinfo nach Europe/Berlin um. Ohne die Zeitzonendatenbank scheitert
# die erste Seite, die eine Uhrzeit anzeigt.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Feste UID/GID, damit die Rechte auf dem ZFS-Dataset vergeben werden können.
# Die Anwendung läuft nicht als root.
RUN groupadd --gid 1000 notenverwaltung \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin \
       notenverwaltung

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY docker/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Der einzige Konfigurationspunkt der Anwendung.
ENV NOTENVERWALTUNG_DB=/daten/notenverwaltung.db

USER notenverwaltung
EXPOSE 8000

# Prüft mit Bordmitteln, kein zusätzliches Paket nötig.
HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"

ENTRYPOINT ["/usr/local/bin/start.sh"]
