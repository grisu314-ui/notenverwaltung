#!/bin/sh
# Startet die Anwendung -- aber nur, wenn die Datenbank zum Programm passt.
#
# Die Migration läuft bewusst NICHT automatisch: sie würde den produktiven
# Bestand mit Klarnamen und Lichtbildern umbauen, ohne dass jemand sie auf
# einer Kopie durchgespielt hat.
set -eu

# Relativ zum Arbeitsverzeichnis, das im Container /app ist. Dadurch lässt
# sich dieses Skript auch außerhalb des Containers aus dem Projektverzeichnis
# heraus ausführen und prüfen.
if ! python scripts/schemastand.py; then
    echo "Die Anwendung startet nicht. Grund steht darüber." >&2
    exit 1
fi

# Genau ein Worker: SQLite mit einem Nutzer; mehrere Prozesse vervielfachen
# nur die Schreibkonkurrenz, ohne irgendetwas schneller zu machen.
exec python -m uvicorn app.web.app:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1
