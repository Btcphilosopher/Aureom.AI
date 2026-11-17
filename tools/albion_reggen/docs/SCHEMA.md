# Register definition format (schema version 1)

Definitions are written in YAML (or JSON) and validated by `python -m albion_reggen validate`.
`schema/regdef.schema.json` is a JSON Schema for the *shape* (use it in an editor); the rules below that
need arithmetic or cross-references are enforced only by the validator, each with a stable error code
(`E_*`). The validator **collects every problem** and prints them all; nothing is generated from a
definition that has any error.

## File layout

```yaml
regdef_version: 1                 # required; this release accepts 1
map:
  name: silicaflux_regs           # lower_snake_case
  version: "1.0"                  # MAJOR.MINOR, each < 65536 (appears in SYSID.REGMAP_VERSION)
  description: ...
  extra_regions: [...]            # optional, see "Regions"
peripherals:
  - include: sysid.yaml           # a peripheral kept in its own file (path relative to this file)
  - name: ...                     # or an inline peripheral
```

An included file contains one peripheral mapping. Include cycles and missing files are errors (`E_INCLUDE`).

### Loader strictness

YAML 1.1 silently changes what registers are made of, so the loader removes the traps (`E_PARSE`):

| Trap | Handling |
|---|---|
| `bits: 7:0` read as the base-60 number 420 | stays the string `"7:0"` |
| `no`, `on`, `off`, `yes` as booleans (`name: NO`) | only `true`/`false` are booleans |
| `010` as octal | rejected: write decimal, `0x…` or `0b…` |
| duplicate mapping key silently overwriting | rejected |
| floats | not recognised (a number with a dot is a string and fails type checks) |

Integers may be written `4096`, `0x1000`, `0x1_8000_0000`, `0b1010`, or as quoted strings of those.

## Peripheral

| Key | Meaning |
|---|---|
| `name` | `lower_snake_case`, unique |
| `description` | prose |
| `region` | name of an ALP region (catalogue or `extra_regions`) the window must lie in (`E_REGION_UNKNOWN`, `E_REGION_RANGE`) |
| `base`, `size` | absolute 64-bit window; `size` a power of two ≥ 16, `base` aligned to `size` (`E_WINDOW_SIZE`, `E_WINDOW_ALIGN`); windows may not overlap (`E_WINDOW_OVERLAP`) |
| `priv_only`, `secure_only` | may *tighten* the region's access; relaxing a region that is privileged/secure-only is `E_RELAX` |
| `rtl` | provenance and binding, see "RTL binding" |
| `connect` | `{irq: module.port}` — where the peripheral's interrupt output goes |
| `registers` | list of registers |
| `examples` | firmware examples, see "Examples" |

The peripheral inherits the region's ALP attributes (read, write, execute, privileged-only, secure-only,
memory type). A peripheral with writable registers in a region that forbids writes is `E_REGION_ATTR`.

## Register

| Key | Meaning |
|---|---|
| `name` | `UPPER_SNAKE_CASE`; unique in the peripheral |
| `offset` | byte offset from the peripheral base, naturally aligned (`E_REG_ALIGN`) |
| `width` | 32 (default) or 64 (`E_REG_WIDTH`) |
| `count`, `stride` | array of `count` registers `stride` bytes apart (default stride = register size; must be a multiple of it, `E_REG_STRIDE`, `E_REG_COUNT`) |
| `fields` | list of fields (or use the single-field shorthand) |
| `wr_strobe`, `rd_strobe` | add a one-cycle hardware pulse per accepted write / read of the register |
| `write_gate` | add a hardware input; a write while it is low is refused with `TARGET_ERR` and has no effect on any register |
| `reserved` | documentation of reserved ranges (`["31:24", "5"]`); must not overlap fields (`E_RESERVED`). Bits not covered by any field are reserved anyway |
| `connect` | RTL binding of the register-level signals: `wr_strobe`, `rd_strobe`, `gate` |

All registers of a peripheral must lie inside its window and may not overlap, array elements included
(`E_REG_RANGE`, `E_REG_OVERLAP`). Two registers may share one 16-byte ALP word — the byte enables pick them out.

**Single-field shorthand.** A register with no `fields` and with `access:` (and optionally `reset`, `hw`,
`precedence`, `interrupt`, `connect`) is one field called `VALUE` spanning the whole register.

## Field

```yaml
- {name: EN, bit: 0, access: rw, reset: 1}
- {name: MODE, bits: "7:4", access: rw}                         # also bits: [7, 4]
- {name: SRC{i}, bits: "2:0", repeat: {count: 8, stride: 4, first: 8}, access: rw, reset: 1}   # SRC8..SRC15
```

`bit` / `bits` give the position; `width` is optional and must agree (`E_FIELD_WIDTH`). A bad range
(`hi < lo`, outside the register, overlapping a sibling) is `E_FIELD_BITS` / `E_FIELD_OVERLAP`.
`repeat` expands a field `count` times, `stride` bits apart; the name must contain `{i}` (replaced by
`first + k`).

### Access types

| `access` | Software | Hardware option (`hw`, first is default) |
|---|---|---|
| `ro` | read only | `const` returns the reset value · `input` reads a live hardware input at the accepting cycle · `update` is a flop that hardware writes (`hw_we` + `hw_wdata`) |
| `rw` | read / write | `none` (output only) · `update` hardware may also write it |
| `wo` | write only, reads 0 | `out` stores the value and drives hardware · `none` the written value is ignored (the write is the event) |
| `w1c` | write 1 to clear | `event` per-bit hardware set strobes · `none` software-only flag |
| `w1s` | write 1 to set | `event` per-bit hardware clear strobes · `none` |
| `w1p` | write 1 → one-cycle hardware pulse; reads 0; no state | — |

Invalid combinations are `E_FIELD_ACCESS` / `E_FIELD_HW`.

**Update precedence.** Where hardware and software can change the same bit in the same cycle, `precedence`
decides (`hw` default, or `sw`; `E_PRECEDENCE` if given where nothing can conflict):

| Field | Software action | Hardware action | `hw` wins | `sw` wins |
|---|---|---|---|---|
| `rw`, `hw: update` | write | `hw_we` write | hardware value | software value |
| `w1c`, `hw: event` | write 1 clears | event sets | bit stays **set** | bit is **cleared** |
| `w1s`, `hw: event` | write 1 sets | event clears | bit is **cleared** | bit stays **set** |

### Reset values (`E_RESET_RANGE`, `E_RESET_INVALID`, `E_RESET_SYMBOL`)

`reset` must be an integer in `0 … 2^width − 1`. It is rejected (`E_RESET_INVALID`) if non-zero on a field
that holds no state (`w1p`, `wo`/`none`) or has no reset value (`ro`/`input`, a live input). Bits no field
covers reset to 0. The only symbol is `$regmap_hash` (on a 32- or 64-bit `ro`/`const` field): the first
8 bytes of the semantic hash, see "Hashes".

### Interrupts (`E_INTERRUPT`)

```yaml
- {name: DONE, bit: 2, access: w1c, hw: event, interrupt: "INT_ENABLE.DONE"}
```

A `w1c` field, or a `ro` field with `hw: input|update`, may name an `rw` enable field of the **same width in
the same peripheral** (a non-array register). The peripheral then gets one output
`<periph>_irq_o = |(status & enable)` over all its interrupt fields.

## Regions

The ALP region catalogue (AlbionCore `regions.yaml`, vendored unmodified) is built in. A map may add
`extra_regions` for peripherals that have no catalogue region yet; they obey the ALP-ADR-01 rules —
power-of-two size ≥ 4 KiB, base aligned to size, inside 64 bits, no overlap with another region or the reserved
legacy window (`E_REGION_SIZE`, `E_REGION_ALIGN`, `E_REGION_RANGE`, `E_REGION_OVERLAP`, `E_REGION_RESERVED`) —
and are flagged **proposed** in every generated document.

```yaml
extra_regions:
  - name: sysctl
    base: 0x1_8000_0000
    size: 0x10_0000
    asid: config
    attr: {read: true, write: true, priv_only: true, mem_type: device}
```

## RTL binding (`rtl:`)

```yaml
rtl:
  status: bound                    # bound | register_compatible | constants
  summary: ...
  modules:
    - module: sf_sram_subsystem
      role: attach                 # attach | replace
      archive: SilicaFlux-main/.../silicaflux-sramcontroller-p73.zip   # relative to the repository root
      path: silicaflux-sramcontroller/rtl/sramc/sf_sram_subsystem.sv   # member inside the archive
      sha256: 4b0f0d2c…            # SHA-256 of that file
      ports: {src_en: input, idle: output, ...}                        # the ports this definition connects to
```

* `attach` — the bank sits **beside** the block and drives/reads its control ports, so a bank output meets a
  block *input* (and vice versa).
* `replace` — the bank **takes over the block's hand-written register slave** (for example `hpc_cq_mmio`), so
  each bank port has the same direction as the matching port of that slave.

Fields and registers say which RTL signal a bank port connects to with `connect: {kind: "module.port[slice]"}`;
kinds are `value`, `event`, `pulse`, `hw_we`, `hw_wdata` (field) and `wr_strobe`, `rd_strobe`, `gate` (register),
`irq` (peripheral). The validator checks syntax, that the module and port are declared, and the **direction**
(`E_BIND_SYNTAX`, `E_BIND_MODULE`, `E_BIND_PORT`, `E_BIND_DIR`, `E_BIND_KIND`). `albion_reggen bindcheck` then opens the
archive, checks the SHA-256 and that each declared port exists with the declared direction in the real RTL.

`status` is an honest statement of how well the definition is integrated: `bound` (ports of an implemented block),
`register_compatible` (same registers as a block whose register file cannot be bound port by port), `constants`
(values taken from an implemented package).

## Examples

```yaml
examples:
  - title: Run one transfer
    steps:
      - {write: SRC, value: 0x20000000}
      - {set: "TAG.TAG", value: 7}            # read-modify-write of an rw field
      - {trigger: "CTRL.GO"}                  # write 1 to a w1p / w1s field
      - {poll: "STATUS.DONE", until: 1, max: 100000}
      - {expect: "STATUS.ERR", value: 0}
      - {clear: "INT_STATUS.DONE"}            # write 1 to a w1c field
      - {read: CPL, index: 0}                 # arrays need index
      - {comment: free text}
```

Steps are checked against the model (register and field exist, the access type fits, values fit the field,
array index in range; `set`/`trigger`/`clear` are refused on registers with read side effects or stored
write-only fields). The same steps become C, Rust and prose (`E_EXAMPLE`).

## Hashes

* **Semantic hash** — SHA-256 of the canonical JSON of everything that changes hardware behaviour or
  firmware-visible numbers: regions used, windows, register offsets/widths/counts, fields, access types,
  hardware options, precedence, interrupt wiring, reset values, region attributes. Descriptions, examples and
  RTL provenance are **not** included, so editing prose never changes the hardware's ID register. Reordering
  peripherals, registers or fields in the source changes nothing (everything is address-sorted).
* **Definition hash** — SHA-256 of the whole canonical definition including prose, examples and bindings.

Both are stamped in every generated file. The first 8 bytes of the semantic hash are `SYSID.REGMAP_HASH`
in hardware, `SF_REGS_MAP_HASH` in C and `MAP_HASH` in Rust.

## Error codes

`E_PARSE` `E_INCLUDE` `E_SCHEMA` `E_UNKNOWN_KEY` `E_VERSION` `E_NAME` `E_KEYWORD` `E_DUP_NAME` `E_INT`
`E_REGION_UNKNOWN` `E_REGION_RANGE` `E_REGION_ALIGN` `E_REGION_SIZE` `E_REGION_OVERLAP` `E_REGION_RESERVED`
`E_REGION_ATTR` `E_RELAX` `E_WINDOW_SIZE` `E_WINDOW_ALIGN` `E_WINDOW_OVERLAP` `E_REG_WIDTH` `E_REG_ALIGN`
`E_REG_RANGE` `E_REG_OVERLAP` `E_REG_COUNT` `E_REG_STRIDE` `E_NO_FIELDS` `E_FIELD_BITS` `E_FIELD_WIDTH`
`E_FIELD_OVERLAP` `E_FIELD_ACCESS` `E_FIELD_HW` `E_RESET_RANGE` `E_RESET_INVALID` `E_RESET_SYMBOL`
`E_PRECEDENCE` `E_INTERRUPT` `E_GATE` `E_STROBE` `E_RESERVED` `E_IDENT_COLLISION` `E_BIND_SYNTAX`
`E_BIND_MODULE` `E_BIND_PORT` `E_BIND_DIR` `E_BIND_KIND` `E_EXAMPLE`.
`E_KEYWORD` rejects names that would be unusable Rust identifiers (`TYPE`, `CONST`, …);
`E_IDENT_COLLISION` rejects two registers or ports that would flatten to the same generated name.
Every code has a test in `tests/test_validation.py`.
