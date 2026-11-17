"""Firmware example steps -> C, Rust and prose.

An example is *data* in the register definition (``examples:``), validated
against the model (register and field exist, the access type fits the step).
The same validated steps are rendered three ways, so the code shown in the
documentation is the code that the tests compile -- it cannot drift from the
register map.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .model import Field, Peripheral, RegMap, Register


def _lookup(p: Peripheral, st: Dict[str, Any]):
    reg = next(r for r in p.registers if r.name == st["reg"])
    fld = next((f for f in reg.fields if f.name == st.get("field")), None) if st.get("field") else None
    return reg, fld


def _clit(width: int, v: int) -> str:
    return f"UINT32_C(0x{v:x})" if width == 32 else f"UINT64_C(0x{v:x})"


# ------------------------------------------------------------------ C
def render_steps_c(m: RegMap, p: Peripheral, steps: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for st in steps:
        if st["op"] == "comment":
            out.append(f"/* {st['text'].replace('*/', '* /')} */")
            continue
        reg, fld = _lookup(p, st)
        fn = f"sf_{p.name}_{reg.name.lower()}"
        mac = f"SF_{p.name.upper()}_{reg.name}"
        idx = f"{st['index']}u, " if reg.count > 1 else ""
        idx0 = f"{st['index']}u" if reg.count > 1 else ""
        op = st["op"]
        if op == "write":
            out.append(f"{fn}_write({idx}{_clit(reg.width, st['value'])});")
        elif op == "read":
            out.append(f"(void){fn}_read({idx0});")
        elif op == "set":
            out.append(f"{fn}_set_{fld.name.lower()}({idx}{_clit(reg.width, st['value'])});")
        elif op in ("trigger", "clear"):
            verb = {"w1p": "pulse", "w1s": "raise", "w1c": "clear"}[fld.access]
            ones = f"{mac}_{fld.name}_MASK >> {mac}_{fld.name}_SHIFT"
            out.append(f"{fn}_{verb}_{fld.name.lower()}({idx}{ones});")
        elif op == "expect":
            out.append(f"if ({fn}_get_{fld.name.lower()}({fn}_read({idx0})) != {_clit(reg.width, st['value'])}) {{ return -1; }}")
        elif op == "poll":
            out.append("{")
            out.append("    unsigned polls_ = 0u;")
            out.append(f"    while ({fn}_get_{fld.name.lower()}({fn}_read({idx0})) != {_clit(reg.width, st['value'])}) {{")
            out.append(f"        if (++polls_ >= {st['max']}u) {{ return -2; }}")
            out.append("    }")
            out.append("}")
    return out


# --------------------------------------------------------------- Rust
def _rlit(width: int, v: int) -> str:
    return f"0x{v:x}_u{width}"


def render_steps_rust(m: RegMap, p: Peripheral, steps: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for st in steps:
        if st["op"] == "comment":
            out.append(f"// {st['text']}")
            continue
        reg, fld = _lookup(p, st)
        path = f"regs::{p.name}::{reg.name.lower()}"
        arr = reg.count > 1
        i = f"{st['index']}" if arr else ""
        ai = f", {i}" if arr else ""
        q = "?" if arr else ""
        op = st["op"]
        if op == "write":
            out.append(f"{path}::write(bus{ai}, {path}::Value({_rlit(reg.width, st['value'])})){q};")
        elif op == "read":
            out.append(f"let _ = {path}::read(bus{ai}){q};")
        elif op == "set":
            out.append(f"{path}::set_{fld.name.lower()}(bus{ai}, {_rlit(reg.width, st['value'])})?;")
        elif op in ("trigger", "clear"):
            verb = {"w1p": "pulse", "w1s": "raise", "w1c": "clear"}[fld.access]
            out.append(f"{path}::{verb}_{fld.name.lower()}(bus{ai}, {path}::fields::{fld.name.lower()}::MASK >> {path}::fields::{fld.name.lower()}::SHIFT)?;")
        elif op == "expect":
            out.append(f"if {path}::read(bus{ai}){q}.{fld.name.lower()}() != {_rlit(reg.width, st['value'])} {{ return Err(ExampleError::Mismatch); }}")
        elif op == "poll":
            out.append("{")
            out.append("    let mut polls: u32 = 0;")
            out.append(f"    while {path}::read(bus{ai}){q}.{fld.name.lower()}() != {_rlit(reg.width, st['value'])} {{")
            out.append("        polls += 1;")
            out.append(f"        if polls >= {st['max']} {{ return Err(ExampleError::Timeout); }}")
            out.append("    }")
            out.append("}")
    return out


# --------------------------------------------------------------- prose
def render_steps_text(p: Peripheral, steps: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for st in steps:
        if st["op"] == "comment":
            out.append(f"- *{st['text']}*")
            continue
        tgt = f"`{p.name}.{st['reg']}" + (f"[{st['index']}]" if next(r for r in p.registers if r.name == st['reg']).count > 1 else "") \
              + (f".{st['field']}`" if st.get("field") else "`")
        op = st["op"]
        if op == "write":
            out.append(f"- write {tgt} = `{st['value']:#x}`")
        elif op == "read":
            out.append(f"- read {tgt}")
        elif op == "set":
            out.append(f"- set {tgt} = `{st['value']:#x}` (read-modify-write of rw bits only)")
        elif op == "trigger":
            out.append(f"- trigger {tgt} (write 1)")
        elif op == "clear":
            out.append(f"- clear {tgt} (write 1 to clear)")
        elif op == "expect":
            out.append(f"- check {tgt} == `{st['value']:#x}`")
        elif op == "poll":
            out.append(f"- poll until {tgt} == `{st['value']:#x}` (at most {st['max']} reads)")
    return out
