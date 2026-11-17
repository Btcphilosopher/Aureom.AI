# Architecture

```
 definition (YAML/JSON) ──► loader ──► validator ──► RegMap (immutable model) ──┬──► SystemVerilog  rtl/sf_reg_{pkg,decoder,interface,bank}.sv
   + ALP region catalogue                │ every error collected                │──► C              fw/c/sf_regs.h, sf_regs_examples.h
   + (optional) RTL archives             ▼                                      │──► Rust           fw/rust/sf_regs.rs, sf_regs_examples.rs
                                   semantic + definition hash                   │──► Markdown       docs/*.md
                                                                                │──► testbench      verif/tb_*.sv
                                                                                └──► MANIFEST.json  (sha256 of every output and input)
```

Every emitter consumes **only** the validated `RegMap`. There is no second parser and no hand-edited output, which
is what makes "RTL, C, Rust and documentation are derived from the same validated definition" structural.
`albion_reggen check` regenerates in memory and compares byte-for-byte with the files on disk, so a stale or
hand-edited output is detected; every file carries the semantic and definition hash.

## Bus protocol: Albion Link Protocol v1

The generated bank is a **target of ALP v1**, the SilicaFlux Albion platform protocol (AlbionCore 0.1.0). It is
compiled against the real `sf_albion_pkg` (types, status codes, `sf_req_check_bits`, `sf_access_check_bits`) and
verified with the real `sf_albion_link_checker`. Nothing about the protocol is re-invented or copied by hand: the
generator's own copy of the numbers (used by the reference model) is proved equal to the package by
`albion_reggen alpcheck`.

* Request: `op` (READ/WRITE), 8-bit `tag`, 8-bit `dom`, 8-bit `attr` (privilege, security, instruction fetch,
  memory type), 64-bit lane-aligned `addr`, 16-bit byte enable `be`, 128-bit `data`.
* Response: echoed `tag`, 4-bit `status`, metadata (`is_write`, `last`), 128-bit `data`.
* Independent valid/ready channels, in-order completion, non-posted writes, no combinational request-to-response path.

### Registers inside a 128-bit word

A register is 32 or 64 bits wide at a naturally aligned offset, so it occupies byte lanes
`offset[3:0] … offset[3:0]+size−1` of the 16-byte ALP word at `offset & ~0xF`:

| Register | Word | `be` lanes |
|---|---|---|
| 32-bit at `…0x04` | `…0x00` | `0x00F0` |
| 64-bit at `…0x08` | `…0x00` | `0xFF00` |
| 32-bit at `…0x0C` | `…0x00` | `0xF000` |

A **32-bit CPU access** therefore becomes one ALP transaction with the four lanes of that register enabled — the
initiator's bridge does that, not the bank. A **64-bit access** to a 64-bit register is one transaction with eight
lanes enabled and is atomic at the bank. Two 32-bit accesses are two transactions and can tear if the register is
changing; the generated C/Rust accessors use a high-low-high read for counters and document the low-then-high
write order for the rest. A single wide access (up to 128 bits) may touch several registers of one word at once.

## Transaction semantics

**Accept is the only commit point.** A request is accepted in the cycle `req_valid && req_ready`. In that cycle
and only that cycle the bank decides the outcome from its state and the hardware inputs, updates its flip-flops,
and loads the response register. Therefore

* a stalled request (valid, not ready) has **no effect** at all and the initiator simply holds it (ALP-REQ-02);
* a response that is not taken is **held unchanged** (ALP-RSP-02) and never re-triggers anything or loses data;
* a side effect happens **exactly once** per accepted request.

```
cycle:        n          n+1        n+2        n+3
req_valid     1          1          0          0
req_ready     1          1 (a)      1          1          (a) response of A leaves this cycle
rsp_valid     0          1          1          0
rsp_ready     x          1          0 (stall)  1          B's response is held through n+2
accepted      A          B
hw pulse                 (A's)      (B's)                 registered: one cycle after acceptance
```

`req_ready = !rsp_valid_q || rsp_ready_i`: it depends on registered state and on the response channel's ready
(a ready chain), never on `req_valid` or the payload (ALP-REQ-03), and the initiator's `rsp_ready` must not depend
on `req_ready` (ALP-RSP-06). One request per cycle can be sustained.

**Advertised capacity is 2.** A new request is accepted on the same edge on which its predecessor's response
leaves, so at the start of that cycle one request is still unanswered. ALP-OUT-01 counts outstanding requests at the
start of the cycle, so the smallest honest bound is `MAX_OUTSTANDING = 2`; it is written to `SYSID.ALP_CAPS` and
passed to the link checker. (`tests/test_simulation.py::test_link_capacity_two_is_necessary_and_sufficient` shows
the AlbionCore link checker accepts this design with capacity 2 and fires `a_alp_out_01` with capacity 1.)

### Status and precedence

A refused access answers with an error status, returns zero data (ALP-RSP-05) and changes **nothing — not even the
other registers the same access touched**. In order:

| # | Check | Status |
|---|---|---|
| 1 | ALP legality: opcode, alignment (`addr[3:0]`), byte enables ≠ 0, attribute reserved bits / memory type 3, invalid domain | `BAD_OPCODE`, `ALIGN_ERR`, `BAD_BE`, `BAD_ATTR`, `ACCESS_DENIED` |
| 2 | address outside every peripheral window | `DECODE_ERR` |
| 3 | region check (`sf_access_check_bits`): read/write/execute permission, privilege, security; device memory type | `ACCESS_DENIED`, `BAD_ATTR` |
| 4 | an **enabled byte lane that belongs to no register** (a hole) | `DECODE_ERR` |
| 5 | write touching a register with no writable field, or read touching one with no readable field | `ACCESS_DENIED` |
| 6 | write to a register whose hardware gate is low | `TARGET_ERR` |
| 7 | otherwise | `OKAY` |

Steps 1–3 are the order the AlbionCore contract prescribes (legality, then decode, then region access); 4–6 are
the device level. Refusing a hole is deliberate: it is atomic and leaks nothing about unmapped lanes to an
access that the region would otherwise allow.

### Hardware/software conflicts

Resolved per field by its `precedence` (see SCHEMA.md). They are decided in the accept cycle together with all
other updates, so "same cycle" means: the hardware event/write presented in the cycle in which the software
write is accepted. A read samples the state *before* that edge, so an event arriving in the same cycle as a read
is visible to the next read.

## Module structure

| Module | Role |
|---|---|
| `sf_reg_bank` | what you instantiate: ALP link + hardware ports; contains the other two, the storage, field logic and read mux |
| `sf_reg_interface` | ALP request/response handshake, legality check, one-entry response slice |
| `sf_reg_decoder` | pure combinational: peripheral/register select per byte lane, region check, hole and permission verdict |
| `sf_reg_pkg` | address-map constants (`SF_<P>_<REG>_ADDR`, `_RESET`, region attribute bytes, `SF_REG_MAP_HASH`) |

* Every flip-flop has an asynchronous active-low reset (`rst_ni`); release it synchronously (ALP-RST-03).
  After reset the response channel is empty and all pulses and strobes are 0.
* Every **hardware output is a flip-flop**; there is no combinational path from the request to a hardware output.
  Hardware inputs reach flip-flops (and, through the status/gate logic, the response register) in the accept cycle.
* Live `ro` fields (`hw: input`) are sampled combinationally in the accept cycle; they have no storage.
* No latches, no combinational loops (checked with Yosys `check -assert`), zero Verilator `-Wall` warnings.
* Requires `sf_albion_pkg.sv` (vendored under `third_party/albioncore/`). Verified with Verilator 5.020 and Yosys 0.33,
  the tools AlbionCore itself uses; Icarus Verilog 12 cannot parse `sf_albion_pkg.sv`.

### Hardware port naming

`<peripheral>_<register>_<field>_<suffix>` in lower case:

| Field kind | Ports |
|---|---|
| `ro`/`input` | `_i` (live value) |
| `ro`/`update` | `_hw_we_i`, `_hw_wdata_i` |
| `rw`, `wo`/`out` | `_o` (+ `_hw_we_i`, `_hw_wdata_i` when `hw: update`) |
| `w1c` | `_o` (flag level), `_set_i` (per-bit event) |
| `w1s` | `_o`, `_clr_i` |
| `w1p` | `_pulse_o` |
| register | `<p>_<reg>_wr_o`, `<p>_<reg>_rd_o`, `<p>_<reg>_wgate_i` |
| peripheral | `<p>_irq_o` |

Register arrays use one packed vector, element *i* at bit `i·width`. Port names are listed with their bound RTL
signal in the generated `docs/HARDWARE_PORTS.md`.

## Firmware

**C (`sf_regs.h`).** Constants for every address, width, reset, field shift/mask; static asserts that every
address is naturally aligned; one inline function per access, each a single naturally aligned volatile access of
the register's width. Read-modify-write helpers write back **only the bits of `rw` fields** (`_RW_MASK`): the bits of
`w1c`/`w1s`/`w1p` fields and read-only bits are written as 0, so updating one field can never clear an unrelated
interrupt flag or fire a command; helpers that could not be safe (read side effects, stored write-only fields)
are not generated. Array accessors check the index and call `SF_REGS_FAULT()` (default `__builtin_trap`). 64-bit
registers use one access on 64-bit CPUs and two on 32-bit ones (`SF_REGS_NATIVE64`). Access primitives can be
replaced (`SF_REGS_CUSTOM_ACCESS`) for remapped windows, simulators and mocks. Compiles as C99/C11 and C++17.

**Rust (`sf_regs.rs`).** All access goes through the `RegBus` trait. The only `unsafe` code is `Mmio`, which checks
alignment and that the bus address fits a pointer before one volatile access; `Mmio::new` is `unsafe` and documents the
contract. A register value is a newtype with field getters and **checked** builders (`FieldOverflow` instead of silent
truncation); array indices are checked (`IndexError`); the same RMW-safety rules as C apply.

**Both** carry `SF_REGS_MAP_HASH`/`MAP_HASH` and a `hardware_matches` check against `SYSID.REGMAP_HASH`.

## Provenance and determinism

No timestamps, host names or absolute paths appear in any output; lists are address-ordered; the same
definition yields byte-identical output across runs, machines, hash seeds and source orderings (tested).
`MANIFEST.json` lists the SHA-256 of every input and output. The chain
*definition → semantic hash → `SYSID.REGMAP_HASH` in RTL = `SF_REGS_MAP_HASH` in C = `MAP_HASH` in Rust* lets
firmware detect at run time that it was built against a different register map than the silicon implements.
