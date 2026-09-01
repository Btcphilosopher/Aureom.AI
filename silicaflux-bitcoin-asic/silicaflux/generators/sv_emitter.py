"""
silicaflux.generators.sv_emitter -- deterministic IRDesign -> SystemVerilog.

`emit_config_package()` is a pure function: same IRDesign in, byte-identical
`.sv` text out, every time (no timestamps, no non-deterministic ordering).
Determinism matters here because the generated file is checked into
rtl/generated/ and reviewed like any other RTL -- a generator that produces
different output for identical input on every run would be undebuggable
and unreviewable, which is exactly what section 16 ("do not generate
opaque SystemVerilog") warns against.

Output is one `package silicaflux_config_pkg;` containing a `localparam`
(or `parameter`, if IRParam.overridable) per IRParam, grouped by IRKind
with a banner comment per group -- so the *generated* RTL documents its
own structure using the same eight categories the architecture layer
above it is organised around.
"""
from __future__ import annotations

from silicaflux.ir.nodes import IRDesign, IRKind, IRParam

_GENERATED_BANNER = """\
// ============================================================================
// AUTO-GENERATED FILE -- DO NOT EDIT BY HAND
//
// Produced by silicaflux.generators.sv_emitter.emit_config_package() from
// architecture "{config_name}". Regenerate with:
//     python -m silicaflux_bitcoin.generate --config <yaml> --out <path>
// Source of truth is the architecture spec (silicaflux/architecture/spec.py)
// and the named config file, NOT this file -- edits here will be
// overwritten on the next `generate` run.
// ============================================================================
"""

_KIND_BANNER = {
    IRKind.DATAFLOW: "DATAFLOW -- core count / nonce search partitioning",
    IRKind.PIPELINE: "PIPELINE -- core micro-architecture and stage count",
    IRKind.REGISTER: "REGISTER -- message-schedule and telemetry storage architecture",
    IRKind.COMBINATIONAL: "COMBINATIONAL -- purely combinational structural choices",
    IRKind.MEMORY: "MEMORY -- addressed storage",
    IRKind.CONTROL: "CONTROL -- control-plane / compile-time feature enables",
    IRKind.CLOCK: "CLOCK -- clock domain metadata (abstract, technology-independent)",
    IRKind.INTERFACE: "INTERFACE -- external port widths fixed by the Bitcoin protocol",
}

# Emit groups in a fixed order so output is stable regardless of dict/set
# iteration order anywhere upstream.
_KIND_ORDER = [
    IRKind.INTERFACE, IRKind.DATAFLOW, IRKind.PIPELINE, IRKind.REGISTER,
    IRKind.CONTROL, IRKind.CLOCK, IRKind.COMBINATIONAL, IRKind.MEMORY,
]


def _sv_literal(p: IRParam) -> str:
    if p.sv_type == "string":
        # value is pre-quoted by the compiler pass (lower.py) for strings.
        return str(p.value)
    if p.sv_type == "bit":
        return "1'b1" if bool(p.value) else "1'b0"
    if p.sv_type == "real":
        return f"{float(p.value):.3f}"
    if isinstance(p.value, bool):
        return "1" if p.value else "0"
    return str(p.value)


def _emit_param(p: IRParam) -> str:
    kw = "parameter" if p.overridable else "localparam"
    decl = f"  {kw} {p.sv_type} {p.name} = {_sv_literal(p)};"
    if p.comment:
        return f"{decl}  // {p.comment}"
    return decl


def emit_config_package(design: IRDesign) -> str:
    lines = []
    lines.append(_GENERATED_BANNER.format(config_name=design.source_config_name))
    if design.notes:
        lines.append("// Architecture notes:")
        for n in design.notes:
            lines.append(f"//   {n}")
        lines.append("//")
    for cd in design.clock_domains:
        lines.append(f"//   Clock domain '{cd.name}': target {cd.target_frequency_mhz:.1f} MHz"
                      f"{' (clock-gated)' if cd.enable_clock_gating else ''}")
    lines.append("")
    lines.append("package silicaflux_config_pkg;")
    lines.append("")

    for kind in _KIND_ORDER:
        group = design.params_by_kind(kind)
        if not group:
            continue
        lines.append(f"  // ---- {_KIND_BANNER[kind]} ----")
        for p in group:
            lines.append(_emit_param(p))
        lines.append("")

    lines.append("endpackage : silicaflux_config_pkg")
    lines.append("")
    return "\n".join(lines)
