"""
Management / Operations / Engineering / Finance dashboards (spec items
56-60). Text-first (so they run anywhere, including this session's remote
container with no display) with an optional matplotlib chart export when
the extra is installed. Every figure is read straight off a
``FactoryTwinResult`` -- there is nothing decorative here that isn't backed
by the simulation.
"""
from __future__ import annotations

from batteryfactory.core.factory_twin import FactoryDigitalTwin, FactoryTwinResult


def _rule(title: str) -> str:
    return f"\n{'=' * 70}\n{title}\n{'=' * 70}"


def render_management_dashboard(twin: FactoryDigitalTwin, result: FactoryTwinResult) -> str:
    sim = result.simulation
    lines = [_rule(f"MANAGEMENT DASHBOARD -- {twin.config.name}")]
    lines += [
        f"Simulated window:            {sim.hours_simulated:.1f} h",
        f"Cells produced:              {sim.cells_completed:,}",
        f"MWh produced:                {result.energy.kwh_per_kwh_produced * sim.cells_completed * twin.profile.capacity_ah_reference * twin.profile.nominal_voltage_v / 1e6:.2f}",
        f"First-pass yield:            {100.0 * sim.pass_count / max(sim.pass_count + sim.rework_count + sim.fail_count + sim.reject_count, 1):.1f}%",
        f"Scrap units:                 {sim.cells_scrapped_or_rejected:,}",
        f"Energy:                      {result.energy.total_factory_kwh:,.0f} kWh ({result.energy.kwh_per_cell:.2f} kWh/cell)",
        f"Cost per kWh:                {result.unit_cost.cost_per_kwh:,.2f}",
        f"Modules / Packs completed:   {sim.modules_completed} / {sim.packs_completed}",
        f"Orders shipped (units):      {sim.stage_stats['shipping'].completed_units}",
        f"Factory EBITDA (annualised): {result.financials.ebitda:,.0f}",
        f"Open safety alarms:          {len(result.safety_alarms)}",
    ]
    return "\n".join(lines)


def render_operations_dashboard(twin: FactoryDigitalTwin, result: FactoryTwinResult) -> str:
    lines = [_rule("OPERATIONS DASHBOARD")]
    for name, stats in result.simulation.stage_stats.items():
        total = stats.busy_hours + stats.idle_hours
        util = 100.0 * stats.busy_hours / total if total else 0.0
        lines.append(f"{name:12s} state=running  util={util:5.1f}%  completed={stats.completed_units:6d}  scrapped={stats.scrapped_units:5d}")
    lines.append("\nBuffers (WIP / capacity, starved / blocked events):")
    for name, buf in result.simulation.buffers.items():
        lines.append(f"  {name:16s} {buf.wip:3d}/{buf.capacity:3d}   starved={buf.starved_events:4d}  blocked={buf.blocked_events:4d}")
    lines.append("\nBottleneck ranking (highest score first):")
    for b in result.bottlenecks[:5]:
        lines.append(f"  {b.stage:12s} score={b.score:5.1f}  util={b.utilisation_pct:5.1f}%  scrap={b.scrap_rate_pct:5.1f}%  queue={b.queue_utilisation_pct:5.1f}%")
    return "\n".join(lines)


def render_engineering_dashboard(twin: FactoryDigitalTwin, result: FactoryTwinResult) -> str:
    lines = [_rule("ENGINEERING DASHBOARD")]
    for metric, cap in result.quality_capability.items():
        lines.append(f"{metric:16s} mean={cap.mean:8.3f} std={cap.std:6.3f} Cp={cap.cp:5.2f} Cpk={cap.cpk:5.2f} defect_rate={cap.defect_rate_ppm:8.1f} ppm")
    lines.append("\nPredictive maintenance (top 5 by failure probability):")
    for pred in sorted(result.maintenance_predictions, key=lambda p: -p.failure_probability_next_week)[:5]:
        lines.append(f"  {pred.machine_id:16s} P(fail/7d)={pred.failure_probability_next_week:.3%}  RUL={pred.remaining_useful_life_hours:8.0f}h  anomaly={pred.anomaly_score:.2f}")
    return "\n".join(lines)


def render_finance_dashboard(twin: FactoryDigitalTwin, result: FactoryTwinResult) -> str:
    f = result.financials
    lines = [_rule("FINANCE DASHBOARD (annualised from this run's rates)")]
    lines += [
        f"Revenue:              {f.revenue:,.0f}",
        f"COGS:                 {f.cogs:,.0f}",
        f"Gross profit:         {f.gross_profit:,.0f}  ({f.gross_margin_pct:.1f}% margin)",
        f"EBITDA:               {f.ebitda:,.0f}",
        f"EBIT:                 {f.ebit:,.0f}",
        f"Cash flow:            {f.cash_flow:,.0f}",
        f"Cost per cell:        {result.unit_cost.cost_per_cell:,.2f}",
        f"Cost per kWh:         {result.unit_cost.cost_per_kwh:,.2f}",
        f"Cost per pack:        {result.unit_cost.cost_per_pack:,.2f}",
        "Cost breakdown:       " + ", ".join(f"{k}={v:.1f}%" for k, v in result.unit_cost.breakdown_pct.items()),
    ]
    return "\n".join(lines)


def render_all(twin: FactoryDigitalTwin, result: FactoryTwinResult) -> str:
    return "\n".join([
        render_management_dashboard(twin, result),
        render_operations_dashboard(twin, result),
        render_engineering_dashboard(twin, result),
        render_finance_dashboard(twin, result),
    ])


def plot_energy_breakdown(result: FactoryTwinResult, out_path: str) -> bool:
    """Optional matplotlib chart. Returns False (no-op) if matplotlib isn't installed."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    b = result.energy.breakdown
    labels = ["Formation", "HVAC/Dry room", "Compressed air", "Other machines"]
    values = [b.formation_kwh, b.hvac_dry_room_kwh, b.compressed_air_kwh, b.other_machine_kwh]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(labels, values, color="#3a7ca5")
    ax.set_ylabel("kWh")
    ax.set_title("Factory Energy Breakdown")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return True
