"""
Structured industrial data model (spec item 54).

These are the nouns every engine in the platform reads and writes:
Factory, Building, ProductionLine, Machine, Robot, Sensor, Material, Batch,
Cell, Module, Pack, ProductionOrder, MaintenanceEvent, QualityResult,
EnergyReading, Shipment.

They are deliberately plain ``@dataclass`` objects (no ORM) so every engine
package stays independently importable and testable (spec item 62); the
``database`` package knows how to persist them, the ``api`` package knows
how to serialise them, but the dataclasses themselves have no dependency on
either.
"""
from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

_serial_counter = itertools.count(1)


def next_serial(prefix: str) -> str:
    """Deterministic-enough, human-readable serial/batch id generator."""
    return f"{prefix}-{next(_serial_counter):08d}-{uuid.uuid4().hex[:6]}"


class DataProvenance(str, Enum):
    """Every numeric fact in the twin is tagged with where it came from.

    Spec item 3 requires the system to distinguish MODEL ASSUMPTIONS from
    MEASURED FACTORY DATA -- this enum is that tag, and engines that
    fabricate engineering constants (chemistry profiles, cost benchmarks)
    must set it explicitly rather than let a reader assume it is measured.
    """

    MODEL_ASSUMPTION = "model_assumption"
    MEASURED = "measured_factory_data"
    SIMULATED_TELEMETRY = "simulated_telemetry"


class CellFormat(str, Enum):
    CYLINDRICAL = "cylindrical"
    PRISMATIC = "prismatic"
    POUCH = "pouch"


class Chemistry(str, Enum):
    LFP = "LFP"
    NMC = "NMC"
    NCA = "NCA"
    LMFP = "LMFP"
    NA_ION = "sodium_ion"


class MachineState(str, Enum):
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    CHANGEOVER = "CHANGEOVER"
    MAINTENANCE = "MAINTENANCE"
    FAULT = "FAULT"


class TestResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REWORK = "REWORK"
    REJECT = "REJECT"


class EventType(str, Enum):
    MATERIAL_RECEIVED = "MATERIAL_RECEIVED"
    BATCH_STARTED = "BATCH_STARTED"
    MACHINE_STARTED = "MACHINE_STARTED"
    MACHINE_STOPPED = "MACHINE_STOPPED"
    CELL_COMPLETED = "CELL_COMPLETED"
    QUALITY_FAILURE = "QUALITY_FAILURE"
    MAINTENANCE_REQUIRED = "MAINTENANCE_REQUIRED"
    PACK_COMPLETED = "PACK_COMPLETED"
    SHIPMENT_CREATED = "SHIPMENT_CREATED"


@dataclass
class Sensor:
    sensor_id: str
    machine_id: Optional[str]
    metric: str  # e.g. "temperature_c", "vibration_mm_s", "humidity_pct"
    unit: str


@dataclass
class Material:
    material_id: str
    name: str
    category: str
    unit: str  # "kg", "m2", "unit"
    density_kg_m3: Optional[float] = None


@dataclass
class Batch:
    """A raw-material batch received from a supplier (spec item 4)."""

    batch_id: str
    material_id: str
    supplier_id: str
    quantity: float
    unit: str
    cost_per_unit: float
    received_at: datetime
    moisture_pct: float
    purity_pct: float
    lead_time_days: float
    quality_score: float = 0.0


@dataclass
class Building:
    building_id: str
    name: str
    floor_area_m2: float
    halls: list[str] = field(default_factory=list)


@dataclass
class Robot:
    robot_id: str
    role: str  # material_handling / cell_movement / assembly / palletisation / inspection
    cycle_time_s: float
    line_id: Optional[str] = None


@dataclass
class Machine:
    machine_id: str
    name: str
    stage: str
    line_id: str
    state: MachineState = MachineState.OFFLINE
    cycle_time_s: float = 1.0
    rated_throughput_per_hr: float = 0.0
    energy_kwh_cumulative: float = 0.0
    utilisation_pct: float = 0.0
    downtime_hours: float = 0.0
    fault_count: int = 0
    runtime_hours: float = 0.0


@dataclass
class ProductionLine:
    line_id: str
    name: str
    building_id: str
    cell_format: CellFormat
    capacity_cells_per_hour: float
    machines: list[str] = field(default_factory=list)


@dataclass
class ElectrodeBatch:
    batch_id: str
    electrode_type: str  # "anode" | "cathode"
    material_batch_ids: list[str]
    thickness_um: float
    density_g_cc: float
    coating_uniformity_std_pct: float
    yield_pct: float
    scrap_pct: float


@dataclass
class Cell:
    serial_number: str
    cell_format: CellFormat
    chemistry: Chemistry
    electrode_batch_ids: list[str]
    line_id: str
    capacity_ah: float = 0.0
    internal_resistance_mohm: float = 0.0
    voltage_v: float = 0.0
    weight_g: float = 0.0
    test_result: Optional[TestResult] = None
    formation_batch_id: Optional[str] = None


@dataclass
class Module:
    module_id: str
    cell_serials: list[str]
    series_count: int
    parallel_count: int
    capacity_ah: float = 0.0
    resistance_mohm: float = 0.0
    mismatch_score: float = 0.0


@dataclass
class Pack:
    pack_id: str
    module_ids: list[str]
    series_count: int
    parallel_count: int
    nominal_voltage_v: float = 0.0
    capacity_kwh: float = 0.0
    bms_id: Optional[str] = None
    test_result: Optional[TestResult] = None


@dataclass
class ProductionOrder:
    order_id: str
    product_spec: str
    quantity: int
    due_date: datetime
    priority: int = 1
    completed_quantity: int = 0


@dataclass
class MaintenanceEvent:
    event_id: str
    machine_id: str
    event_type: str  # "predicted" | "scheduled" | "corrective"
    created_at: datetime
    remaining_useful_life_hours: Optional[float] = None
    failure_probability: Optional[float] = None
    resolved: bool = False


@dataclass
class QualityResult:
    result_id: str
    subject_id: str  # cell serial / module id / pack id
    stage: str
    measurements: dict[str, float]
    result: TestResult
    timestamp: datetime


@dataclass
class EnergyReading:
    reading_id: str
    timestamp: datetime
    category: str  # electricity / hvac / dry_room / formation / compressed_air / ...
    machine_id: Optional[str]
    kwh: float


@dataclass
class Shipment:
    shipment_id: str
    order_id: str
    pack_ids: list[str]
    created_at: datetime
    destination: str


@dataclass
class FactoryEvent:
    """Generic factory event envelope used by the telemetry event stream."""

    event_type: EventType
    timestamp: datetime
    payload: dict[str, Any]
    source: str = "simulation"
