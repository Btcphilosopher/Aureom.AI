# NLSF v1 — NANDLab Store Format

The persistent backing store shared by `nand_flash_model.sv` and `nand_flash_twin.py`.
One file per NAND **target** (chip enable): `<store>/target<N>.nlsf`, where
`N = (channel × packages_per_channel + package) × targets_per_package + ce`.

## Design goals

* **Committed state only.** The file holds what the cells contain. Volatile state (page
  register, status, features, timing mode, read-retry level) is never persisted, so a
  controller reset or process restart cannot "restore" anything that was erased.
* **Crash consistency.** The file is an append-only journal: every committed array change is
  appended and flushed (`$fflush` in SV, `flush()` plus optional `fsync()` in Python) when it
  happens. A process killed at any point leaves a valid prefix.
* **One format, two simulators.** Plain text, one record per line, whitespace-separated
  tokens, readable with `$fscanf` in Icarus Verilog and Verilator.
* **Exact reals.** Reals are written with `%.17g` by both models, so they round-trip
  exactly and the SV and Python journals can be compared textually.

## Records

Every record ends with the token `;`. A line without the terminating `;` is a **torn write**:
it is skipped on load and reported. Each new writer session starts on a fresh line, so a torn
line is never glued to the next record. Blank lines are ignored; unknown record tags are
skipped (forward compatibility).

| Record | Fields | Meaning on replay |
|---|---|---|
| `NLSF 1 <data> <spare> <pages/blk> <blocks/LUN> <planes> <LUNs> <seed:016x> <target> ;` | header | Geometry, global fault seed and target index. Must match the configuration and, in SV, the module parameters (mismatch is fatal). |
| `M <key> <value> ;` | metadata | `model`, `version`, `creator` (`python` or `sv`), `config` (fingerprint), `compacted`. Not used by replay. |
| `C <clock_s> ;` | retention clock checkpoint | `clock = max(clock, value)` |
| `B <lun> <blk> <erase_count> <flags:02x> <reads> ;` | absolute block state | replaces erase count, block flags, reads-since-erase |
| `R <lun> <blk> <reads> ;` | read-disturb counter | sets reads-since-erase (one per page read when `persist_read_counts` is on) |
| `E <lun> <blk> <clock_s> ;` | block erased | all pages of the block become erased (reads all 1s); always followed by a `B` record |
| `P <lun> <blk> <pg> <nop> <flags:02x> <t_prog_s> <b0> … <bN-1> ;` | page state | the page's complete cell contents (data + spare, hex bytes), program count since erase, page flags, program timestamp |

`clock_s` is the **retention clock**: seconds at the reference temperature. Powered time is
scaled by the Arrhenius factor of the operating temperature; an unpowered bake adds
`hours × 3600 × AF(T_bake)`. On load the clock is the maximum of every `C`, `E` and `P`
timestamp, so it never runs backwards.

Records are **absolute**, not deltas: a `P` record carries the page as it now is (for a
program, `old AND new`; for an interrupted program or erase, the partial result). Replay
therefore never needs the fault model or the configuration — only the records.

### Flags

Page flags: `02` program failed, `04` program interrupted (reset or power loss), `08`
factory bad-block marker page, `10` left by a failed or interrupted erase. Pages with `02`,
`04` or `10` are *unstable*: they read with the extra `interrupted_rber` error rate.

Block flags: `01` factory bad, `02` erase failed (sticky), `04` a program failed in this block,
`08` worn out (beyond `endurance_hard_limit_factor × rated endurance`), `10` marginal
(last erase failed or was interrupted), `20` erase interrupted. `10` and `20` are cleared by a
successful erase.

## Manufacture

When a store does not exist, it is created ("the device leaves the factory"): header,
`M` records, `C 0 ;`, then for each factory-bad block a `B` record with flag `01` and two
`P` records (first and last page) that hold `00h` in spare byte `bad_block_marker_byte`
(default 0). The SV model and the Python twin generate byte-identical manufacture records
for the same configuration (only `M creator` differs) — checked by `sv-regress`.

## Compaction

`nand_flash_twin.py compact --store DIR` (or `NandTarget.compact()`) rewrites a journal as a
snapshot — header, metadata, one `C`, a `B` for every non-default block, a `P` for every
stored page — via a temporary file and an atomic `rename`. The reference test
`compaction_equivalence` checks that the semantic state is unchanged.

## Example

```
NLSF 1 512 16 16 64 2 2 00005f1caf10c552 0 ;
M model SilicaFlux-NANDLab ;
M version 0.1.0 ;
M creator sv ;
M config 9c1f3e0d2a7b4c55 ;
C 0 ;
B 0 5 0 01 0 ;
P 0 5 0 0 08 0 ff ff … 00 ff … ff ;
R 0 2 1 ;
P 0 2 0 1 00 0.0010000000000000001 3e a1 … ;
E 0 2 0.0030000000000000001 ;
B 0 2 1 00 0 ;
```
