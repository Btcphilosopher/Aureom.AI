# Using `nand_flash_model.sv` in a storage-controller testbench

## 1. Instantiate one model per chip enable

```systemverilog
nand_flash_model #(
  .PAGE_DATA_BYTES(512), .PAGE_SPARE_BYTES(16), .PAGES_PER_BLOCK(16),
  .BLOCKS_PER_PLANE(32), .PLANES_PER_LUN(2), .LUNS(2),
  .TARGET_ID(0),          // selects <dir>/target0.nlsf and target0.trace
  .POOL_PAGES(0)          // 0 = room for every page; set lower for large geometries
) u_nand0 (
  .ce_n(ce_n[0]), .cle(cle), .ale(ale), .we_n(we_n), .re_n(re_n), .wp_n(wp_n),
  .dq_in(dq_from_ctrl), .dq_out(dq_to_ctrl), .dq_oe(dq_oe0),
  .rb_n(rb_n0), .vcc_ok(vcc_ok));
```

* Use `nand_flash_device` (same parameters) when the controller has a bidirectional `inout`
  DQ bus. Several devices can share one channel; only the target whose CE# is low drives DQ,
  and it releases the bus about 15 ns after RE# rises. R/B# outputs are push-pull in the
  model; AND them to model an open-drain line with pull-up (`tb/tb_nand_channel.sv`).
* With a shared R/B#, per-target readiness must come from READ STATUS (70h/78h) polling.
* Geometry parameters must match the configuration. Generate them with
  `python3 nand_flash_twin.py export-sv --config config/slc_tiny.json --out <dir>`
  (`nandlab_geom.svh` with `` `define``s, plus the runtime file `nandlab.svcfg`).
* The sparse page pool means memory grows with programmed pages, not device size. For the
  1 Gbit-class configuration set `POOL_PAGES` to the number of pages your test programs.

## 2. Point the model at a store directory

| Plusarg | Effect |
|---|---|
| `+NANDLAB_DIR=<dir>` | `<dir>/nandlab.svcfg` (configuration), `<dir>/target<ID>.nlsf` (store, created if absent), `<dir>/target<ID>.trace` (operation trace) |
| `+NANDLAB_BAKE_HOURS=<h> +NANDLAB_BAKE_TEMP_C=<c>` | unpowered time before this power-on (retention) |
| `+NANDLAB_NOTRACE` | disable the trace file |
| `+NANDLAB_QUIET` | suppress informational messages (protocol and timing errors still print) |

Without `nandlab.svcfg` the model uses built-in defaults equal to the Python `nominal`
profile. The fault profile, seed, policies, timing values and directed faults are runtime
settings: change them without recompiling.

## 3. Power-on, reset and power loss

* At simulation start the device is powered and **requires RESET (FFh)** before any other
  command except READ STATUS (configurable: `policy.require_reset_after_power_on`). The first
  reset is busy for `t_rst_poweron_ns`.
* Drive `vcc_ok` low to cut power. In-flight program/erase operations are aborted and leave
  partially programmed/erased cells, committed to the store at once. Volatile state
  (page registers, status, timing mode, read-retry level) is lost; R/B# reads low while
  unpowered. Raise `vcc_ok` and issue RESET again.
* RESET during a program or erase also aborts it (busy `t_rst_prog_ns` / `t_rst_erase_ns`).

## 4. What the controller sees

| Situation | Status register | R/B# busy time |
|---|---|---|
| Program/erase/read OK | `E0h` (`RDY`,`ARDY`,`WP#`) | tPROG / tBERS / tR (wear-scaled) |
| Program or erase failure (seeded, directed, worn-out, sticky) | `FAIL` set | `fail_time_factor ×` the nominal time |
| Program to a factory-bad block | `FAIL` | `fail_time_factor × tPROG` |
| Policy rejection: 0→1 request, NOP exceeded, out-of-order page | `FAIL` | `t_reject_ns` (model choice) |
| WP# low during program/erase | `FAIL`, `WP#` bit = 0 | none |

Reads never set FAIL for bit errors: raw NAND has no ECC. Bit errors appear in the data;
ECC and read retry are the controller's job. The model-specific SET FEATURES address `A0h`
selects a read-retry level (signed byte P1, ±`retry_max_level`): positive levels lower the
read reference (recovering retention errors), negative levels raise it (recovering read
disturb). Address `01h` selects the ONFI timing mode (0–5) used by the AC timing checker.

## 5. Protocol and timing checking

Protocol misuse (commands before reset, commands to a busy LUN, data output while busy,
reads past the end of the page, unsupported opcodes, …) increments
`u_nand.n_proto_errors` and prints `PROTOCOL:`. AC timing violations (tWP, tWH, tWC, tRP,
tREH, tRC, tCLS, tALS, tDS, tWHR, tADL, tRR, tCCS against the current timing mode)
increment `u_nand.n_timing_violations`; set `timing_fatal 1` to stop at the first one.
A controller regression should assert both counters are zero except where a test provokes
an error on purpose.

## 6. Back-door API (checking only)

`bd_peek(lun, blk, pg, col)`, `bd_erase_count`, `bd_block_flags`, `bd_block_reads`,
`bd_page_flags`, `bd_page_nop`, `bd_clock()`, `bd_bake(hours, temp_c)`,
`bd_checkpoint()`. A real controller cannot do any of this; use it only in scoreboards,
for example to separate raw bit errors from controller bugs.

## 7. Golden-model check of a controller simulation

Every array decision the SV model takes is written to `target<ID>.trace`. Replaying it
through the Python twin verifies data, injected bit errors, status, busy times and the
resulting store byte-for-byte:

```bash
python3 nand_flash_twin.py cosim --config <dir>/config.json --before <copy of the store taken before the run> --trace <dir>/target0.trace
```

`sv-regress` does this for every phase automatically.

## 8. Simulator notes

* Verilator ≥ 5.0 with `--binary --timing` (tested 5.020). Recommended flags:
  `-Wno-fatal -Wno-lint -Wno-style -Wno-MULTIDRIVEN`.
* Icarus Verilog ≥ 12 with `-g2012`. Always pass `-s <top>`: otherwise Icarus also elaborates
  the unused `nand_flash_device` wrapper as a second root, and two models would share one
  store. The model contains `` `ifdef __ICARUS__`` work-arounds for two Icarus 12 crashes
  (fork/join_none and intra-assignment delays inside automatic tasks); behaviour is
  identical.
