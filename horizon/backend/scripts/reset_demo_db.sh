#!/usr/bin/env bash
# Réinitialise la base de DÉMONSTRATION : schéma recréé par Alembic puis données synthétiques.
# Ne jamais utiliser sur une base contenant des données à conserver.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${HORIZON_ENV:-demo}" != "demo" ] && [ "${HORIZON_ENV:-demo}" != "test" ]; then
  echo "Refus : HORIZON_ENV=${HORIZON_ENV} (réservé aux environnements demo/test)" >&2
  exit 1
fi
alembic downgrade base
alembic upgrade head
python -m horizon.seed
if [ "${1:-}" = "--mockup-state" ]; then
  # Rejoue les étapes 1 à 3 de la démonstration : état identique à la maquette (lot de 480 000 € en attente).
  python -W ignore -m horizon.demo --until 3
fi
