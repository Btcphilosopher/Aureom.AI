"""Hardware configuration objects and external-memory presets.

All peak numbers derived here are THEORETICAL ceilings (clock x width).
External-memory efficiency, latency, energy and PHY-area figures are
ANALYTICAL ASSUMPTIONS taken from public literature ranges; each preset
carries a ``source`` note and every one of them should be replaced by vendor
datasheet values before tape-out decisions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

from memoryflow.provenance import Provenance, Quantity


@dataclass(frozen=True)
class ComputeConfig:
    """Compute resources of one SilicaFlux variant."""

    clock_hz: float = 500e6
    cpu_cores: int = 1
    cpu_ops_per_cycle: float = 2.0         # scalar FMA = 2 ops
    vec_lanes: int = 4                     # int16 lanes (64-bit datapath)
    vec_ops_per_lane: float = 2.0          # MAC per lane per cycle
    tensor_rows: int = 8
    tensor_cols: int = 8
    tensor_ops_per_mac: float = 2.0
    tensor_in_bytes: int = 1               # int8 operands
    tensor_acc_bytes: int = 4              # int32 accumulators
    # Tensor dataflow.  "outer_product": MemoryFlow sf_tensor_array (TR x TC MACs
    # per cycle, accumulators held in the array, A streamed, B reused).
    # "block": the SilicaFlux 2.5 tensor_unit style - one DIM x DIM x DIM
    # product per cycle (tensor_depth = DIM), no accumulation buffer: partial C
    # tiles leave the unit and are accumulated elsewhere.
    tensor_dataflow: str = "outer_product"
    tensor_depth: int = 1                  # MACs per (row, col) per cycle
    # Bytes/cycle the tensor RESULT path can absorb (0 = unlimited).  SilicaFlux
    # 2.5: 16 (one 128-bit vector-register write port) - see tb_sf25_tensor.
    tensor_drain_bytes_per_cycle: float = 0.0
    vec_lane_bits: int = 16                # element width of one vector lane

    @property
    def tensor_macs_per_cycle(self) -> int:
        return self.tensor_rows * self.tensor_cols * self.tensor_depth

    def peak_ops(self, unit: str) -> Quantity:
        f = self.clock_hz
        if unit == "cpu":
            v = self.cpu_cores * self.cpu_ops_per_cycle * f
        elif unit == "vector":
            v = self.vec_lanes * self.vec_ops_per_lane * f
        elif unit == "tensor":
            v = self.tensor_macs_per_cycle * self.tensor_ops_per_mac * f
        else:
            raise ValueError(unit)
        return Quantity(v, "op/s", Provenance.THEORETICAL, f"{unit} peak = width x clock")

    @property
    def vec_datapath_bits(self) -> int:
        return self.vec_lanes * self.vec_lane_bits

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScratchpadConfig:
    capacity_bytes: int = 256 * 1024
    banks: int = 8
    bank_width_bits: int = 64
    ports: int = 3                         # DMA read, DMA write, CPU/host
    ecc: str = "secded"                    # none | parity | secded
    interleave: str = "xor"                # modulo | xor | block
    # measured fraction of the port's width x clock actually delivered to an
    # engine (1.0 for MemoryFlow's pipelined SPM; e.g. 0.57 for the SilicaFlux
    # v1 FSM controller, RTL_SIMULATION tb_sf1_memctrl)
    port_efficiency: float = 1.0

    @property
    def words_per_bank(self) -> int:
        return self.capacity_bytes // (self.banks * self.bank_width_bits // 8)

    def peak_bytes_per_cycle(self) -> float:
        """Aggregate bank bandwidth limited by the number of ports."""
        return min(self.banks, self.ports) * self.bank_width_bits / 8

    def stored_bits_per_word(self) -> int:
        w = self.bank_width_bits
        if self.ecc == "secded":
            r = 1
            while (1 << r) < w + r + 1:
                r += 1
            return w + r + 1
        if self.ecc == "parity":
            return w + w // 8
        return w

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DmaConfig:
    burst_beats: int = 16
    dfifo_depth: int = 16
    desc_depth: int = 4
    beat_bytes: int = 8
    channels: int = 4
    engines: int = 2                       # MM2S/MEM2MEM + S2MM
    wout: int = 8                          # outstanding write acknowledgements (sf_dma WOUT)


@dataclass(frozen=True)
class ExtMemConfig:
    """External DRAM interface (controller + PHY + devices)."""

    name: str
    kind: str
    data_rate_mtps: float                  # mega-transfers per second per pin
    bus_width_bits: int
    channels: int = 1
    efficiency: float = 0.70               # sustained / peak for streaming DMA
    latency_ns: float = 90.0               # idle read latency at the controller
    pj_per_bit: float = 15.0               # device + IO + PHY energy
    phy_area_mm2: float = 2.5              # PHY + controller hard IP (indicative)
    max_node_nm: int = 65                  # coarsest node with commonly available PHY IP
    source: str = ""

    def available_at(self, node_nm: int) -> bool:
        """Indicative PHY-IP availability rule (assumption, not a vendor survey)."""
        return node_nm <= self.max_node_nm

    @property
    def mature_node_ok(self) -> bool:
        return self.max_node_nm >= 40

    def peak_bw(self) -> Quantity:
        v = self.data_rate_mtps * 1e6 * self.bus_width_bits / 8 * self.channels
        return Quantity(v, "B/s", Provenance.THEORETICAL, f"{self.name} pin bandwidth")

    def sustained_bw(self) -> Quantity:
        v = self.peak_bw().value * self.efficiency
        return Quantity(v, "B/s", Provenance.ANALYTICAL,
                        f"{self.name} x efficiency {self.efficiency:.2f} (assumed)")

    def latency_cycles(self, clock_hz: float) -> float:
        return self.latency_ns * 1e-9 * clock_hz

    def to_dict(self) -> dict:
        return asdict(self)


_SRC_DRAM = ("indicative public-literature range (JEDEC rates; energy per O'Connor et al., "
             "MICRO 2017 and vendor briefs) -- replace with datasheet values")

_SRC_SERIAL = ("device rates from public QSPI-flash (104 MHz SDR) and HyperBus/HyperRAM (200 MHz DDR x8) "
               "datasheets; efficiency covers command/address/latency overhead; digital PHY (pads + DLL) "
               "so no analog DDR PHY is needed at mature nodes -- energy and area are indicative")

EXTMEM_PRESETS: dict[str, ExtMemConfig] = {m.name: m for m in [
    # mature-node, low-pin options (added v2: SilicaFlux-V targets 65 / 130 nm)
    ExtMemConfig("QSPI 104 MHz (no DRAM)", "QSPI", 104, 4, 1, 0.50, 400, 60.0, 0.02, 180, _SRC_SERIAL),
    ExtMemConfig("HyperRAM 200 MHz x8", "HyperRAM", 400, 8, 1, 0.60, 70, 20.0, 0.05, 180, _SRC_SERIAL),
    ExtMemConfig("2x HyperRAM 200 MHz x8", "HyperRAM", 400, 8, 2, 0.60, 70, 20.0, 0.10, 180, _SRC_SERIAL),
    ExtMemConfig("LPDDR2-800 x32", "LPDDR2", 800, 32, 1, 0.65, 100, 12.0, 2.2, 65, _SRC_DRAM),
    # v1 presets (unchanged)
    ExtMemConfig("DDR3-1600 x16", "DDR3", 1600, 16, 1, 0.65, 95, 25.0, 1.8, 130, _SRC_DRAM),
    ExtMemConfig("DDR4-2400 x16", "DDR4", 2400, 16, 1, 0.70, 90, 15.0, 2.0, 55, _SRC_DRAM),
    ExtMemConfig("DDR4-3200 x32", "DDR4", 3200, 32, 1, 0.70, 90, 15.0, 3.2, 40, _SRC_DRAM),
    ExtMemConfig("LPDDR4X-4266 x32", "LPDDR4X", 4266, 32, 1, 0.70, 110, 5.5, 2.8, 28, _SRC_DRAM),
    ExtMemConfig("LPDDR5-6400 x32", "LPDDR5", 6400, 32, 1, 0.70, 110, 4.5, 3.0, 16, _SRC_DRAM),
    # multi-channel options for the full SilicaFlux (PHY area scales per channel)
    ExtMemConfig("LPDDR4X-4266 2x32", "LPDDR4X", 4266, 32, 2, 0.70, 110, 5.5, 5.6, 28, _SRC_DRAM),
    ExtMemConfig("LPDDR5-6400 2x32", "LPDDR5", 6400, 32, 2, 0.70, 110, 4.5, 6.0, 16, _SRC_DRAM),
    ExtMemConfig("LPDDR5-6400 4x32", "LPDDR5", 6400, 32, 4, 0.70, 110, 4.5, 12.0, 16, _SRC_DRAM),
    ExtMemConfig("HBM2E 1 stack", "HBM2E", 3200, 1024, 1, 0.80, 100, 3.9, 15.0, 16, _SRC_DRAM),
    ExtMemConfig("HBM3 1 stack", "HBM3", 6400, 1024, 1, 0.80, 100, 3.0, 18.0, 7, _SRC_DRAM),
]}


@dataclass(frozen=True)
class SystemConfig:
    """One complete design point."""

    compute: ComputeConfig = field(default_factory=ComputeConfig)
    spm: ScratchpadConfig = field(default_factory=ScratchpadConfig)
    dma: DmaConfig = field(default_factory=DmaConfig)
    extmem: ExtMemConfig = field(default_factory=lambda: EXTMEM_PRESETS["DDR4-3200 x32"])
    node_nm: int = 40
    name: str = "SilicaFlux-V"
    # Replicated compute tiles (tensor + vector + SPM + DMA each) sharing ONE
    # external-memory interface.  1 = SilicaFlux-V; the full SilicaFlux cluster
    # (silicaflux_top.sf: 2 complexes x 4 cores) is modelled with tiles = 4..16.
    tiles: int = 1

    def with_(self, **kw) -> "SystemConfig":
        return replace(self, **kw)

    def spm_to_accel_bw(self) -> Quantity:
        """On-chip operand path: one DMA read beat (bank width) per cycle per tile."""
        v = self.spm.bank_width_bits / 8 * self.compute.clock_hz * self.tiles * self.spm.port_efficiency
        return Quantity(v, "B/s", Provenance.THEORETICAL, "DMA engine 0 read path, 1 beat/cycle")

    def spm_peak_bw(self) -> Quantity:
        v = self.spm.peak_bytes_per_cycle() * self.compute.clock_hz * self.tiles
        return Quantity(v, "B/s", Provenance.THEORETICAL, "min(banks, ports) x width x clock")

    def label(self) -> str:
        c, s = self.compute, self.spm
        return ((f"{self.tiles}x " if self.tiles > 1 else "") + f"{s.capacity_bytes // 1024}KiB/{s.banks}b/{s.bank_width_bits}w "
                f"T{c.tensor_rows}x{c.tensor_cols}{'x%d' % c.tensor_depth if c.tensor_depth > 1 else ''} "
                f"V{c.vec_lanes} "
                f"B{self.dma.burst_beats}/F{self.dma.dfifo_depth} {self.extmem.name}")
