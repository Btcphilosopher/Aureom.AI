#!/usr/bin/env bash
# Restauration HORIZON dans une base VIDE, après vérification des empreintes.
# Usage : PGURL=postgresql://.../base_cible [STORAGE_PATH=./var/objects] ./restore.sh <dossier_sauvegarde>
set -euo pipefail
SRC="${1:?dossier de sauvegarde requis}"
: "${PGURL:?PGURL requis}"
( cd "$SRC" && sha256sum --check --quiet SHA256SUMS )
pg_restore --exit-on-error --no-owner --no-privileges --dbname="$PGURL" "$SRC/database.dump"
if [ -f "$SRC/objects.tar.gz" ] && [ -n "${STORAGE_PATH:-}" ]; then
  mkdir -p "$STORAGE_PATH"
  tar -C "$STORAGE_PATH" -xzf "$SRC/objects.tar.gz"
fi
echo "Restauration terminée depuis $SRC"
