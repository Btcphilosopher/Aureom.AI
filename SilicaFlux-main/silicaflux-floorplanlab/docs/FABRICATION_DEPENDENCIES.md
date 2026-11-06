# Unresolved fabrication dependencies

Passing every FloorplanLab gate means *the preliminary floorplan is self-consistent on an open PDK*.
It does **not** mean fabrication readiness. This list is what stands between the current results
and a tape-out.

## A. Before clock-tree synthesis and detailed routing (next engineering steps)

| # | Item | Why / evidence |
|---|---|---|
| A1 | Pick the floorplan to carry forward on measured data (docs/RESULTS.md); re-run it with the final clock/I-O constraints | the automatic baseline is congested (GRT overflow) |
| A2 | Resolve global-route overflow to 0 on the chosen floorplan (macro channels, pin-edge orientation, Metal5 track supply: `make_tracks` gives Metal5 a 3.48 µm x-pitch) | GATE 12 warnings; `GRT-0026` missing routes to tie/macro pins |
| A3 | Fix the remaining DRV violators (max fanout 16 vs 8 on SRAM bit-mask drivers, ≈0.01 ns max-slew on TSPM `A_DIN`) | `place_drv.rpt` |
| A4 | Hold: pre-CTS WHS ≈ −0.35 ns (MBIST → SRAM inputs) — must be repaired after CTS (`repair_timing -hold`) | `place_timing_hold.rpt` |
| A5 | Clock tree: `clk` drives ~2.9 k sinks + 2 ICGs (`u_tile/u_cg_ve/te`); balanced reset tree for `sys_rst_n` (~2.4 k sinks) | OpenDB high-fanout nets; release-1 ISS-006 |
| A6 | Multi-corner STA: SG13G2 slow/fast **std-cell** Liberty are not in ORFS ab2aaf0f (SRAM slow/fast exist) | GATE 4 warnings |
| A7 | SRAM power model: vectorless STA power attributes 0 W to the macros although their Liberty has leakage/internal power → resolve before any power/IR claim | `power_vectorless.notes` |
| A8 | Static IR drop: needs real supply-source locations (pads/bumps) — none exist for the pad-less core | not run |
| A9 | Newer OpenROAD/ORFS: the installable OpenROAD (Feb 2024) crashed in multi-threaded STA during GRT and lacks Hier-RTLMP; move to a current ORFS + OpenROAD when a binary/container is available | ORFS_INTEGRATION.md |

## B. Downstream implementation and signoff

CTS (clock + reset trees, ICG-aware), detailed routing (TritonRoute) with antenna repair, RC
extraction (OpenRCX rules exist for SG13G2), signoff STA across PVT corners with SI, hold closure,
gate-level simulation of the firmware regression, filler/decap insertion, metal fill, DRC/LVS
(KLayout decks present but not run; SRAM CDL in ORFS d0e5b3c), EM, dynamic IR drop, DFT
(scan insertion — release 1 has JTAG/MBIST/test mode only), formal equivalence netlist vs RTL.

## C. Chip-level physical integration (not modelled: logical core pins only)

* Foundry I/O pad cells (IHP `sg13g2_io` exists in later ORFS revisions, not in ab2aaf0f), ESD
  structures, separate I/O supply domain.
* Power and ground pads (count from current estimate and package), pad-ring PDN connection.
* Seal ring, scribe boundary, corner cells, die-size rules of the shuttle/MPW.
* Bond-wire or flip-chip bump plan, package selection, signal/power assignment.
* A top-level `sfv_chip` wrapper (pads + `sfv_soc_df`) — does not exist in the repository.

## D. What prevents a commercial 130 nm or 65 nm implementation

| Missing | Effect |
|---|---|
| Foundry PDK under NDA: tech LEF, std-cell LEF/Liberty (tt/ss/ff), RC tables / RCX rules, DRC/LVS/antenna decks | `platforms/commercial_{130,65}` are templates; validation fails (`UNFILLED_TEMPLATE`, `PLATFORM_NOT_ENABLED`) |
| SRAM compiler outputs (4 × 8192×32 + 4 × 1024×32 single-port with byte enables, or equivalent) | no macro abstracts / timing |
| SilicaFlux-V technology wrappers for that foundry (`sfv_clkgate.sv`, `sfv_sram_macro_bank.sv`) | design cannot be elaborated for the node |
| ORFS platform directory for the node (config.mk, PDN, tapcell/endcap rules, tracks) | ORFS cannot run |
| Foundry I/O library, ESD rules, packaging | no chip top |
| Signoff tools and decks accepted by the foundry | no tape-out acceptance |

FloorplanLab contains **no** scaling of 130 nm results to 65/28 nm; such numbers are not produced.

## E. Design-level open items

* `sfv_soc_df` cannot use the SRAM Wrapper Library on silicon (`SRAM_IMPL=1` lacks
  `BACKEND`/`MACRO` forwarding) — a one-line RTL change in DataFabric would enable it.
* No MCU-I RTL exists; no larger SilicaFlux top with SRAM macros exists.
* TwinLab cannot import results (no importer).
