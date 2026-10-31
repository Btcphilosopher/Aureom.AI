# SilicaFlux
## A Modular Dataflow-Oriented Semiconductor Compute Architecture

> **Dataflow fabric · 32-bit ISA · SIMD vector engine · 4×4 tensor unit · 2×2 NoC mesh · Chiplet-ready**

SilicaFlux is a semiconductor-grade, synthesisable SystemVerilog compute architecture designed for AI inference, signal processing, and parallel numerical workloads. It combines ARM-style energy efficiency with GPU-style throughput and modern AI accelerator dataflow principles.

---

## Architecture Overview

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                    SilicaFlux Cluster (Single Die)                  │
  │                                                                     │
  │  ┌──────────┐   ┌──────────┐   ┌─────────────────────────────────┐ │
  │  │  Fetch   │→  │ Decoder  │→  │         Control Core            │ │
  │  │  Unit    │   │          │   │  (Scalar ALU + Forwarding + WB)  │ │
  │  └──────────┘   └──────────┘   └────────────────┬────────────────┘ │
  │                                                  │ DF/Vec tokens    │
  │                                ┌─────────────────▼──────────────┐  │
  │                                │       Dataflow Scheduler        │  │
  │                                │  (scoreboard + DFSYNC barrier)  │  │
  │                                └──┬──────┬──────┬──────┬────────┘  │
  │                                   │      │      │      │           │
  │  ┌────────────┐  ┌────────────┐  ┌┴───────┐  ┌─┴──────┐           │
  │  │   Tile 0   │  │   Tile 1   │  │ Tile 2 │  │ Tile 3 │           │
  │  │ Vec + Mat  │  │ Vec + Mat  │  │Vec+Mat │  │Vec+Mat │           │
  │  │ SRAM 1KB   │  │ SRAM 1KB   │  │SRAM 1KB│  │SRAM 1KB│           │
  │  └─────┬──────┘  └─────┬──────┘  └───┬────┘  └────┬───┘           │
  │        └───────────────┴──── NoC ────┴─────────────┘               │
  │                           (2×2 mesh, XY routing)                   │
  │                                                                     │
  │  ┌────────────────────────────────────────────────────────────────┐ │
  │  │          Register Bank: 32×32b scalar  +  16×128b vector       │ │
  │  └────────────────────────────────────────────────────────────────┘ │
  │                                                                     │
  │  ── Chiplet boundary ──── tile_interface ──── PHY link 8/16/32b ── │
  └─────────────────────────────────────────────────────────────────────┘
```

---

## Repository Layout

```
silicaflux/
│
├── rtl/                       SystemVerilog RTL (fully synthesisable)
│   ├── silicaflux_pkg.sv      Package: types, opcodes, pipeline structs
│   ├── silicaflux_top.sv      Top-level cluster integration
│   ├── fetch_unit.sv          PC + instruction SRAM + branch redirect
│   ├── decoder.sv             32-bit 4-format instruction decode
│   ├── alu.sv                 Scalar ALU (ADD/SUB/MUL/AND/OR/XOR/SHL/SHR/SAR/SLT)
│   ├── forwarding_unit.sv     RAW hazard detection + EX/MEM bypass paths
│   ├── control_core.sv        Scalar pipeline (IS→EX→MEM→WB) + DF dispatch
│   ├── register_bank.sv       32×32b scalar + 16×128b vector registers
│   ├── vector_engine.sv       Parameterised SIMD ALU (4/8/16 lanes)
│   ├── tensor_unit.sv         4×4 signed integer MATMUL (~20 cycle latency)
│   ├── memory_controller.sv   Scratchpad SRAM: scalar + vector + burst access
│   ├── scheduler.sv           Dataflow token dispatch + DFSYNC barrier
│   ├── compute_tile.sv        Tile wrapper: vec engine + tensor + SRAM
│   ├── noc_interconnect.sv    2×2 XY-routed mesh NoC
│   └── tile_interface.sv      Chiplet boundary serialiser + 2-FF retimer
│
├── tb/                        SystemVerilog testbenches
│   ├── tb_vector_engine.sv    VADD/VSUB/VMUL/DOT/REDUCE/BROADCAST
│   ├── tb_tensor_unit.sv      4×4 MATMUL correctness (identity, diagonal)
│   ├── tb_memory_controller.sv Scalar/vector/burst/misaligned access
│   ├── tb_compute_tile.sv     Token injection: VADD/DOT/REDUCE/BCAST/MATMUL
│   ├── tb_scheduler.sv        Dispatch, scoreboard, DFSYNC barrier
│   ├── tb_noc_interconnect.sv Local/1-hop/diagonal/bidirectional routing
│   └── tb_silicaflux_top.sv   Full-system scalar and branch tests
│
├── sim/
│   ├── run_sim.sh             Icarus Verilog simulation runner (all targets)
│   ├── sfx_asm.py             SilicaFlux assembler → .hex/.bin/.mif/.coe
│   └── programs/
│       ├── fibonacci.sfx      Scalar Fibonacci sequence
│       ├── dot_product_parallel.sfx  Parallel 16-element dot product
│       ├── matmul_4x4.sfx     4×4 matrix multiply via dataflow
│       └── softmax_inference.sfx     Approximate softmax kernel
│
├── synth/
│   ├── silicaflux.sdc         Shared SDC timing constraints (100 MHz)
│   ├── vivado/
│   │   ├── synth.tcl          Xilinx Vivado synthesis (Arty A7-100T)
│   │   └── silicaflux_arty.xdc  Pin + timing constraints
│   └── quartus/
│       └── synth.tcl          Intel Quartus synthesis (DE10-Nano Cyclone V)
│
└── docs/
    └── ISA_REFERENCE.md       Full ISA encoding, opcode table, assembly examples
```

---

## ISA Quick Reference

**32-bit fixed-width encoding. 4 formats determined entirely by opcode.**

| Format | Layout | Used by |
|--------|--------|---------|
| **R** | `[31:27]=op [26:22]=rd [21:17]=rs1 [16:12]=rs2 [11:0]=func` | ADD, SUB, MUL |
| **I** | `[31:27]=op [26:22]=rd [21:17]=rs1 [16:0]=imm17` | LOAD, STORE, MOV, BEQ, BNE, JMP |
| **D** | `[31:27]=op [26:24]=tile [23:19]=reg [18:14]=len [13:0]=addr` | DFLOAD, DFSTORE, DFEXEC, DFSYNC |
| **V** | `[31:27]=op [26:23]=vrd [22:19]=vrs1 [18:15]=vrs2 [7:0]=func` | VADD, VMUL, DOT, MATMUL, REDUCE |

**Scalar registers:** r0 (hardwired zero) … r31  
**Vector registers:** v0 … v15 (128-bit, 4×32-bit lanes)

See `docs/ISA_REFERENCE.md` for the full opcode table and assembly examples.

---

## Pipeline

```
  IF → ID → IS → EX → MEM → WB

  IF  — Synchronous instruction SRAM read, PC management
  ID  — 4-format decode, register file read
  IS  — Forwarded operand select, hazard check, scheduler dispatch
  EX  — Scalar ALU, branch resolution, DF token issue
  MEM — SRAM LOAD/STORE
  WB  — Register file writeback (scalar + scheduler results)
```

**Hazard handling:**
- RAW (load-use): 1-cycle stall inserted by `forwarding_unit`
- Control hazard: 1-cycle flush on taken branch
- DFSYNC barrier: scalar pipeline stalls until all tiles report idle

---

## Simulation

### Requirements
- **Icarus Verilog** 11.0+ (`iverilog`, `vvp`)
- Optional: **GTKWave** for waveform viewing

```bash
# Install (Ubuntu/Debian)
sudo apt install iverilog gtkwave

# Install (macOS)
brew install icarus-verilog gtkwave
```

### Run All Testbenches
```bash
cd silicaflux/sim
chmod +x run_sim.sh
./run_sim.sh
```

### Run Specific Testbenches
```bash
./run_sim.sh vec              # Vector engine only
./run_sim.sh tensor mem       # Tensor unit + memory controller
./run_sim.sh tile sched noc   # Tile, scheduler, NoC
./run_sim.sh top              # Full system
```

### View Waveforms
```bash
gtkwave sim/build/tb_vector_engine.vcd
gtkwave sim/build/tb_noc_interconnect.vcd
```

---

## Assembler

```bash
cd silicaflux/sim

# Assemble to all formats
python3 sfx_asm.py programs/fibonacci.sfx -o out/fibonacci

# With listing output
python3 sfx_asm.py programs/matmul_4x4.sfx --list -o out/matmul

# Specific output format
python3 sfx_asm.py programs/dot_product_parallel.sfx \
    --format coe -o out/dot_product   # Vivado .coe
    --format mif -o out/dot_product   # Quartus .mif
```

**Generated files:**
| Extension | Use |
|-----------|-----|
| `.hex` | One word per line; loaded by testbench `imem_wr_*` port |
| `.bin` | Raw little-endian 32-bit binary |
| `.mif` | Intel Quartus BRAM initialisation |
| `.coe` | Xilinx Vivado BRAM initialisation |

---

## FPGA Synthesis

### Xilinx Vivado — Digilent Arty A7-100T

```bash
cd silicaflux/synth/vivado
vivado -mode batch -source synth.tcl
# Bitstream: build/silicaflux/silicaflux.runs/impl_1/silicaflux_top.bit
```

### Intel Quartus — DE10-Nano (Cyclone V)

```bash
cd silicaflux/synth/quartus
quartus_sh -t synth.tcl
# SOF: build/silicaflux.sof
```

**Expected resource utilisation (Artix-7, LANES=4, 4 tiles):**

| Resource | Estimate |
|----------|----------|
| LUTs | ~8,000–12,000 |
| FFs | ~6,000–9,000 |
| BRAM (36K) | 8 (1 per SRAM) |
| DSP48 | 16–24 (multipliers) |
| Fmax (est.) | 80–110 MHz |

---

## Execution Model Summary

### Scalar Path
Instructions execute in-order through the 6-stage pipeline. Forwarding covers
EX→IS and MEM→IS. Load-use hazards insert a 1-cycle bubble automatically.

### Dataflow Path
1. DFLOAD/DFSTORE/DFEXEC/VADD/DOT/MATMUL instructions are detected in EX
2. Scheduler assigns a **work token** to the target tile (if idle)
3. Tile executes asynchronously (vector engine: 2-cycle; tensor: ~20-cycle)
4. Completion raises `tile_status.done`; scalar results written to register file
5. DFSYNC stalls the scalar pipeline until the tile scoreboard clears

### Chiplet Scaling
Each SilicaFlux cluster exposes boundary NoC ports through `tile_interface`,
which serialises 43-bit flits to an 8/16/32-bit physical link. Multiple dies
tile into a larger mesh using the same XY routing — no protocol changes needed.

---

## Extending SilicaFlux

### Increasing SIMD Width
Change the `LANES` parameter at instantiation:
```systemverilog
silicaflux_top #(.LANES(8)) u_cluster ( ... );
```
The vector engine, compute tile, and pack/unpack logic all adapt via `generate`.

### Adding More Tiles
1. Update `NUM_TILES` and `NOC_ROWS`/`NOC_COLS` in `silicaflux_pkg.sv`
2. The NoC mesh scales automatically via its `ROWS`/`COLS` generate loops

### Adding Floating-Point
Replace the integer `MUL` in `vector_engine.sv` lane logic with an
IEEE-754 single-precision FMA unit. The pipeline latency parameter on
`compute_tile` accommodates longer FP latencies via configurable
`TILE_EXEC_LATENCY` (add to pkg and propagate).

### Custom Dataflow Kernels
Reserve opcodes `0x18`–`0x1E` in `silicaflux_pkg.sv` for application-specific
kernels. Wire them through the scheduler's opcode dispatch and add the
corresponding functional unit to `compute_tile`.

---

## Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Determinism** | No speculation, no OOO, XY routing |
| **Modularity** | Each module has a single responsibility; pkg-isolated types |
| **Synthesisability** | No `#delay`, no `initial` in RTL, BRAM-inferrable SRAM |
| **Scalability** | All critical structures parameterised; chiplet interface abstracted |
| **Performance-per-watt** | SIMD amortises control overhead; tiles gate-off when idle |

---

*SilicaFlux v1.0 — Semiconductor Architecture RTL*
