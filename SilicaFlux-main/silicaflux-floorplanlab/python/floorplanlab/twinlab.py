"""TwinLab exchange format: FloorplanLab -> SilicaFlux TwinLab.

Status of the integration (audited): the SilicaFlux TwinLab application in the
repository (silicaflux-twinlab.zip, Angular) keeps its floorplan as a hard-coded
`signal<SemiconductorBlock[]>` in services/twinlab-state.ts and has NO file
import.  The integration is therefore NOT complete: this module defines the
exchange schema (JSON Schema generated from the Pydantic models below), writes
the export, and also emits `twinlab_blocks`, a list shaped like TwinLab's
`SemiconductorBlock` interface, so a future TwinLab importer can consume it.
Quantities FloorplanLab does not establish (per-block power, temperature,
IR drop, 3-D z level) are null -- never filled with placeholders.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"
Box = list[float]


class Provenance(BaseModel):
    run_id: str
    design: str
    top: str
    platform: str
    process: str
    orfs_revision: Optional[str] = None
    tools: dict[str, str] = Field(default_factory=dict)
    netlist_sha256: Optional[str] = None
    source_odb: str
    created: str
    fidelity: Literal["OPENROAD_PRELIMINARY"] = "OPENROAD_PRELIMINARY"
    label: str = ("Preliminary floorplan/placement from OpenROAD (ORFS). Pre-CTS, pre-detailed-route; "
                  "not a signoff or fabrication-ready layout.")


class Layer(BaseModel):
    name: str
    direction: str
    pitch_um: Optional[float] = None
    width_um: Optional[float] = None


class Technology(BaseModel):
    site: str
    row_height_um: float
    site_width_um: float
    routing_layers: list[Layer]
    signal_layer_range: list[str]
    supply_voltage_v: Optional[float] = None
    analysis_corner: str


class MacroX(BaseModel):
    name: str
    master: str
    bbox_um: Box
    orient: str
    status: str
    group: str
    words: Optional[int] = None
    bits: Optional[int] = None
    signal_pin_edge: Optional[str] = None


class GroupX(BaseModel):
    name: str
    label: str
    cells: int
    area_um2: float
    centroid_um: list[float]
    extent_um: Box
    annotation_only: bool = True      # placement extent of the group's cells, not a physical fence


class DensityGrid(BaseModel):
    bins: int
    bin_w_um: float
    bin_h_um: float
    origin_um: list[float]
    utilisation: list[list[float]]


class PinX(BaseModel):
    name: str
    dir: str
    layer: str
    bbox_um: Box
    edge: str


class Stripe(BaseModel):
    net: str
    layer: str
    shape: str
    bbox_um: Box


class PowerGrid(BaseModel):
    stripes: list[Stripe]
    followpin_rails: list[dict]
    connectivity: Optional[dict] = None


class TimingX(BaseModel):
    label: Optional[str] = None
    wns_ns: Optional[float] = None
    tns_ns: Optional[float] = None
    whs_ns: Optional[float] = None
    clock_period_ns: Optional[float] = None
    critical_paths: list[dict] = Field(default_factory=list)


class RoutingX(BaseModel):
    label: Optional[str] = None
    completed: Optional[bool] = None
    overflow_total: Optional[int] = None
    routed_wirelength_um: Optional[float] = None
    layers: dict = Field(default_factory=dict)


class TwinLabBlock(BaseModel):
    """Shape of TwinLab's `SemiconductorBlock` (models/semiconductor.models.ts)."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    type: Literal["CPU_CORE", "VECTOR_UNIT", "TENSOR_ARRAY", "SRAM_BANK", "NOC_ROUTER", "MEM_CTRL", "CLK_GEN",
                  "POWER_MGMT", "IO_PAD_RING", "DFT_JTAG"]
    x: float
    y: float
    width: float
    height: float
    zLevel: Optional[float] = None
    color: str
    dynamicPowerMw: Optional[float] = None
    leakagePowerMw: Optional[float] = None
    activityFactor: Optional[float] = None
    cellCount: int
    timingSlackPs: Optional[float] = None
    metalDensity: Optional[float] = None
    voltageDomain: str
    clockDomain: str
    locked: bool = False
    temperatureC: Optional[float] = None
    irDropMv: Optional[float] = None
    provenanceNote: str


class FloorplanExport(BaseModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    provenance: Provenance
    technology: Technology
    die_um: Box
    core_um: Box
    macros: list[MacroX]
    std_cell_groups: list[GroupX]
    density_grid: Optional[DensityGrid] = None
    io_pins: list[PinX]
    clock_source_pin: Optional[PinX] = None
    power_grid: PowerGrid
    area: dict
    timing: Optional[TimingX] = None
    routing: Optional[RoutingX] = None
    twinlab_blocks: list[TwinLabBlock]
    integration_status: str = ("TwinLab has no importer yet (hard-coded blocks in twinlab-state.ts); this file is "
                               "the proposed import format. Integration NOT complete.")


GROUP_TYPE = {"cpu": "CPU_CORE", "vector": "VECTOR_UNIT", "tensor": "TENSOR_ARRAY", "fabric": "NOC_ROUTER",
              "dma": "MEM_CTRL", "sram_ctrl": "MEM_CTRL", "debug": "DFT_JTAG", "mbist": "DFT_JTAG",
              "reset": "POWER_MGMT"}
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def write_schema(path: Path) -> Path:
    path.write_text(json.dumps(FloorplanExport.model_json_schema(), indent=2) + "\n")
    return path


def build_export(run, geo: dict, lef) -> FloorplanExport:
    rec = run.rec
    pf, design = run.platform, run.design
    labels = {g.name: g.label for g in design.logical_groups}
    t = rec.get("metrics", {}).get("timing_preroute") or {}
    rm = rec.get("metrics", {}).get("route") or {}
    routing_layers = [Layer(name=l.name, direction=l.direction, pitch_um=l.pitch, width_um=l.width)
                      for l in lef.routing_layers()]
    macros = []
    for m in geo.get("macros", []):
        info = pf.macros.get(m["master"])
        lm = lef.macros.get(m["master"])
        from .geometry import FLIP_SIDE
        edge = FLIP_SIDE.get(m["orient"], {}).get(lm.pin_side_r0()) if lm else None
        macros.append(MacroX(name=m["name"].replace("\\", ""), master=m["master"], bbox_um=m["bbox"], orient=m["orient"],
                             status=m["status"], group="tspm" if "u_tile" in m["name"] else "main_sram",
                             words=info.words if info else None, bits=info.bits if info else None, signal_pin_edge=edge))
    groups = []
    for g, v in (geo.get("groups") or {}).items():
        if g in ("macro",):
            continue
        groups.append(GroupX(name=g, label=labels.get(g, g), cells=v["cells"], area_um2=float(v["area_um2"]),
                             centroid_um=v["centroid_um"], extent_um=v["bbox_um"]))
    pins = [PinX(name=p["name"], dir=p["dir"], layer=p["layer"], bbox_um=p["bbox"], edge=p["edge"]) for p in geo.get("io_pins", [])]
    cp = geo.get("clock_pin")
    clock_pin = PinX(name=cp["name"], dir=cp["dir"], layer=cp["layer"], bbox_um=cp["bbox"], edge=cp["edge"]) if cp else None
    stripes = [Stripe(net=s["net"], layer=s["layer"], shape=s["shape"], bbox_um=s["bbox"]) for s in geo.get("pdn_stripes", [])]
    pdn_chk = None
    f = run.out / "pdn_checks.json"
    if f.is_file():
        d = json.loads(f.read_text())
        pdn_chk = {"nets": [{k: n[k] for k in ("net", "connected", "result")} for n in d.get("nets", [])],
                   "macro_pg_errors": d.get("macro_pg_errors")}
    place = rec.get("metrics", {}).get("place") or rec.get("metrics", {}).get("floorplan") or {}
    blocks = []
    period = t.get("clock_period_ns") or run.period
    vdd = pf.power.get("supply_voltage")
    for i, m in enumerate(macros):
        b = m.bbox_um
        blocks.append(TwinLabBlock(id=f"macro_{i}", name=m.name, type="SRAM_BANK", x=b[0], y=b[1], width=b[2] - b[0],
                                   height=b[3] - b[1], color="#d9d8d3", cellCount=1, locked=True,
                                   voltageDomain=f"VDD ({vdd} V)", clockDomain=f"clk ({1000 / period:.1f} MHz target)",
                                   provenanceNote=f"OpenROAD macro {m.master} {m.orient} ({m.status})"))
    for j, g in enumerate(sorted(groups, key=lambda g: -g.area_um2)):
        if g.name == "top" or g.cells < 50:
            continue
        e = g.extent_um
        blocks.append(TwinLabBlock(id=f"group_{g.name}", name=g.label, type=GROUP_TYPE.get(g.name, "MEM_CTRL"),
                                   x=e[0], y=e[1], width=e[2] - e[0], height=e[3] - e[1],
                                   color=CATEGORICAL[j % len(CATEGORICAL)], cellCount=g.cells,
                                   voltageDomain=f"VDD ({vdd} V)", clockDomain=f"clk ({1000 / period:.1f} MHz target)",
                                   provenanceNote="ANNOTATION ONLY: bounding box of this logical group's placed cells "
                                                  "(cells of other groups interleave); not a physical block outline"))
    return FloorplanExport(
        provenance=Provenance(run_id=rec["run_id"], design=design.name, top=design.top, platform=pf.name,
                              process=pf.process, orfs_revision=(rec.get("tools") or {}).get("orfs"),
                              tools={k: str(v) for k, v in (rec.get("tools") or {}).items()},
                              netlist_sha256=rec.get("netlist_sha256"), source_odb=geo["source_odb"],
                              created=rec.get("updated", rec.get("created"))),
        technology=Technology(site=pf.place_site, row_height_um=pf.row_height_um, site_width_um=pf.site_width_um,
                              routing_layers=routing_layers,
                              signal_layer_range=[pf.routing.min_layer, pf.routing.max_layer],
                              supply_voltage_v=vdd, analysis_corner=pf.analysis_corner),
        die_um=geo["die_um"], core_um=geo["core_um"], macros=macros, std_cell_groups=groups,
        density_grid=DensityGrid(**geo["density_grid"]) if geo.get("density_grid") else None,
        io_pins=pins, clock_source_pin=clock_pin,
        power_grid=PowerGrid(stripes=stripes, followpin_rails=geo.get("pdn_followpin_rails", []), connectivity=pdn_chk),
        area={k: place.get(k) for k in ("die_area_mm2", "core_area_mm2", "std_cell_area_um2", "macro_area_um2",
                                        "std_cell_util_of_rows", "core_util_incl_macros")},
        timing=TimingX(label=t.get("label"), wns_ns=t.get("wns_ns"), tns_ns=t.get("tns_ns"), whs_ns=t.get("whs_ns"),
                       clock_period_ns=t.get("clock_period_ns"), critical_paths=t.get("critical_paths", [])) if t else None,
        routing=RoutingX(label=rm.get("label"), completed=bool(rm.get("completed")) if rm else None,
                         overflow_total=(rm.get("total") or {}).get("overflow_total"),
                         routed_wirelength_um=rm.get("routed_wirelength_um"), layers=rm.get("layers", {})) if rm else None,
        twinlab_blocks=blocks,
    )


def load_export(path: Path) -> FloorplanExport:
    """Round-trip validation used by tests and the standalone viewer contract."""
    return FloorplanExport.model_validate_json(Path(path).read_text())
