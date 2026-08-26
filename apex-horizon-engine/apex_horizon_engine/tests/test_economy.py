from apex_horizon_engine.economy.credits import CreditLedger
from apex_horizon_engine.economy.sponsorships import SponsorshipBook
from apex_horizon_engine.economy.vehicle_market import VehicleMarket
from apex_horizon_engine.progression.reputation import ReputationBook
from apex_horizon_engine.progression.unlock_tree import STOCK_UPGRADE_PARTS, apply_upgrade, can_purchase, evaluate_vehicle_unlocks
from apex_horizon_engine.utils.config import get_vehicle_preset


def test_ledger_earn_and_spend():
    ledger = CreditLedger(balance=1000)
    ledger.earn(500, "test")
    assert ledger.balance == 1500
    assert ledger.spend(2000, "too_much") is False
    assert ledger.balance == 1500
    assert ledger.spend(500, "ok") is True
    assert ledger.balance == 1000
    assert ledger.history[-1].reason == "ok"


def test_vehicle_unlock_gating():
    reputation = ReputationBook()
    statuses = evaluate_vehicle_unlocks(reputation, credits_balance=1_000_000)
    hatch = next(s for s in statuses if s.item_id == "meridian_gt_hatch")
    hypercar = next(s for s in statuses if s.item_id == "solace_hypercar")
    assert hatch.unlocked is True   # tier 1, always available
    assert hypercar.unlocked is False  # tier 5, needs reputation


def test_can_purchase_requires_both_tier_and_credits():
    reputation = ReputationBook()
    spec = get_vehicle_preset("meridian_gt_hatch")
    assert can_purchase(spec, reputation, credits_balance=spec.base_price_credits) is True
    assert can_purchase(spec, reputation, credits_balance=0) is False


def test_market_purchase_deducts_credits_and_respects_gating():
    market = VehicleMarket(seed=0)
    ledger = CreditLedger(balance=1_000_000)
    reputation = ReputationBook()

    bought = market.purchase("meridian_gt_hatch", ledger, reputation)
    assert bought is not None
    assert ledger.balance < 1_000_000

    gated = market.purchase("solace_hypercar", ledger, reputation)
    assert gated is None  # not enough reputation tier


def test_market_prices_drift_but_stay_bounded():
    market = VehicleMarket(seed=1)
    base = market.price("meridian_gt_hatch")
    for _ in range(200):
        market.tick_prices(dt_days=1.0)
    new_price = market.price("meridian_gt_hatch")
    assert 0.7 * base <= new_price <= 1.4 * base


def test_apply_upgrade_increases_peak_torque_and_mass():
    spec = get_vehicle_preset("meridian_gt_hatch")
    turbo = next(p for p in STOCK_UPGRADE_PARTS if p.part_id == "turbo_stage2")
    upgraded = apply_upgrade(spec, turbo)
    original_peak = max(t for _, t in spec.engine.points)
    upgraded_peak = max(t for _, t in upgraded.engine.points)
    assert upgraded_peak > original_peak
    assert upgraded.mass_kg > spec.mass_kg
    # Original preset must be untouched (no shared-mutation bug).
    assert max(t for _, t in get_vehicle_preset("meridian_gt_hatch").engine.points) == original_peak


def test_sponsorship_upkeep_drops_lapsed_deals():
    reputation = ReputationBook()
    # overall_tier() averages across every discipline, so clearing the
    # velocore_energy deal's tier-2 requirement (avg reputation >= 8)
    # needs enough in "street" alone to carry the other four disciplines.
    reputation.gain("street", 40.0)
    book = SponsorshipBook()
    assert book.sign("velocore_energy", reputation) is True
    reputation.scores["street"] = 0.0
    lapsed = book.check_upkeep(reputation)
    assert "velocore_energy" in lapsed
    assert "velocore_energy" not in book.active_deal_ids
