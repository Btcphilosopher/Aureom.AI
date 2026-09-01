import numpy as np

from batteryfactory.materials.inventory import InventoryLedger
from batteryfactory.materials.inventory_optimiser import (
    economic_order_quantity, optimise_supplier_mix, reorder_point, safety_stock,
)
from batteryfactory.materials.supply_chain import Supplier, SupplyChainSimulator


def test_inventory_receive_and_fifo_consume():
    ledger = InventoryLedger()
    ledger.receive_batch("graphite", "sup-1", 1000.0, 8.0, moisture_pct=0.2, purity_pct=99.8, lead_time_days=10)
    ledger.receive_batch("graphite", "sup-2", 500.0, 8.5, moisture_pct=0.2, purity_pct=99.8, lead_time_days=12)
    assert ledger.stock_level("graphite") == 1500.0

    records, consumed = ledger.consume("graphite", 1200.0)
    assert consumed == 1200.0
    assert ledger.stock_level("graphite") == 300.0
    assert records[0].quantity_consumed == 1000.0  # FIFO: first batch drained first


def test_inventory_rejects_out_of_spec_batch():
    ledger = InventoryLedger()
    ledger.receive_batch("graphite", "sup-1", 100.0, 8.0, moisture_pct=5.0, purity_pct=90.0, lead_time_days=5)
    assert ledger.stock_level("graphite") == 0.0
    assert len(ledger.rejected_batches) == 1


def test_eoq_and_safety_stock_positive():
    eoq = economic_order_quantity(annual_demand=100_000, order_cost=500, holding_cost_per_unit_per_year=2.0)
    assert eoq > 0
    ss = safety_stock(demand_std_per_day=50, lead_time_days=14, service_level=0.97)
    assert ss > 0
    rop = reorder_point(avg_demand_per_day=200, avg_lead_time_days=14, safety_stock_units=ss)
    assert rop > ss


def test_supplier_mix_respects_capacity_and_diversifies():
    suppliers = [
        Supplier("s1", "Supplier A", "graphite", "CN", monthly_capacity=500, lead_time_days_mean=20, lead_time_days_std=3,
                 reliability=0.95, price_per_unit=8.0, minimum_order_quantity=50, quality_mean_pct=99.5, quality_std_pct=0.2,
                 disruption_probability=0.02),
        Supplier("s2", "Supplier B", "graphite", "AU", monthly_capacity=800, lead_time_days_mean=25, lead_time_days_std=4,
                 reliability=0.90, price_per_unit=7.5, minimum_order_quantity=100, quality_mean_pct=99.0, quality_std_pct=0.3,
                 disruption_probability=0.05),
    ]
    result = optimise_supplier_mix(suppliers, required_quantity=900, max_single_supplier_share=0.7)
    assert abs(result.total_quantity - 900) < 1e-6
    assert len(result.allocations) >= 2  # diversified, not all on one supplier
    for alloc in result.allocations:
        assert alloc.quantity <= 900 * 0.7 + 1e-6


def test_supply_chain_simulator_disruptions():
    rng = np.random.default_rng(0)
    sim = SupplyChainSimulator(rng=rng)
    supplier = Supplier("s1", "Supplier A", "graphite", "CN", monthly_capacity=1000, lead_time_days_mean=20,
                         lead_time_days_std=2, reliability=0.5, price_per_unit=8.0, minimum_order_quantity=10,
                         quality_mean_pct=99.0, quality_std_pct=0.5, disruption_probability=0.5)
    outcomes = [sim.place_order(supplier, 100) for _ in range(50)]
    assert any(o.disruption.value != "none" for o in outcomes)
    assert all(o.delivered_quantity <= o.ordered_quantity for o in outcomes)
