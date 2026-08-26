"""
Save/load: flattens the durable slice of player progression (credits,
reputation, festival influence, sponsorships, garage) to a plain JSON-
serialisable dict and back. World/physics/AI runtime state is
intentionally excluded -- a loaded save drops the player back into free
roam with a fresh world tick, not mid-physics-step, which is both simpler
and safer than trying to serialize live rigid-body state.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict

from apex_horizon_engine.economy.credits import CreditLedger
from apex_horizon_engine.economy.sponsorships import SponsorshipBook
from apex_horizon_engine.progression.festival_system import FestivalSystem
from apex_horizon_engine.progression.reputation import ReputationBook
from apex_horizon_engine.utils.logging import get_logger

logger = get_logger("core.state_manager")

SAVE_FORMAT_VERSION = 1


def build_save_payload(
    ledger: CreditLedger,
    reputation: ReputationBook,
    festival: FestivalSystem,
    sponsorships: SponsorshipBook,
    owned_vehicle_ids: list[str],
    active_vehicle_id: str,
    garage_upgrades: Dict[str, list[str]],
    player_x: float,
    player_y: float,
) -> Dict[str, Any]:
    return {
        "format_version": SAVE_FORMAT_VERSION,
        "credits": {"balance": ledger.balance},
        "reputation": reputation.as_dict(),
        "festival": {"zone_influence": dict(festival.zone_influence)},
        "sponsorships": {"active_deal_ids": list(sponsorships.active_deal_ids)},
        "garage": {
            "owned_vehicle_ids": list(owned_vehicle_ids),
            "active_vehicle_id": active_vehicle_id,
            "upgrades": {k: list(v) for k, v in garage_upgrades.items()},
        },
        "position": {"x": player_x, "y": player_y},
    }


def save_to_file(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    logger.info("Saved game state to %s", path)


def load_from_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if payload.get("format_version") != SAVE_FORMAT_VERSION:
        logger.warning("Save file %s has format_version=%s, engine expects %s",
                        path, payload.get("format_version"), SAVE_FORMAT_VERSION)
    return payload


def apply_save_payload(
    payload: Dict[str, Any],
    ledger: CreditLedger,
    reputation: ReputationBook,
    festival: FestivalSystem,
    sponsorships: SponsorshipBook,
) -> Dict[str, Any]:
    """Mutates the passed-in live objects in place and returns the
    garage/position sub-payloads for the caller (``core.engine``) to
    finish reconstructing (owned vehicles need real ``Vehicle`` instances,
    which this module deliberately doesn't own)."""
    ledger.balance = payload["credits"]["balance"]
    reputation.scores = dict(payload["reputation"])
    festival.zone_influence = dict(payload["festival"]["zone_influence"])
    sponsorships.active_deal_ids = list(payload["sponsorships"]["active_deal_ids"])
    return {"garage": payload["garage"], "position": payload["position"]}
