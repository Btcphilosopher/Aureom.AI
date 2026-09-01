"""
Area/energy tradeoff modelling (sections 21/30).

Area figures here are SYNTHESIS ESTIMATES: a generic, technology-
independent "cell count" proxy taken from an actual yosys `stat` run
against this project's RTL (see python/silicaflux_bitcoin/optimisation/
design_space_explore.py, which drives yosys and records real output --
this module only aggregates/ratios numbers that were actually measured,
it never invents a cell count). Cell count is NOT mm^2: converting it to
physical area requires a real standard-cell library (site size, cell
heights) this project does not have -- see docs/architecture.md's
technology-independence section.

Energy/power figures are computed ONLY when the caller supplies an
explicit power assumption (section 30's rule) -- nothing here fabricates
a wattage. Pass `power_watts=None` (the default) and the energy/power
outputs come back as None rather than a guessed number.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AreaEnergyResult:
    architecture: str
    cell_count: int | None            # SYNTHESIS ESTIMATE (yosys `stat`), or None if not measured
    hashrate_hz: float                # from performance_model.py, category carried by the caller
    power_watts: float | None         # explicit input assumption, or None
    hashes_per_cell: float | None
    energy_per_hash_joules: float | None
    hashes_per_watt: float | None


def evaluate(architecture: str, hashrate_hz: float, cell_count: int | None = None,
             power_watts: float | None = None) -> AreaEnergyResult:
    if hashrate_hz <= 0:
        raise ValueError("hashrate_hz must be > 0")

    hashes_per_cell = (hashrate_hz / cell_count) if cell_count else None
    energy_per_hash = (power_watts / hashrate_hz) if power_watts else None
    hashes_per_watt = (hashrate_hz / power_watts) if power_watts else None

    return AreaEnergyResult(
        architecture=architecture,
        cell_count=cell_count,
        hashrate_hz=hashrate_hz,
        power_watts=power_watts,
        hashes_per_cell=hashes_per_cell,
        energy_per_hash_joules=energy_per_hash,
        hashes_per_watt=hashes_per_watt,
    )


def tradeoff_table(results: list[AreaEnergyResult]) -> str:
    """Plain-text area/performance tradeoff matrix (section 21). Missing
    figures print as a short "n/a" so every column stays a fixed width
    (a longer explanatory string here would silently overflow its field
    and run into the next column with no separator) -- the caller
    prints why a column is n/a (e.g. "no power assumption given")
    separately, once, rather than repeating it per row.
    """
    col = dict(arch=40, cells=12, hashrate=16, hpc=12, jph=14, hpw=12)
    header = (f"{'Architecture':<{col['arch']}}{'Cells':>{col['cells']}}{'Hashrate(H/s)':>{col['hashrate']}}"
              f"{'H/cell':>{col['hpc']}}{'J/hash':>{col['jph']}}{'H/W':>{col['hpw']}}")
    lines = [header, "-" * len(header)]
    for r in results:
        arch = r.architecture if len(r.architecture) <= col['arch'] - 1 else r.architecture[:col['arch'] - 2] + "…"
        cells = f"{r.cell_count:,}" if r.cell_count is not None else "n/a"
        hpc = f"{r.hashes_per_cell:,.2f}" if r.hashes_per_cell is not None else "n/a"
        jph = f"{r.energy_per_hash_joules:.3e}" if r.energy_per_hash_joules is not None else "n/a"
        hpw = f"{r.hashes_per_watt:,.1f}" if r.hashes_per_watt is not None else "n/a"
        lines.append(f"{arch:<{col['arch']}}{cells:>{col['cells']}}{r.hashrate_hz:>{col['hashrate']},.0f}"
                      f"{hpc:>{col['hpc']}}{jph:>{col['jph']}}{hpw:>{col['hpw']}}")
    lines.append("")
    lines.append("Cells: SYNTHESIS ESTIMATE (yosys generic cell library, NOT mm^2 / not a real PDK -- section 23).")
    lines.append("J/hash, H/W: n/a unless an explicit power assumption was supplied (section 30).")
    return "\n".join(lines)
