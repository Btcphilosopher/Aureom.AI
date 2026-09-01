"""
SilicaFlux architecture layer for the Bitcoin SHA-256 mining ASIC.

    silicaflux.architecture   Declarative architecture spec (dataclasses)
    silicaflux.ir             Hardware intermediate representation
    silicaflux.compiler       spec -> IR lowering + validation
    silicaflux.generators     IR -> SystemVerilog emission

This package does NOT implement the hashing datapath. It describes and
validates *configuration* of the hand-written, independently-verified
RTL in rtl/ (core count, pipeline depth, message-schedule architecture,
nonce allocation, telemetry, clock domains) and deterministically
compiles that configuration down to a generated SystemVerilog parameter
package (rtl/generated/silicaflux_config_pkg.sv) that the RTL imports.
See docs/silicaflux_ir.md.
"""
