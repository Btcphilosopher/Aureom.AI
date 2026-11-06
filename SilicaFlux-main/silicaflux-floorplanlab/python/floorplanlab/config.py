"""Configuration model: platform profiles, design description, run/experiment specs.

YAML files are loaded with ``${VAR}`` expansion (variables from env/tools.env,
the process environment and PROJECT).  Experiment files may ``extends:`` a base
file; mappings are deep-merged, lists replaced.
"""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PROJECT = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    """Raised for invalid / conflicting configuration (reported, never ignored)."""


# --------------------------------------------------------------------------- variables
def tool_env() -> dict[str, str]:
    env: dict[str, str] = {}
    f = PROJECT / "env" / "tools.env"
    if f.is_file():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in list(env):
        if k in os.environ:
            env[k] = os.environ[k]
    for k in ("FOUNDRY_KIT",):
        if k in os.environ:
            env[k] = os.environ[k]
    env["PROJECT"] = str(PROJECT)
    return env


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
UNSET = "<UNSET:{}>"


def expand_text(text: str, env: dict[str, str]) -> str:
    """Substitute ${VAR}; unknown variables become an explicit <UNSET:VAR> marker
    that path validation reports (never silently empty)."""
    return _VAR.sub(lambda m: env.get(m.group(1), UNSET.format(m.group(1))), text)


def expand(obj: Any, env: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return expand_text(obj, env)
    if isinstance(obj, list):
        return [expand(x, env) for x in obj]
    if isinstance(obj, dict):
        return {k: expand(v, env) for k, v in obj.items()}
    return obj


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_yaml(path: Path, env: dict[str, str] | None = None, _seen=None) -> dict:
    path = Path(path).resolve()
    _seen = _seen or set()
    if path in _seen:
        raise ConfigError(f"circular 'extends' at {path}")
    _seen.add(path)
    if not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")
    data = yaml.safe_load(expand_text(path.read_text(), env if env is not None else tool_env())) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    if "extends" in data:
        base = load_yaml((path.parent / data.pop("extends")).resolve(), None, _seen)
        data = deep_merge(base, data)
    return data


# --------------------------------------------------------------------------- platform
class Corner(BaseModel):
    model_config = ConfigDict(extra="allow")
    liberty: list[str]
    voltage: float | None = None
    temperature_c: float | None = None
    process: str | None = None


class MacroLib(BaseModel):
    model_config = ConfigDict(extra="allow")
    lef: str
    liberty: dict[str, str] = Field(default_factory=dict)
    gds: str | None = None
    verilog: str | None = None
    words: int | None = None
    bits: int | None = None
    ports: str | None = None


class Routing(BaseModel):
    model_config = ConfigDict(extra="allow")
    min_layer: str
    max_layer: str
    io_h_layer: str
    io_v_layer: str
    fastroute_tcl: str | None = None
    make_tracks_tcl: str | None = None
    pdn_layers: list[str] = Field(default_factory=list)


class Tapcell(BaseModel):
    model_config = ConfigDict(extra="allow")
    method: str
    script: str | None = None
    tapcell_master: str | None = None
    endcap_master: str | None = None
    distance_um: Any = None
    note: str = ""


class PlatformProfile(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    status: Literal["enabled", "disabled", "template"]
    orfs_platform: str
    process: str = ""
    disabled_reason: str = ""
    tech_lef: str = ""
    sc_lefs: list[str] = Field(default_factory=list)
    sc_gds: list[str] = Field(default_factory=list)
    corners: dict[str, Corner] = Field(default_factory=dict)
    missing_corners: list[dict] = Field(default_factory=list)
    analysis_corner: str = "typ"
    place_site: str = ""
    row_height_um: float | None = None
    site_width_um: float | None = None
    routing: Routing | None = None
    rc: dict = Field(default_factory=dict)
    tapcell: Tapcell | None = None
    tie_cells: dict = Field(default_factory=dict)
    fill_cells: list[str] = Field(default_factory=list)
    dont_use: list[str] = Field(default_factory=list)
    power: dict = Field(default_factory=dict)
    pdn: dict = Field(default_factory=dict)
    macro_pg_pins: dict[str, str] = Field(default_factory=dict)
    macro_pg_assumption: str = ""
    macro_allowed_orients: list[str] = Field(default_factory=lambda: ["R0", "MX", "MY", "R180"])
    macros: dict[str, MacroLib] = Field(default_factory=dict)
    rtl_tech_files: dict[str, str] = Field(default_factory=dict)
    physical_verification: dict = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)

    def liberty_files(self, corner: str | None = None) -> list[str]:
        c = self.corners.get(corner or self.analysis_corner)
        return list(c.liberty) if c else []

    def macro_liberty(self, corner: str | None = None) -> dict[str, str]:
        corner = corner or self.analysis_corner
        return {m: lib.liberty[corner] for m, lib in self.macros.items() if corner in lib.liberty}


def load_platform(name: str) -> PlatformProfile:
    path = PROJECT / "platforms" / name / "profile.yaml"
    if not path.is_file():
        known = sorted(p.name for p in (PROJECT / "platforms").iterdir() if (p / "profile.yaml").is_file())
        raise ConfigError(f"unknown platform '{name}' (known: {', '.join(known)})")
    return PlatformProfile(**load_yaml(path, tool_env()))


# --------------------------------------------------------------------------- design
class LogicalGroup(BaseModel):
    name: str
    label: str
    match: list[str]


class Clock(BaseModel):
    name: str
    port: str
    period_ns: float = Field(gt=0)
    secondary: list[dict] = Field(default_factory=list)


class IoGroup(BaseModel):
    name: str
    edge: Literal["left", "right", "top", "bottom"]
    pins: list[str]
    note: str = ""


class IoPlan(BaseModel):
    groups: list[IoGroup] = Field(default_factory=list)


class Rtl(BaseModel):
    files: list[str]
    include_dirs: list[str] = Field(default_factory=list)
    defines: list[str] = Field(default_factory=list)
    top_params: dict[str, Any] = Field(default_factory=dict)


class DesignConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    description: str = ""
    top: str
    rtl: Rtl
    clock: Clock
    sdc_template: str
    allowed_blackboxes: list[str] = Field(default_factory=list)
    expected_macros: dict[str, dict[str, int]] = Field(default_factory=dict)
    logical_groups: list[LogicalGroup] = Field(default_factory=list)
    macro_groups: dict[str, str] = Field(default_factory=dict)
    io_plan: IoPlan = Field(default_factory=IoPlan)

    def resolved_files(self, platform: PlatformProfile) -> list[Path]:
        out = []
        for f in self.rtl.files:
            if f.startswith("@tech:"):
                key = f.split(":", 1)[1]
                if key not in platform.rtl_tech_files:
                    raise ConfigError(f"platform {platform.name} provides no technology file for '{key}'")
                out.append(Path(platform.rtl_tech_files[key]))
            else:
                out.append(PROJECT / f)
        return out


def load_design(name: str) -> DesignConfig:
    path = PROJECT / "configs" / name / "design.yaml"
    if not path.is_file():
        raise ConfigError(f"design '{name}' has no configs/{name}/design.yaml")
    data = load_yaml(path, tool_env())
    if data.get("status") == "not_available":
        raise ConfigError(f"design '{name}' is not available: {data.get('reason', 'see its design.yaml')}")
    return DesignConfig(**data)


# --------------------------------------------------------------------------- run spec
class FloorplanSpec(BaseModel):
    """MODE A: explicit die/core rectangles.  MODE B: derived from mapped area.

    The two modes are mutually exclusive; mixing their keys is an error so that
    OpenROAD's initialize_floorplan never receives conflicting sizing methods.
    """
    model_config = ConfigDict(extra="forbid")
    mode: Literal["A", "B"]
    die_area: list[float] | None = None
    core_area: list[float] | None = None
    target_util: float | None = None          # std-cell utilisation of the std-cell region
    aspect_ratio: float | None = None         # core height / width
    core_margin_um: float | None = None       # die edge -> core edge (PDN ring + pin keep-out)
    logic_growth: float = 1.15                # allowance for repair_design buffering/resizing
    corridor_um: float = 0.0                  # extra routing corridor around the macro arrangement
    pdn_overhead: float = 0.0                 # fraction of core area reserved for PDN strap blockage

    @model_validator(mode="after")
    def _exclusive(self):
        a_keys = [k for k in ("die_area", "core_area") if getattr(self, k) is not None]
        b_keys = [k for k in ("target_util", "aspect_ratio") if getattr(self, k) is not None]
        if self.mode == "A":
            if b_keys:
                raise ValueError(f"MODE A (explicit die/core) conflicts with MODE B keys {b_keys}")
            if len(a_keys) != 2:
                raise ValueError("MODE A requires both die_area and core_area")
            for k in ("die_area", "core_area"):
                v = getattr(self, k)
                if len(v) != 4 or v[2] <= v[0] or v[3] <= v[1]:
                    raise ValueError(f"{k} must be [llx, lly, urx, ury] with ur > ll, got {v}")
        else:
            if a_keys:
                raise ValueError(f"MODE B (automatic sizing) conflicts with MODE A keys {a_keys}")
            if self.target_util is None or not (0.05 < self.target_util < 0.95):
                raise ValueError("MODE B requires 0.05 < target_util < 0.95")
            if self.aspect_ratio is None or not (0.2 <= self.aspect_ratio <= 5.0):
                raise ValueError("MODE B requires 0.2 <= aspect_ratio <= 5")
            if self.core_margin_um is None or self.core_margin_um < 0:
                raise ValueError("MODE B requires core_margin_um >= 0")
        if not (1.0 <= self.logic_growth <= 3.0):
            raise ValueError("logic_growth must be within [1, 3]")
        if not (0 <= self.pdn_overhead < 0.5):
            raise ValueError("pdn_overhead must be within [0, 0.5)")
        return self


class MacroSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["physical", "logic_only", "mock"] = "physical"
    placement: Literal["auto", "manual"] = "auto"
    arrangement: str | None = None            # manual: named arrangement (arrangements.py)
    positions: dict[str, list] | None = None  # manual: explicit {inst: [x, y, orient]}
    halo_um: float = 20.0
    channel_um: float = 40.0
    auto_style: Literal["corner_max_wl", "corner_min_wl"] = "corner_max_wl"

    @model_validator(mode="after")
    def _check(self):
        if self.placement == "manual" and not (self.arrangement or self.positions):
            raise ValueError("manual macro placement needs an 'arrangement' or explicit 'positions'")
        if self.placement == "auto" and (self.arrangement or self.positions):
            raise ValueError("automatic macro placement must not also specify arrangement/positions")
        if self.halo_um < 0 or self.channel_um < 0:
            raise ValueError("halo/channel must be >= 0")
        return self


class PinSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["plan", "auto"] = "plan"     # plan: design io_plan edge constraints
    min_distance_tracks: int = 2
    corner_avoidance_um: float = 50.0
    edge_overrides: dict[str, str] = Field(default_factory=dict)   # group -> edge


class PdnSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    params: dict[str, Any] = Field(default_factory=dict)          # overrides of profile pdn.params
    check_power_grid: bool = True
    ir_drop: bool = True


class PlaceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    density: float | None = Field(None, gt=0.05, le=1.0)     # fixed PLACE_DENSITY, or
    density_lb_addon: float | None = Field(0.20, ge=0.0, lt=1.0)  # ORFS: lb + addon x (1 - lb) + 0.01
    timing_driven: bool = True
    routability_driven: bool = True
    pad_global: int = 2
    pad_detail: int = 1


    @model_validator(mode="after")
    def _one(self):
        if (self.density is None) == (self.density_lb_addon is None):
            raise ValueError("place: set exactly one of density / density_lb_addon")
        return self


class RouteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    congestion_iterations: int = 50          # ORFS default is 30; 50 gives FastRoute more overflow-removal effort
    allow_congestion: bool = True     # finish GRT to *measure* overflow; overflow is reported, not hidden


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str = ""
    design: str
    platform: str
    seed: int = 1
    clock_period_ns: float | None = None      # None = design default
    floorplan: FloorplanSpec
    macros: MacroSpec = Field(default_factory=MacroSpec)
    pins: PinSpec = Field(default_factory=PinSpec)
    pdn: PdnSpec = Field(default_factory=PdnSpec)
    place: PlaceSpec = Field(default_factory=PlaceSpec)
    route_estimate: RouteSpec = Field(default_factory=RouteSpec)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids(self):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.id):
            raise ValueError(f"run id '{self.id}' must match [A-Za-z0-9_.-]+")
        return self


def load_run(path: str | Path, overrides: dict | None = None) -> RunSpec:
    data = load_yaml(Path(path), tool_env())
    if overrides:
        data = deep_merge(data, overrides)
    try:
        return RunSpec(**data)
    except Exception as e:  # pydantic.ValidationError -> uniform error type
        raise ConfigError(f"{path}: {e}") from e
