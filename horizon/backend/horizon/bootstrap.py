"""Initialisation idempotente (conteneur « migrate ») : migrations, données
synthétiques si la base est vide, puis — optionnellement — rejeu des étapes 1 à 3
de la démonstration pour obtenir l'état de la maquette."""
from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from horizon.core.db import SessionLocal
from horizon.modules.organizations.models import Organization


def main() -> None:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "alembic"))
    command.upgrade(cfg, "head")
    with SessionLocal() as s:
        empty = s.scalar(select(Organization.id).limit(1)) is None
    if not empty:
        print("Base déjà initialisée : aucune donnée ajoutée.")
        return
    from horizon.seed import seed

    seed()
    print("Données synthétiques du Groupe Lumière créées.")
    if os.environ.get("HORIZON_BOOTSTRAP_MOCKUP_STATE", "true") == "true":
        from horizon.demo import run

        run(None, 3, None)
        print("État de la maquette reproduit (étapes 1 à 3 de la démonstration).")


if __name__ == "__main__":
    main()
