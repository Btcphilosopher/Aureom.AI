"""
Factory discrete-event simulator (spec item 19).

Wires materials -> electrode production -> cell assembly -> formation ->
testing -> module assembly -> pack assembly -> QC -> warehouse -> shipping
into one pipeline of generic producer/consumer stage processes running on
the ``simulation.events`` kernel, using ``machines.conveyor.Buffer`` for
WIP/starvation/blocking and ``machines.machine_twin.MachineTwin`` for
per-stage machine state.

Cells move through the line in **lots** (a lot represents a fixed number of
physical cells). Detailed per-cell physics (mixing/coating/assembly/
formation/EOL test) are run on a bounded sample drawn from each lot and the
resulting yield/scrap/quality rates are applied to the whole lot -- this
keeps a gigafactory-scale run (hundreds of thousands of cells) tractable
while still deriving every reported number from the same engines used
elsewhere in the platform, rather than a separate hard-coded throughput
constant.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from batteryfactory.config.chemistry_profiles import ChemistryProfile
from batteryfactory.config.factory_config import FactoryConfig
from batteryfactory.datamodel.models import (
    Cell, EventType, MachineState, TestResult, next_serial,
)
from batteryfactory.machines.conveyor import Buffer, MaterialFlowNetwork
from batteryfactory.machines.machine_twin import MachineTwin, MachineTwinConfig
from batteryfactory.production.calendering import CalenderingParameters
from batteryfactory.production.cell_assembly import CellAssemblyLine
from batteryfactory.production.coating import CoatingParameters
from batteryfactory.production.electrode_line import ElectrodeLineConfig, ElectrodeProductionLine
from batteryfactory.production.formation import FormationLine, FormationRecipe
from batteryfactory.production.mixing import MixingRecipe
from batteryfactory.production.testing import EOLTester
from batteryfactory.quality.cell_matching import CellMatchingEngine
from batteryfactory.simulation.events import Environment, Timeout
from batteryfactory.telemetry.event_stream import EventBus

_SAMPLE_SIZE = 20  # cells sampled per lot for detailed physics


@dataclass
class Lot:
    lot_id: str
    size: int
    sample_cells: list[Cell] = field(default_factory=list)


@dataclass
class StageStats:
    name: str
    completed_units: int = 0
    scrapped_units: int = 0
    energy_kwh: float = 0.0
    busy_hours: float = 0.0
    idle_hours: float = 0.0


@dataclass
class FactorySimulationResult:
    hours_simulated: float
    lots_started: int
    cells_completed: int
    cells_scrapped_or_rejected: int
    pass_count: int
    rework_count: int
    fail_count: int
    reject_count: int
    modules_completed: int
    packs_completed: int
    total_energy_kwh: float
    stage_stats: dict[str, StageStats]
    buffers: dict[str, Buffer]
    event_bus: EventBus


class FactorySimulationEngine:
    def __init__(
        self,
        config: FactoryConfig,
        profile: ChemistryProfile,
        lot_size: int = 200,
        buffer_capacity_lots: int = 8,
        formation_channels: int = 8,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.config = config
        self.profile = profile
        self.lot_size = lot_size
        self.rng = rng or np.random.default_rng()
        self.event_bus = EventBus()
        self.network = MaterialFlowNetwork()

        self.electrode_anode = ElectrodeProductionLine(rng=self.rng)
        self.electrode_cathode = ElectrodeProductionLine(rng=self.rng)
        self.assembly = CellAssemblyLine(config.cell_format, config.chemistry, "line-1", rng=self.rng)
        self.formation = FormationLine(rng=self.rng)
        self.tester = EOLTester(rng=self.rng)
        self.matcher = CellMatchingEngine()

        self.buf_assembly = self.network.add_buffer("assembly_in", buffer_capacity_lots)
        self.buf_formation = self.network.add_buffer("formation_in", buffer_capacity_lots)
        self.buf_testing = self.network.add_buffer("testing_in", buffer_capacity_lots)
        self.buf_module = self.network.add_buffer("module_in", buffer_capacity_lots)
        self.buf_pack = self.network.add_buffer("pack_in", buffer_capacity_lots)
        self.buf_warehouse = self.network.add_buffer("warehouse", buffer_capacity_lots * 10)

        self.formation_channels = formation_channels
        self.machines: dict[str, MachineTwin] = {
            stage: MachineTwin(MachineTwinConfig(f"M-{stage}", stage.title(), stage, cycle_time_s=2.0, rated_power_kw=power))
            for stage, power in [
                ("electrode", 220.0), ("assembly", 150.0),
                ("testing", 40.0), ("module", 60.0), ("pack", 90.0),
            ]
        }
        # Formation is a long-dwell batch process (hours per lot), so unlike
        # every other stage it needs *parallel* capacity to keep pace with a
        # line that turns out a new lot every few minutes -- modelled here
        # as a bank of independent formation-rack twins rather than one
        # machine serving a queue.
        self.formation_machines: list[MachineTwin] = [
            MachineTwin(MachineTwinConfig(f"M-formation-{i}", f"Formation Rack {i}", "formation", cycle_time_s=2.0, rated_power_kw=50.0))
            for i in range(formation_channels)
        ]
        self.machines.update({f"formation_{i}": m for i, m in enumerate(self.formation_machines)})
        for m in self.machines.values():
            m.transition(MachineState.STARTING)
            m.transition(MachineState.RUNNING)

        self.stage_stats: dict[str, StageStats] = {
            name: StageStats(name) for name in
            ["electrode", "assembly", "formation", "testing", "module", "pack", "shipping"]
        }
        self.lots_started = 0
        self.pass_count = self.rework_count = self.fail_count = self.reject_count = 0
        self.modules_completed = 0
        self.packs_completed = 0

    def _electrode_config(self, electrode_type: str) -> ElectrodeLineConfig:
        return ElectrodeLineConfig(
            electrode_type=electrode_type,
            mixing_recipe=MixingRecipe(94.0, 3.0, 3.0, 45.0, 90.0, 25.0, 4500.0),
            coating_params=CoatingParameters(line_speed_m_min=30.0, target_thickness_um=80.0, web_width_mm=600.0, drying_zone_temp_c=110.0),
            calendering_params=CalenderingParameters(roller_pressure_kn_m=300.0, target_thickness_um=60.0, line_speed_m_min=30.0, temperature_c=40.0),
        )

    def _electrode_process(self, env, poll_interval: float):
        cfg_a = self._electrode_config("anode")
        cfg_c = self._electrode_config("cathode")
        machine = self.machines["electrode"]
        while True:
            if self.buf_assembly.is_full:
                machine.transition(MachineState.IDLE) if machine.state == MachineState.RUNNING else None
                self.stage_stats["electrode"].idle_hours += poll_interval
                yield Timeout(poll_interval)
                continue
            if machine.state != MachineState.RUNNING:
                machine.transition(MachineState.RUNNING)
            cycle_hours = self.lot_size / self.config.line_capacity_cells_per_hour
            yield Timeout(cycle_hours)
            machine.step(cycle_hours)

            anode = self.electrode_anode.run_batch(cfg_a, batch_size_kg=self.lot_size * 0.02, material_batch_ids=[])
            cathode = self.electrode_cathode.run_batch(cfg_c, batch_size_kg=self.lot_size * 0.03, material_batch_ids=[])
            self.stage_stats["electrode"].energy_kwh += anode.stage_energy_kwh + cathode.stage_energy_kwh
            self.stage_stats["electrode"].busy_hours += cycle_hours

            usable_fraction = (anode.stage_yield_pct / 100.0 + cathode.stage_yield_pct / 100.0) / 2.0
            lot_size = max(1, int(round(self.lot_size * usable_fraction)))
            lot = Lot(lot_id=next_serial("LOT"), size=lot_size, sample_cells=[])
            self.lots_started += 1
            self.event_bus.emit(EventType.BATCH_STARTED, {"lot_id": lot.lot_id, "size": lot.size}, env.now)
            self.buf_assembly.push(lot)

    def _assembly_process(self, env, poll_interval: float):
        machine = self.machines["assembly"]
        while True:
            if self.buf_assembly.is_empty:
                self.stage_stats["assembly"].idle_hours += poll_interval
                yield Timeout(poll_interval)
                continue
            if self.buf_pack.is_full or self.buf_formation.is_full:
                yield Timeout(poll_interval)
                continue
            lot: Lot = self.buf_assembly.pull()
            cycle_hours = lot.size / self.config.line_capacity_cells_per_hour
            yield Timeout(cycle_hours)
            machine.step(cycle_hours)
            self.stage_stats["assembly"].busy_hours += cycle_hours

            n_sample = min(_SAMPLE_SIZE, lot.size)
            scrapped = 0
            good_cells: list[Cell] = []
            for _ in range(n_sample):
                result = self.assembly.assemble([])
                self.stage_stats["assembly"].energy_kwh += result.total_energy_kwh
                if result.cell is None:
                    scrapped += 1
                else:
                    good_cells.append(result.cell)
            scrap_fraction = scrapped / n_sample if n_sample else 0.0
            good_lot_size = max(0, int(round(lot.size * (1.0 - scrap_fraction))))
            self.stage_stats["assembly"].scrapped_units += int(round(lot.size * scrap_fraction))
            self.stage_stats["assembly"].completed_units += good_lot_size

            if good_lot_size > 0 and good_cells:
                new_lot = Lot(lot_id=lot.lot_id, size=good_lot_size, sample_cells=good_cells[:n_sample])
                self.buf_formation.push(new_lot)

    def _formation_process(self, env, poll_interval: float, machine: MachineTwin):
        recipe = FormationRecipe(num_cycles=2, charge_c_rate=0.5, discharge_c_rate=1.0)
        while True:
            if self.buf_formation.is_empty:
                self.stage_stats["formation"].idle_hours += poll_interval
                yield Timeout(poll_interval)
                continue
            if self.buf_testing.is_full:
                yield Timeout(poll_interval)
                continue
            lot: Lot = self.buf_formation.pull()
            sample_results = [self.formation.run(c, self.profile, recipe) for c in lot.sample_cells] or \
                [self.formation.run(Cell(next_serial("CELL"), self.config.cell_format, self.config.chemistry, [], "line-1"), self.profile, recipe)]
            duration_hours = float(np.mean([r.duration_hr for r in sample_results]))
            yield Timeout(duration_hours)
            machine.step(duration_hours)
            self.stage_stats["formation"].busy_hours += duration_hours
            self.stage_stats["formation"].energy_kwh += sum(r.energy_charge_kwh for r in sample_results)

            pass_fraction = sum(1 for r in sample_results if r.passed) / len(sample_results)
            lot_size = max(0, int(round(lot.size * pass_fraction)))
            self.stage_stats["formation"].scrapped_units += lot.size - lot_size
            self.stage_stats["formation"].completed_units += lot_size

            cells = (lot.sample_cells if lot.sample_cells else [])[:min(_SAMPLE_SIZE, lot_size)]
            for c, r in zip(cells, sample_results):
                c.formation_batch_id = r.formation_batch_id
            if lot_size > 0:
                self.buf_testing.push(Lot(lot.lot_id, lot_size, cells))

    def _testing_process(self, env, poll_interval: float):
        machine = self.machines["testing"]
        recipe = FormationRecipe()
        while True:
            if self.buf_testing.is_empty:
                self.stage_stats["testing"].idle_hours += poll_interval
                yield Timeout(poll_interval)
                continue
            if self.buf_module.is_full:
                yield Timeout(poll_interval)
                continue
            lot: Lot = self.buf_testing.pull()
            cycle_hours = min(lot.size, _SAMPLE_SIZE) * 0.002  # ~7s/cell test
            yield Timeout(cycle_hours)
            machine.step(cycle_hours)
            self.stage_stats["testing"].busy_hours += cycle_hours

            cells = lot.sample_cells or [Cell(next_serial("CELL"), self.config.cell_format, self.config.chemistry, [], "line-1")
                                          for _ in range(min(_SAMPLE_SIZE, lot.size))]
            counts = {r: 0 for r in TestResult}
            passed_cells: list[Cell] = []
            for c in cells:
                # Cells reaching testing should already carry a formation result; re-run
                # formation defensively for any synthetic/fallback cell that doesn't.
                approx = self.formation.run(c, self.profile, recipe)
                cell, qr = self.tester.run(c, self.profile, approx)
                counts[qr.result] += 1
                self.event_bus.emit(EventType.CELL_COMPLETED if qr.result == TestResult.PASS else EventType.QUALITY_FAILURE,
                                     {"serial": cell.serial_number, "result": qr.result.value}, env.now)
                if qr.result == TestResult.PASS:
                    passed_cells.append(cell)

            n = len(cells)
            pass_rate = counts[TestResult.PASS] / n if n else 0.0
            self.pass_count += counts[TestResult.PASS]
            self.rework_count += counts[TestResult.REWORK]
            self.fail_count += counts[TestResult.FAIL]
            self.reject_count += counts[TestResult.REJECT]

            good_lot_size = max(0, int(round(lot.size * pass_rate)))
            self.stage_stats["testing"].completed_units += good_lot_size
            self.stage_stats["testing"].scrapped_units += lot.size - good_lot_size
            if good_lot_size > 0:
                self.buf_module.push(Lot(lot.lot_id, good_lot_size, passed_cells))

    def _module_pack_process(self, env, poll_interval: float):
        """
        Module/pack formation accumulates good cells across *many* lots before
        a module-sized group is complete (a module is 10s-100s of cells; a
        single production lot rarely lines up exactly on that boundary), so
        this stage keeps a running WIP carry of unassigned cells/modules
        rather than requiring each individual lot to fill a whole module.
        """
        machine_m, machine_p = self.machines["module"], self.machines["pack"]
        cells_per_module = self.config.module_architecture.cells_per_module
        modules_per_pack = self.config.pack_architecture.modules_per_pack
        cell_carry = 0
        sample_carry: list[Cell] = []
        module_carry = 0
        while True:
            if self.buf_module.is_empty:
                self.stage_stats["module"].idle_hours += poll_interval
                yield Timeout(poll_interval)
                continue
            lot: Lot = self.buf_module.pull()
            cycle_hours = lot.size / self.config.line_capacity_cells_per_hour
            yield Timeout(cycle_hours)
            machine_m.step(cycle_hours)
            machine_p.step(cycle_hours)
            self.stage_stats["module"].busy_hours += cycle_hours

            cell_carry += lot.size
            sample_carry.extend(lot.sample_cells)

            modules_in_lot = int(cell_carry // cells_per_module) if cells_per_module else 0
            if modules_in_lot > 0:
                cell_carry -= modules_in_lot * cells_per_module
                if len(sample_carry) >= cells_per_module:
                    self.matcher.match_cells_to_modules(
                        sample_carry, cells_per_module,
                        self.config.module_architecture.cells_series, self.config.module_architecture.cells_parallel,
                    )
                    sample_carry = []  # sample consumed into matched groups
                self.modules_completed += modules_in_lot
                self.stage_stats["module"].completed_units += modules_in_lot
                module_carry += modules_in_lot

            packs_in_lot = int(module_carry // modules_per_pack) if modules_per_pack else 0
            if packs_in_lot > 0:
                module_carry -= packs_in_lot * modules_per_pack
                self.packs_completed += packs_in_lot
                self.stage_stats["pack"].completed_units += packs_in_lot
                self.event_bus.emit(EventType.PACK_COMPLETED, {"lot_id": lot.lot_id, "count": packs_in_lot}, env.now)
                self.buf_warehouse.push(Lot(lot.lot_id, packs_in_lot))

    def _shipping_process(self, env, poll_interval: float, ship_interval_hours: float = 4.0):
        while True:
            yield Timeout(ship_interval_hours)
            shipped = 0
            while not self.buf_warehouse.is_empty:
                lot = self.buf_warehouse.pull()
                shipped += lot.size
            if shipped:
                self.stage_stats["shipping"].completed_units += shipped
                self.event_bus.emit(EventType.SHIPMENT_CREATED, {"pack_count": shipped}, env.now)

    def run(self, hours: float, poll_interval: float = 0.1) -> FactorySimulationResult:
        env = Environment()
        env.on_event = None
        env.process(self._electrode_process(env, poll_interval))
        env.process(self._assembly_process(env, poll_interval))
        for machine in self.formation_machines:
            env.process(self._formation_process(env, poll_interval, machine))
        env.process(self._testing_process(env, poll_interval))
        env.process(self._module_pack_process(env, poll_interval))
        env.process(self._shipping_process(env, poll_interval))
        env.run(until=hours)

        total_energy = sum(s.energy_kwh for s in self.stage_stats.values())
        cells_completed = self.stage_stats["testing"].completed_units
        cells_scrapped = sum(s.scrapped_units for s in self.stage_stats.values())

        return FactorySimulationResult(
            hours_simulated=hours,
            lots_started=self.lots_started,
            cells_completed=cells_completed,
            cells_scrapped_or_rejected=cells_scrapped,
            pass_count=self.pass_count,
            rework_count=self.rework_count,
            fail_count=self.fail_count,
            reject_count=self.reject_count,
            modules_completed=self.modules_completed,
            packs_completed=self.packs_completed,
            total_energy_kwh=total_energy,
            stage_stats=self.stage_stats,
            buffers=self.network.buffers,
            event_bus=self.event_bus,
        )
