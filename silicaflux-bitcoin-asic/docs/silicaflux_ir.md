# SilicaFlux architectural IR (section 15/16)

## Why an IR at all, for something this small

The temptation with a "generator" layer is to make it a string template
that stamps out RTL text. That produces exactly the "opaque
SystemVerilog" section 16 warns against: no validation step, no
inspectable intermediate form, and a diff of the generated file that
means nothing without re-reading the template. SilicaFlux instead has
three real, separately-testable stages:

```
MinerArchitecture (dataclasses)  -- what a human/config file writes
        |  silicaflux.compiler.lower()   [validates; never trusts input]
        v
IRDesign (silicaflux/ir/nodes.py)  -- a flat list of typed, tagged params
        |  silicaflux.generators.sv_emitter.emit_config_package()  [pure fn]
        v
SystemVerilog text (rtl/generated/silicaflux_config_pkg.sv)
```

`lower()` is a real compiler pass: it re-validates the architecture
(`arch.validate()` — belt-and-braces, since the spec layer already
validates on construction, but the compiler must not trust its caller),
then produces one `IRParam` per architectural knob, each tagged with
which of the eight section-15 categories it belongs to:

- **DATAFLOW** — core count, nonce start/stride (how work is split)
- **PIPELINE** — core architecture selection, pipeline depth
- **REGISTER** — message-schedule storage strategy, telemetry counter width
- **COMBINATIONAL** — reserved; nothing in the current parameter set
  needs this tag, but the IR supports it (e.g. a future "constant-fold
  the digest-pass padding by hand" toggle would live here)
- **MEMORY** — reserved; this design has no addressed storage
- **CONTROL** — compile-time feature enables (assertions, telemetry)
- **CLOCK** — target frequency, clock-gating enable (metadata only — see
  `docs/architecture.md` §9 for why gating isn't wired up yet)
- **INTERFACE** — widths fixed by the Bitcoin protocol itself (nonce
  width, header width, hash width) — these exist in the IR mainly so the
  generated package documents *why* they're fixed, not because they're
  ever actually swept

`emit_config_package()` is then a **pure function**, `IRDesign -> str`,
with no access back to the spec layer and no non-determinism (no
timestamps, no unordered-dict iteration) — the same `IRDesign` always
produces byte-identical output. That determinism is what makes the
generated file reviewable: a diff of `silicaflux_config_pkg.sv` after
changing one config field shows exactly one changed line, every time.

## What actually gets generated vs. hand-written

The generated package carries **configuration** (`NUM_CORES`,
`PIPELINE_DEPTH`, `SCHEDULE_ARCHITECTURE`, ...) as `localparam`s grouped
by IR category with inline comments. It does not, and architecturally
should not, generate the fixed algorithmic RTL (Ch/Maj/Sigma, the round
function, the padding constants) — that content doesn't vary with
configuration, so there is nothing for a generator to parametrize; it's
hand-written once, and correctness-critical enough that section 25's
"independent implementation, cross-checked against Python" rule matters
far more for it than any generation-determinism property would.
`hash_core_array.sv`'s `NUM_CORES`-wide replication is handled by plain
SystemVerilog `generate for` — the right, native tool for "instantiate N
of these," not something a Python text generator should reimplement.

## Running it

```bash
python -m silicaflux_bitcoin.generate --config configs/deep_pipeline.yaml
# -> rtl/generated/silicaflux_config_pkg.sv
```

Four named configs ship in `configs/`: `default` (small, fast to
simulate), `small_iterative` (64 cheap cores — area-optimised end of the
Pareto frontier), `deep_pipeline` (few cores, PIPELINE_DEPTH=64 —
throughput-optimised end), `array_64core` (64 cores at a moderate
8-stage pipeline depth — the balanced point). See
`docs/architecture.md` §3 for what each tradeoff actually measures to.
