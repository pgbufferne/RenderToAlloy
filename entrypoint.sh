#!/bin/sh
set -e

# Exporter Python en fond
python3 /app/exporter.py &

# Alloy au premier plan (process principal du conteneur).
# Render assigne dynamiquement $PORT : c'est ce port qu'il pingera pour
# considérer le service "actif" et éviter le spin-down.
exec /bin/alloy run /etc/alloy/config.alloy \
  --storage.path=/var/lib/alloy/data \
  --server.http.listen-addr=0.0.0.0:"${PORT:-12345}"
