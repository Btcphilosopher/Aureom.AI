# SilicaFlux NANDLab -- engineering report (v0.1.0)

_Aureom.AI | SilicaFlux-STORE | Project 52 -- generated 2026-11-11 22:24 UTC_

> Simulated results from a behavioural model of external NAND devices. Every reliability and array-timing value is illustrative (see MODEL_LIMITATIONS.md); nothing here is measured NAND data.

## Device under simulation

* Geometry: 2 ch x 1 pkg x 2 CE x 2 die x 1 LUN x 2 plane x 32 blk x 16 pg x (512+16) B = 4.00 MiB user data
* Fault scenario profile: `stress` -- Deliberately exaggerated rates so error handling is exercised in short simulations. Not representative of any device.

## Verification

* Python reference suite: **32/32 pass**

| Area | Test | Result | Detail |
|---|---|---|---|
| Fresh device | `fresh_device_reads_erased` | PASS | {"pages_checked": 3} |
| Fresh device | `reset_required_after_power_on` | PASS |  |
| Fresh device | `parameter_page` | PASS | {"crc": "1370"} |
| Read after program | `program_read_roundtrip` | PASS |  |
| Read after program | `partial_page_programming_nop` | PASS |  |
| Invalid bit transitions | `invalid_transition_policies` | PASS |  |
| Invalid bit transitions | `sequential_program_rule` | PASS |  |
| Block erase | `block_erase` | PASS | {"erase_busy_ns": 2000000.0} |
| Page boundaries | `page_boundaries` | PASS |  |
| Factory bad blocks | `factory_bad_blocks` | PASS | {"nominal_factory_bad_lun0": [21], "nominal_factory_bad_lun1": [8, 40]} |
| Persistence | `controller_reset_preserves_array` | PASS |  |
| Persistence | `process_restart` | PASS |  |
| Persistence | `crash_consistency_subprocess` | PASS |  |
| Persistence | `torn_journal_tail` | PASS |  |
| Persistence | `compaction_equivalence` | PASS | {"journal_lines": 33, "compacted_lines": 23} |
| Persistence | `manufacture_determinism` | PASS |  |
| Injected bit errors | `bit_error_statistics` | PASS | {"bits": 270336, "errors": 565, "expected": 540.7} |
| Injected bit errors | `error_physics_direction` | PASS | {"retention_0to1": 47, "disturb_1to0": 246} |
| Injected bit errors | `stuck_bits_and_directed_failures` | PASS |  |
| Injected bit errors | `endurance_degradation` | PASS | {"rber_vs_pe": ["1.00e-10", "6.35e-09", "2.51e-08", "1.00e-07", "4.00e-07"]} |
| Power interruption | `power_cut_during_program` | PASS | {"intended_zeros": 2106, "written_zeros": 827} |
| Power interruption | `power_cut_during_erase` | PASS |  |
| Power interruption | `power_cut_persists_across_restart` | PASS |  |
| Error reproducibility | `error_reproducibility` | PASS |  |
| Error reproducibility | `nested_monotonic_retention` | PASS | {"errors_vs_bake": [0, 0, 6, 12, 31]} |
| Error reproducibility | `restart_reproduces_errors` | PASS |  |
| Read retry | `read_retry_recovers_retention` | PASS | {"errors_by_retry_level": {"0": 22, "1": 13, "2": 9, "3": 6, "-2": 98}} |
| Timing | `busy_times_and_wp` | PASS |  |
| Latency and contention | `latency_contention` | PASS | {"fifo_read_latency_us": 386.338, "interleave_read_latency_us": 132.438} |
| Latency and contention | `read_retry_latency` | PASS | {"retries": 6, "errors_first": 141, "errors_final": 11} |
| Threshold research model | `vt_model_consistency` | PASS | {"checks": 13} |
| SV interface | `svcfg_export` | PASS |  |

* SystemVerilog regression (verilator): **PASS**, 128/128 testbench checks; every phase replayed through the Python golden model.

| Store | Phase | TB checks | Co-simulation | Ops replayed | Bit errors replayed |
|---|---|---|---|---|---|
| store_functional | fresh | 78/78 | bit-exact | 321 | 0 |
| store_functional | restart | 14/14 | bit-exact | 9 | 0 |
| store_functional | powercut | 13/13 | bit-exact | 12 | 0 |
| store_faults | faults | 7/7 | bit-exact | 205 | 41 |
| store_faults | faults_bake | 3/3 | bit-exact | 82 | 8852 |
| store_channel | channel (2 targets, shared bus) | 13/13 | bit-exact | 5 | 0 |

## Fault scenario (target 0, stress profile, 400 h unpowered bake at 55 degC)

Bit errors observed in a full read sweep, attributed by mechanism:

| Wear | Retention | Read disturb | Read noise | Stuck |
|---|---|---|---|---|
| 5757 | 73487 | 88 | 67 | 0 |

* Ground-truth bad/failed blocks: 17; controller-visible factory markers: 4

## Latency and contention (illustrative timing)

| Scenario | Read p50 (us) | Read p99 (us) | Program p50 (us) | Erases | Read MB/s | Write MB/s | Ch util | Retries | Uncorrectable |
|---|---|---|---|---|---|---|---|---|---|
| FIFO, mode 0 | 18515 | 47246 | 19671 | 0 | 6.2 | 4.1 | 0.57 | 0 | 0 |
| Interleave, mode 0 | 1105 | 5840 | 1297 | 0 | 8.7 | 5.7 | 0.79 | 0 | 0 |
| Interleave, mode 5 | 40 | 458 | 215 | 0 | 9.2 | 6.0 | 0.17 | 0 | 0 |
| Interleave, mode 5, multi-plane | 73 | 528 | 253 | 0 | 18.5 | 12.1 | 0.35 | 0 | 0 |
| Interleave, mode 5, stress + retention bake | 36 | 101 | 0 | 0 | 15.1 | 0.0 | 0.16 | 31 | 5 |
| Single target, write-heavy (block reuse -> erases) | 36 | 2232 | 211 | 158 | 0.5 | 1.6 | 0.04 | 0 | 0 |

## Threshold-voltage research model (UNVALIDATED)

RBER with fixed default read references / optimal references:

| Mode | fresh | 1 year retention | rated P/E | rated P/E + 1 year | 100k reads (disturb) |
|---|---|---|---|---|---|
| SLC | 1.2e-11 / 1.4e-13 | 1.4e-11 / 7.9e-12 | 2.0e-05 / 1.2e-06 | 2.2e-05 / 1.4e-05 | 1.6e-10 / 7.1e-13 |
| MLC | 2.4e-06 / 7.7e-07 | 6.0e-05 / 3.0e-05 | 1.5e-03 / 3.4e-04 | 8.1e-03 / 2.1e-03 | 8.3e-06 / 7.7e-07 |
| TLC | 3.7e-04 / 3.7e-04 | 2.7e-03 / 1.8e-03 | 5.3e-03 / 4.6e-03 | 2.9e-02 / 1.1e-02 | 4.0e-04 / 3.7e-04 |
| QLC | 8.4e-04 / 8.1e-04 | 6.0e-03 / 3.9e-03 | 4.9e-03 / 4.4e-03 | 3.9e-02 / 1.2e-02 | 9.0e-04 / 8.1e-04 |

Internal consistency checks: 13/13 pass. These test the mathematics, not agreement with silicon.

## Limitations

* Behavioural model of external NAND devices; it does not model, and makes no claim about, SilicaFlux-fabricated NAND cells.
* All reliability numbers (RBER coefficients, failure probabilities, factory-bad rate, read-disturb and retention terms) are illustrative. They are not measured NAND reliability and must be replaced with calibrated device data before any quantitative conclusion.
* Array timing (tR, tPROG, tBERS, tRST, tFEAT) are illustrative SLC-datasheet-range values; the ONFI async timing-mode table is a transcription to be checked against the ONFI revision / datasheet in use.
* ONFI subset only: no cache read/program, multi-plane commands in SV, copyback, read unique ID, synchronous/NV-DDR/Toggle interfaces, ZQ calibration, volume addressing or ODT. Multi-plane and multi-LUN concurrency are modelled in the Python latency engine; the SV model supports multi-LUN interleaving.
* Device semantics are SLC only. MLC/TLC/QLC exist only as a Gaussian threshold-voltage research model (unvalidated); there is no multi-bit device model, no program-order (LSB/MSB) constraint model and no cell-to-cell interference.
* Bit errors are drawn per cell from deterministic hashes; spatial correlation (bitline/wordline faults, edge wordlines), temperature during programming, program/erase suspend, and data-pattern dependence are not modelled.
* Retention uses an Arrhenius time scaling (Ea = 1.1 eV) of an illustrative power-law term; read disturb is a linear function of reads since erase; both are bit-level abstractions, not charge-transport physics.
* Partial-page programs update the page's program timestamp, so retention of earlier-programmed bytes on the same page is slightly underestimated.
* Power-loss behaviour (partially programmed/erased cells chosen by hash, proportional to elapsed busy time) is a plausible abstraction, not a characterised device behaviour.
* Stuck bits are applied at read time only; they do not cause program-verify failures.
* The SV model checks a subset of host AC timing (tWP, tWH, tWC, tRP, tREH, tRC, tCLS, tALS, tDS, tWHR, tADL, tRR, tCCS); hold times and CE#-related timings are not checked.
* The latency engine is a timing-accurate resource model (bus cycles, array busy, LUN/plane/channel contention), not a full SSD/FTL simulator; its workload generator is synthetic.
* Python and SV agreement is bit-exact for identical operation histories on the same platform; both rely on IEEE-754 double arithmetic and the C math library for exp/pow.
