"""C firmware interface: ``sf_regs.h`` and ``sf_regs_examples.h``.

Safety properties of the generated API
--------------------------------------
* Every register address is checked at compile time to be naturally aligned
  for its width (``SF_REGS_STATIC_ASSERT``); the generated accessors are the
  only intended way to touch a register, and they use exactly one naturally
  aligned access of the register's width.
* Read-modify-write helpers write back **only** the bits of ``rw`` fields
  (``*_RW_MASK``).  Bits of write-one-to-clear / write-one-to-set / pulse
  fields and read-only bits are written as 0, which has no effect, so a field
  update can never clear an unrelated interrupt flag or fire a command.
  Registers where a read-back cannot be trusted (read side effects, or
  write-only stored fields) get no RMW helpers at all.
* Array accessors check the index and call ``SF_REGS_FAULT()`` (default: trap).
* 64-bit registers use one 64-bit access where the CPU has one; otherwise two
  32-bit accesses (low word first for writes; high-low-high for read-only
  counters so a carry between the halves cannot produce a torn value).
"""

from __future__ import annotations

from typing import Dict, List

from . import GENERATOR_NAME, SCHEMA_VERSION, __version__
from .examples import render_steps_c
from .model import Field, Peripheral, RegInst, RegMap, Register


def _comment(s: str) -> str:
    return s.replace("*/", "* /")


def header_c(m: RegMap, what: str) -> str:
    return (
        "/*\n"
        f" * {what}\n"
        " * GENERATED FILE - DO NOT EDIT.  Edit the register definition instead.\n"
        f" * generator       : {GENERATOR_NAME} {__version__} (definition schema {SCHEMA_VERSION})\n"
        f" * register map    : {m.name} v{m.version[0]}.{m.version[1]}\n"
        f" * semantic hash   : {m.semantic_hash}\n"
        f" * definition hash : {m.definition_hash}\n"
        " */\n")


def _t(width: int) -> str:
    return "uint32_t" if width == 32 else "uint64_t"


def _lit(width: int, v: int) -> str:
    return f"UINT32_C(0x{v:x})" if width == 32 else f"UINT64_C(0x{v:x})"


def _fn(p: Peripheral, r: Register) -> str:
    return f"sf_{p.name}_{r.name.lower()}"


def _mac(p: Peripheral, r: Register) -> str:
    return f"SF_{p.name.upper()}_{r.name}"


PRELUDE = r"""
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifdef __cplusplus
#define SF_REGS_STATIC_ASSERT(c, m) static_assert(c, m)
#else
#define SF_REGS_STATIC_ASSERT(c, m) _Static_assert(c, m)
#endif

/* A violated precondition (array index out of range) must never be silent. */
#ifndef SF_REGS_FAULT
#if defined(__GNUC__) || defined(__clang__)
#define SF_REGS_FAULT() __builtin_trap()
#else
#define SF_REGS_FAULT() do { for (;;) { } } while (0)
#endif
#endif

/* Native 64-bit register access is used when pointers are 64 bits wide, unless overridden. */
#ifndef SF_REGS_NATIVE64
#if defined(UINTPTR_MAX) && (UINTPTR_MAX > 0xffffffffu)
#define SF_REGS_NATIVE64 1
#else
#define SF_REGS_NATIVE64 0
#endif
#endif

/*
 * Bus access primitives.  By default registers are accessed with volatile loads and stores
 * through a pointer.  A project that needs a remapped window, a simulator, or a mock can define
 * SF_REGS_CUSTOM_ACCESS and provide these four functions itself:
 *     uint32_t sf_regs_rd32_(uint64_t addr);   void sf_regs_wr32_(uint64_t addr, uint32_t v);
 *     uint64_t sf_regs_rd64n_(uint64_t addr);  void sf_regs_wr64n_(uint64_t addr, uint64_t v);
 * (the *64n_ pair is only called when SF_REGS_NATIVE64 is 1).
 */
#ifndef SF_REGS_CUSTOM_ACCESS
static inline uintptr_t sf_regs_ptr_(uint64_t addr)
{
#if UINTPTR_MAX < UINT64_MAX
    if (addr > (uint64_t)UINTPTR_MAX) {
        SF_REGS_FAULT();   /* the bus address does not fit a pointer: remap via SF_REGS_CUSTOM_ACCESS */
    }
#endif
    return (uintptr_t)addr;
}
static inline uint32_t sf_regs_rd32_(uint64_t addr)
{
    const uintptr_t p = sf_regs_ptr_(addr);
    return *(volatile uint32_t *)p;
}
static inline void sf_regs_wr32_(uint64_t addr, uint32_t v)
{
    const uintptr_t p = sf_regs_ptr_(addr);
    *(volatile uint32_t *)p = v;
}
static inline uint64_t sf_regs_rd64n_(uint64_t addr)
{
    const uintptr_t p = sf_regs_ptr_(addr);
    return *(volatile uint64_t *)p;
}
static inline void sf_regs_wr64n_(uint64_t addr, uint64_t v)
{
    const uintptr_t p = sf_regs_ptr_(addr);
    *(volatile uint64_t *)p = v;
}
#endif

/* 64-bit read of a register whose value can change under us (counters): high-low-high. */
static inline uint64_t sf_regs_rd64_stable_(uint64_t addr)
{
#if SF_REGS_NATIVE64
    return sf_regs_rd64n_(addr);
#else
    uint32_t hi, lo, hi2;
    do {
        hi = sf_regs_rd32_(addr + 4u);
        lo = sf_regs_rd32_(addr);
        hi2 = sf_regs_rd32_(addr + 4u);
    } while (hi != hi2);
    return ((uint64_t)hi << 32) | lo;
#endif
}

/* 64-bit read of any other register: one access if native, else low then high. */
static inline uint64_t sf_regs_rd64_(uint64_t addr)
{
#if SF_REGS_NATIVE64
    return sf_regs_rd64n_(addr);
#else
    uint32_t lo = sf_regs_rd32_(addr);
    uint32_t hi = sf_regs_rd32_(addr + 4u);
    return ((uint64_t)hi << 32) | lo;
#endif
}

/* 64-bit write: one access if native, else low word then high word (two bus transactions). */
static inline void sf_regs_wr64_(uint64_t addr, uint64_t v)
{
#if SF_REGS_NATIVE64
    sf_regs_wr64n_(addr, v);
#else
    sf_regs_wr32_(addr, (uint32_t)v);
    sf_regs_wr32_(addr + 4u, (uint32_t)(v >> 32));
#endif
}
"""


def _reg_c(p: Peripheral, r: Register, addr0: int, L: List[str]) -> None:
    w = r.width
    T = _t(w)
    mac = _mac(p, r)
    fn = _fn(p, r)
    arr = r.count > 1
    idx_p = "unsigned i" if arr else "void"
    idx_c = "i, " if arr else ""
    idx_a = "unsigned i, " if arr else ""
    rd_fn = "sf_regs_rd32_" if w == 32 else (
        "sf_regs_rd64_stable_" if not any(f.access != "ro" for f in r.fields) else "sf_regs_rd64_")
    wr_fn = "sf_regs_wr32_" if w == 32 else "sf_regs_wr64_"
    L.append(f"/* {p.name}.{r.name}{'[' + str(r.count) + ']' if arr else ''}: {w}-bit"
             + (f" array of {r.count}, stride {r.stride}" if arr else "") + f" @ offset {r.offset:#x}"
             + (f" - {_comment(r.description)}" if r.description else "") + " */")
    L.append(f"#define {mac}_OFFSET {_lit(64, r.offset).replace('UINT32_C', 'UINT64_C')}")
    L.append(f"#define {mac}_ADDR {_lit(64, addr0).replace('UINT32_C', 'UINT64_C')}")
    L.append(f"#define {mac}_WIDTH {w}u")
    L.append(f"#define {mac}_RESET {_lit(w, r.reset)}")
    L.append(f"#define {mac}_RW_MASK {_lit(w, r.mask_of('rw'))}")
    if arr:
        L.append(f"#define {mac}_COUNT {r.count}u")
        L.append(f"#define {mac}_STRIDE UINT64_C({r.stride})")
    L.append(f"SF_REGS_STATIC_ASSERT(({mac}_ADDR % {r.nbytes}u) == 0u, \"{p.name}.{r.name} is not naturally aligned\");")
    for f in r.fields:
        fm = f"{mac}_{f.name}"
        L.append(f"#define {fm}_SHIFT {f.lsb}u")
        L.append(f"#define {fm}_WIDTH {f.width}u")
        L.append(f"#define {fm}_MASK {_lit(w, f.mask)}")
        L.append(f"#define {fm}_RESET {_lit(w, f.reset)}")
    # address and access
    if arr:
        L.append(f"static inline uint64_t {fn}_addr(unsigned i)")
        L.append("{")
        L.append(f"    if (i >= {mac}_COUNT) {{ SF_REGS_FAULT(); }}")
        L.append(f"    return {mac}_ADDR + (uint64_t)i * {mac}_STRIDE;")
        L.append("}")
        addr_expr = f"{fn}_addr(i)"
    else:
        addr_expr = f"{mac}_ADDR"
    if r.readable:
        L.append(f"static inline {T} {fn}_read({idx_p})")
        L.append("{")
        L.append(f"    return {rd_fn}({addr_expr});")
        L.append("}")
    if r.writable:
        L.append(f"static inline void {fn}_write({idx_a}{T} value)")
        L.append("{")
        L.append(f"    {wr_fn}({addr_expr}, value);")
        L.append("}")
    safe = r.rmw_safe and r.readable and r.writable
    for f in r.fields:
        fm = f"{mac}_{f.name}"
        fl = f.name.lower()
        if f.access in ("ro", "rw", "w1c", "w1s"):
            L.append(f"static inline {T} {fn}_get_{fl}({T} reg)")
            L.append("{")
            L.append(f"    return (reg & {fm}_MASK) >> {fm}_SHIFT;")
            L.append("}")
        if f.access in ("rw", "wo", "w1c", "w1s", "w1p"):
            L.append(f"static inline {T} {fn}_{fl}_encode({T} value)")
            L.append("{")
            L.append(f"    return (({T})(value) << {fm}_SHIFT) & {fm}_MASK;")
            L.append("}")
        # read-modify-write style helpers
        if f.access == "rw" and safe:
            L.append(f"/* RMW of rw field {f.name}: only rw bits are written back; w1c/w1s/w1p/ro bits are written as 0 (no effect). */")
            L.append(f"static inline void {fn}_set_{fl}({idx_a}{T} value)")
            L.append("{")
            L.append(f"    {T} v = {fn}_read({'i' if arr else ''}) & {mac}_RW_MASK;")
            L.append(f"    v = (v & ~{fm}_MASK) | {fn}_{fl}_encode(value);")
            L.append(f"    {fn}_write({idx_c}v);")
            L.append("}")
        elif f.access in ("w1c", "w1s", "w1p") and r.writable and r.rmw_safe:
            verb = {"w1c": "clear", "w1s": "raise", "w1p": "pulse"}[f.access]
            L.append(f"/* {f.access}: write 1 to the chosen bits of {f.name} ({verb}); other rw fields keep their value, other write-one fields get 0. */")
            L.append(f"static inline void {fn}_{verb}_{fl}({idx_a}{T} bits)")
            L.append("{")
            if r.mask_of("rw"):
                L.append(f"    {T} v = {fn}_read({'i' if arr else ''}) & {mac}_RW_MASK;")
                L.append(f"    {fn}_write({idx_c}v | {fn}_{fl}_encode(bits));")
            else:
                L.append(f"    {fn}_write({idx_c}{fn}_{fl}_encode(bits));")
            L.append("}")
    L.append("")


def emit_header(m: RegMap) -> str:
    L: List[str] = [header_c(m, "sf_regs.h - register definitions and safe accessors"),
                    "#ifndef SF_REGS_H", "#define SF_REGS_H", PRELUDE]
    L.append(f"#define SF_REGS_MAP_NAME \"{m.name}\"")
    L.append(f"#define SF_REGS_VERSION_MAJOR {m.version[0]}u")
    L.append(f"#define SF_REGS_VERSION_MINOR {m.version[1]}u")
    L.append(f"/* equals the value of SYSID.REGMAP_HASH in hardware built from this definition */")
    L.append(f"#define SF_REGS_MAP_HASH UINT64_C(0x{m.hash64:016x})")
    L.append(f"#define SF_REGS_SEMANTIC_HASH \"{m.semantic_hash}\"")
    L.append(f"#define SF_REGS_DEFINITION_HASH \"{m.definition_hash}\"")
    L.append(f"#define SF_REGS_NUM_PERIPHERALS {len(m.peripherals)}u")
    L.append(f"#define SF_REGS_NUM_REGISTERS {len(m.instances)}u\n")
    L.append("/* ===== address map ===== */")
    for p in m.peripherals:
        n = p.name.upper()
        L.append(f"#define SF_{n}_BASE UINT64_C(0x{p.base:x})")
        L.append(f"#define SF_{n}_SIZE UINT64_C(0x{p.size:x})")
    L.append("")
    L.append("/* X-macro tables for tools and tests: X(periph, base, size) and X(periph, REG, address, width, reset) */")
    L.append("#define SF_REGS_PERIPH_LIST(X) \\")
    for p in m.peripherals:
        L.append(f"    X({p.name}, UINT64_C(0x{p.base:x}), UINT64_C(0x{p.size:x})) \\")
    L.append("    /* end */")
    L.append("#define SF_REGS_REG_LIST(X) \\")
    for i in m.instances:
        nm = i.reg.name if i.reg.count == 1 else f"{i.reg.name}_{i.elem}"
        L.append(f"    X({i.periph.name}, {nm}, UINT64_C(0x{i.addr:x}), {i.reg.width}, {_lit(i.reg.width, i.reg.reset)}) \\")
    L.append("    /* end */\n")
    L.append("/* ===== registers ===== */\n")
    for p in m.peripherals:
        L.append(f"/* ---------- {p.name}: {_comment(p.description)} ---------- */")
        L.append(f"/* region {p.region}; window {p.base:#x} + {p.size:#x}" + (" ; privileged access only" if m.periph_attr_byte(p) & 0x8 else "") + " */\n")
        for r in p.registers:
            _reg_c(p, r, p.base + r.offset, L)
    # sysid check
    sysid = next((p for p in m.peripherals if p.name == "sysid"), None)
    h = next((r for r in sysid.registers if r.name == "REGMAP_HASH"), None) if sysid else None
    if h is not None and h.width == 64:
        L.append("/* Returns 1 if the hardware's REGMAP_HASH equals the definition this header was generated from. */")
        L.append("static inline int sf_regs_hardware_matches(void)")
        L.append("{")
        L.append("    return sf_sysid_regmap_hash_read() == SF_REGS_MAP_HASH;")
        L.append("}")
        L.append("")
    L.append("#ifdef __cplusplus")
    L.append("}")
    L.append("#endif")
    L.append("#endif /* SF_REGS_H */")
    return "\n".join(L) + "\n"


def emit_examples(m: RegMap) -> str:
    L: List[str] = [header_c(m, "sf_regs_examples.h - firmware examples generated from the definition's example steps"),
                    "#ifndef SF_REGS_EXAMPLES_H", "#define SF_REGS_EXAMPLES_H", '#include "sf_regs.h"', ""]
    L.append("/* Each function returns 0 on success, -1 if an expected value differs, -2 if a poll times out. */")
    for p in m.peripherals:
        for k, ex in enumerate(p.examples):
            L.append(f"/* {p.name}: {_comment(ex['title'])} */")
            L.append(f"static inline int sf_example_{p.name}_{k}(void)")
            L.append("{")
            L.extend("    " + ln for ln in render_steps_c(m, p, ex["steps"]))
            L.append("    return 0;")
            L.append("}")
            L.append("")
    L.append("#endif /* SF_REGS_EXAMPLES_H */")
    return "\n".join(L) + "\n"


def emit_all(m: RegMap) -> Dict[str, str]:
    return {"sf_regs.h": emit_header(m), "sf_regs_examples.h": emit_examples(m)}
