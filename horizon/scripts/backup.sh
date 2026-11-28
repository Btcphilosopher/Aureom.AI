#!/usr/bin/env bash
# Sauvegarde HORIZON : base PostgreSQL (format custom) + objets chiffrés + manifeste d'empreintes.
# Usage : PGURL=postgresql://user:pass@host:port/db [STORAGE_PATH=./var/objects] ./backup.sh <dossier_sortie>
set -euo pipefail
OUT="${1:?dossier de sortie requis}"
: "${PGURL:?PGURL requis (postgresql://...)}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$OUT/horizon-backup-$STAMP"
mkdir -p "$DEST"
pg_dump --format=custom --no-owner --no-privileges --file="$DEST/database.dump" "$PGURL"
if [ -n "${STORAGE_PATH:-}" ] && [ -d "$STORAGE_PATH" ]; then
  tar -C "$STORAGE_PATH" -czf "$DEST/objects.tar.gz" .
fi
( cd "$DEST" && sha256sum ./* > SHA256SUMS )
echo "$DEST"
