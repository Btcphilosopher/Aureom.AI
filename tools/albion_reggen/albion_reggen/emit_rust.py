"""Rust firmware interface: ``sf_regs.rs`` (+ ``sf_regs_examples.rs``).

Design
------
* All register access goes through the :class:`RegBus` trait.  The only
  ``unsafe`` code in the generated file is ``Mmio``, which performs a single
  volatile access after checking natural alignment and that the bus address
  fits a pointer; its constructor is ``unsafe`` and documents the contract.
  Tests and simulators implement ``RegBus`` safely.
* A register value is a newtype (``Value``) with field getters and checked
  builders: setting a field to a value that does not fit returns
  ``FieldOverflow`` instead of silently truncating.
* Read-modify-write helpers preserve only ``rw`` bits (``RW_MASK``); bits of
  write-one-to-clear / write-one-to-set / pulse fields are written as 0.
  Registers with read side effects or stored write-only fields get none.
* Array registers take an index and return ``Err(Error::Index(..))`` when it
  is out of range.
"""

from __future__ import annotations

from typing import Dict, List

from . import GENERATOR_NAME, SCHEMA_VERSION, __version__
from .examples import render_steps_rust
from .model import Field, Peripheral, RegInst, RegMap, Register


def header_rs(m: RegMap, what: str) -> str:
    return (
        f"// {what}\n"
        "// GENERATED FILE - DO NOT EDIT.  Edit the register definition instead.\n"
        f"// generator       : {GENERATOR_NAME} {__version__} (definition schema {SCHEMA_VERSION})\n"
        f"// register map    : {m.name} v{m.version[0]}.{m.version[1]}\n"
        f"// semantic hash   : {m.semantic_hash}\n"
        f"// definition hash : {m.definition_hash}\n")


def _u(width: int, v: int) -> str:
    return f"0x{v:x}_u{width}"


PRELUDE = r"""
#![allow(dead_code, unused_imports)]

/// A field value does not fit the field.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FieldOverflow {
    pub field: &'static str,
    pub value: u64,
    pub max: u64,
}

/// An array register index is out of range.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IndexError {
    pub index: usize,
    pub count: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Error {
    Overflow(FieldOverflow),
    Index(IndexError),
}

impl From<FieldOverflow> for Error {
    fn from(e: FieldOverflow) -> Self {
        Error::Overflow(e)
    }
}

impl From<IndexError> for Error {
    fn from(e: IndexError) -> Self {
        Error::Index(e)
    }
}

/// A register bus.  Addresses are 64-bit bus addresses; 32-bit registers are accessed with one
/// naturally aligned 32-bit access.  The 64-bit operations have default implementations made of
/// two 32-bit accesses (two bus transactions: not atomic).  `read64_stable` re-reads until the
/// high word is stable, which is what a free-running counter needs.
pub trait RegBus {
    fn read32(&self, addr: u64) -> u32;
    fn write32(&self, addr: u64, value: u32);

    fn read64(&self, addr: u64) -> u64 {
        let lo = self.read32(addr) as u64;
        let hi = self.read32(addr + 4) as u64;
        (hi << 32) | lo
    }

    fn read64_stable(&self, addr: u64) -> u64 {
        loop {
            let hi = self.read32(addr + 4);
            let lo = self.read32(addr);
            if self.read32(addr + 4) == hi {
                return ((hi as u64) << 32) | lo as u64;
            }
        }
    }

    fn write64(&self, addr: u64, value: u64) {
        self.write32(addr, value as u32);
        self.write32(addr + 4, (value >> 32) as u32);
    }
}

/// Memory-mapped register access: one volatile, naturally aligned access per call.
pub struct Mmio {
    _private: (),
}

impl Mmio {
    /// # Safety
    /// The caller guarantees that every register address of this map is mapped at its bus address
    /// in the current address space, that accessing it has only the documented hardware effects,
    /// and that no other code races on these registers in a way the hardware does not allow.
    pub const unsafe fn new() -> Self {
        Mmio { _private: () }
    }

    fn ptr<T>(addr: u64) -> *mut T {
        let a = usize::try_from(addr).expect("register address does not fit a pointer");
        assert!(a % core::mem::align_of::<T>() == 0, "misaligned register access");
        a as *mut T
    }
}

impl RegBus for Mmio {
    fn read32(&self, addr: u64) -> u32 {
        // SAFETY: Mmio::new's contract; the pointer is aligned and fits usize (checked in ptr).
        unsafe { core::ptr::read_volatile(Self::ptr::<u32>(addr)) }
    }

    fn write32(&self, addr: u64, value: u32) {
        // SAFETY: as above.
        unsafe { core::ptr::write_volatile(Self::ptr::<u32>(addr), value) }
    }

    #[cfg(target_pointer_width = "64")]
    fn read64(&self, addr: u64) -> u64 {
        // SAFETY: as above; 8-byte alignment is checked in ptr.
        unsafe { core::ptr::read_volatile(Self::ptr::<u64>(addr)) }
    }

    #[cfg(target_pointer_width = "64")]
    fn read64_stable(&self, addr: u64) -> u64 {
        self.read64(addr)
    }

    #[cfg(target_pointer_width = "64")]
    fn write64(&self, addr: u64, value: u64) {
        // SAFETY: as above.
        unsafe { core::ptr::write_volatile(Self::ptr::<u64>(addr), value) }
    }
}

/// Address, width and reset value of every register instance (array elements expanded).
#[derive(Debug, Clone, Copy)]
pub struct RegInfo {
    pub periph: &'static str,
    pub name: &'static str,
    pub addr: u64,
    pub width: u32,
    pub reset: u64,
}

#[derive(Debug, Clone, Copy)]
pub struct PeriphInfo {
    pub name: &'static str,
    pub base: u64,
    pub size: u64,
}
"""


def _reg_rs(p: Peripheral, r: Register, L: List[str]) -> None:
    w = r.width
    T = f"u{w}"
    arr = r.count > 1
    mod = r.name.lower()
    rd = "read32" if w == 32 else ("read64_stable" if not any(f.access != "ro" for f in r.fields) else "read64")
    wr = "write32" if w == 32 else "write64"
    L.append(f"    /// {p.name}.{r.name}{' (array of ' + str(r.count) + ')' if arr else ''}: {w}-bit at offset {r.offset:#x}"
             + (f" - {r.description}" if r.description else ""))
    L.append(f"    pub mod {mod} {{")
    L.append("        use super::super::{Error, FieldOverflow, IndexError, RegBus};")
    L.append("        use super::BASE;")
    L.append(f"        pub const OFFSET: u64 = {r.offset:#x};")
    L.append("        pub const ADDR: u64 = BASE + OFFSET;")
    L.append(f"        pub const WIDTH: u32 = {w};")
    L.append(f"        pub const RESET: {T} = {_u(w, r.reset)};")
    L.append(f"        pub const RW_MASK: {T} = {_u(w, r.mask_of('rw'))};")
    if arr:
        L.append(f"        pub const COUNT: usize = {r.count};")
        L.append(f"        pub const STRIDE: u64 = {r.stride};")
        L.append("        pub fn addr(index: usize) -> Result<u64, Error> {")
        L.append("            if index >= COUNT {")
        L.append("                return Err(Error::Index(IndexError { index, count: COUNT }));")
        L.append("            }")
        L.append("            Ok(ADDR + (index as u64) * STRIDE)")
        L.append("        }")
    L.append("        pub mod fields {")
    for f in r.fields:
        L.append(f"            /// {f.name} [{f.msb}:{f.lsb}] {f.access}" + (f" - {f.description}" if f.description else ""))
        L.append(f"            pub mod {f.name.lower()} {{")
        L.append(f"                pub const SHIFT: u32 = {f.lsb};")
        L.append(f"                pub const WIDTH: u32 = {f.width};")
        L.append(f"                pub const MASK: u{w} = {_u(w, f.mask)};")
        L.append(f"                pub const MAX: u{w} = {_u(w, (1 << f.width) - 1)};")
        L.append(f"                pub const RESET: u{w} = {_u(w, f.reset)};")
        L.append("            }")
    L.append("        }")
    L.append("        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]")
    L.append(f"        pub struct Value(pub {T});")
    L.append("        impl Value {")
    L.append("            pub const RESET: Value = Value(RESET);")
    L.append(f"            pub const fn raw(self) -> {T} {{ self.0 }}")
    for f in r.fields:
        fl = f.name.lower()
        if f.access in ("ro", "rw", "w1c", "w1s"):
            L.append(f"            pub const fn {fl}(self) -> {T} {{ (self.0 & fields::{fl}::MASK) >> fields::{fl}::SHIFT }}")
        if f.access in ("rw", "wo", "w1c", "w1s", "w1p"):
            L.append(f"            pub const fn with_{fl}(self, v: {T}) -> Result<Value, FieldOverflow> {{")
            L.append(f"                if v > fields::{fl}::MAX {{")
            L.append(f"                    return Err(FieldOverflow {{ field: \"{f.name}\", value: v as u64, max: fields::{fl}::MAX as u64 }});")
            L.append("                }")
            L.append(f"                Ok(Value((self.0 & !fields::{fl}::MASK) | (v << fields::{fl}::SHIFT)))")
            L.append("            }")
    L.append("        }")
    ia = ", index: usize" if arr else ""
    ib = ", index" if arr else ""
    addr = "addr(index)?" if arr else "ADDR"
    ret = "Result<Value, Error>" if arr else "Value"
    if r.readable:
        L.append(f"        pub fn read<B: RegBus>(bus: &B{ia}) -> {ret} {{")
        if arr:
            L.append(f"            Ok(Value(bus.{rd}({addr})))")
        else:
            L.append(f"            Value(bus.{rd}({addr}))")
        L.append("        }")
    if r.writable:
        wret = "Result<(), Error>" if arr else "()"
        L.append(f"        pub fn write<B: RegBus>(bus: &B{ia}, value: Value) -> {wret} {{")
        if arr:
            L.append(f"            bus.{wr}({addr}, value.0);")
            L.append("            Ok(())")
        else:
            L.append(f"            bus.{wr}({addr}, value.0)")
        L.append("        }")
    safe = r.rmw_safe and r.readable and r.writable
    q = "?" if arr else ""
    for f in r.fields:
        fl = f.name.lower()
        if f.access == "rw" and safe:
            L.append(f"        /// Read-modify-write of rw field {f.name}; only rw bits are written back.")
            L.append(f"        pub fn set_{fl}<B: RegBus>(bus: &B{ia}, v: {T}) -> Result<(), Error> {{")
            L.append(f"            let new = Value(read(bus{ib}){q}.0 & RW_MASK).with_{fl}(v)?;")
            L.append(f"            write(bus{ib}, new){q};")
            L.append("            Ok(())")
            L.append("        }")
        elif f.access in ("w1c", "w1s", "w1p") and r.writable and r.rmw_safe:
            verb = {"w1c": "clear", "w1s": "raise", "w1p": "pulse"}[f.access]
            L.append(f"        /// Write 1 to the chosen bits of {f.name} ({f.access}); other rw fields keep their value, other write-one fields get 0.")
            L.append(f"        pub fn {verb}_{fl}<B: RegBus>(bus: &B{ia}, bits: {T}) -> Result<(), Error> {{")
            if r.mask_of("rw"):
                L.append(f"            let cur = Value(read(bus{ib}){q}.0 & RW_MASK);")
            else:
                L.append("            let cur = Value(0);")
            L.append(f"            let new = Value(cur.0 | Value(0).with_{fl}(bits)?.0);")
            L.append(f"            write(bus{ib}, new){q};")
            L.append("            Ok(())")
            L.append("        }")
    L.append("    }")
    L.append("")


def emit_rust(m: RegMap) -> str:
    L: List[str] = [header_rs(m, "sf_regs.rs - register definitions and safe accessors"),
                    "//! Register map `" + m.name + "`. Include with `mod sf_regs;`."]
    L.append(PRELUDE)
    L.append(f"pub const MAP_NAME: &str = \"{m.name}\";")
    L.append(f"pub const VERSION: (u16, u16) = ({m.version[0]}, {m.version[1]});")
    L.append("/// Equals the value of SYSID.REGMAP_HASH in hardware built from this definition.")
    L.append(f"pub const MAP_HASH: u64 = 0x{m.hash64:016x};")
    L.append(f"pub const SEMANTIC_HASH: &str = \"{m.semantic_hash}\";")
    L.append(f"pub const DEFINITION_HASH: &str = \"{m.definition_hash}\";")
    L.append("")
    L.append("pub const PERIPHS: &[PeriphInfo] = &[")
    for p in m.peripherals:
        L.append(f"    PeriphInfo {{ name: \"{p.name}\", base: 0x{p.base:x}, size: 0x{p.size:x} }},")
    L.append("];")
    L.append("")
    L.append("pub const REGS: &[RegInfo] = &[")
    for i in m.instances:
        nm = i.reg.name if i.reg.count == 1 else f"{i.reg.name}_{i.elem}"
        L.append(f"    RegInfo {{ periph: \"{i.periph.name}\", name: \"{nm}\", addr: 0x{i.addr:x}, width: {i.reg.width}, reset: 0x{i.reg.reset:x} }},")
    L.append("];")
    L.append("")
    for p in m.peripherals:
        L.append(f"/// {p.name}: {p.description}")
        L.append(f"pub mod {p.name} {{")
        L.append(f"    pub const BASE: u64 = 0x{p.base:x};")
        L.append(f"    pub const SIZE: u64 = 0x{p.size:x};")
        for r in p.registers:
            _reg_rs(p, r, L)
        L.append("}")
        L.append("")
    sysid = next((p for p in m.peripherals if p.name == "sysid"), None)
    h = next((r for r in sysid.registers if r.name == "REGMAP_HASH"), None) if sysid else None
    if h is not None and h.width == 64:
        L.append("/// True if the hardware's REGMAP_HASH equals the definition this file was generated from.")
        L.append("pub fn hardware_matches<B: RegBus>(bus: &B) -> bool {")
        L.append("    sysid::regmap_hash::read(bus).0 == MAP_HASH")
        L.append("}")
    return "\n".join(L) + "\n"


def emit_examples(m: RegMap) -> str:
    L: List[str] = [header_rs(m, "sf_regs_examples.rs - firmware examples generated from the definition's example steps"),
                    "// Declare next to sf_regs:   mod sf_regs;  mod sf_regs_examples;",
                    "#![allow(dead_code, unused_imports)]",
                    "use super::sf_regs as regs;",
                    "use regs::RegBus;", "",
                    "#[derive(Debug, PartialEq, Eq)]",
                    "pub enum ExampleError {",
                    "    Mismatch,",
                    "    Timeout,",
                    "    Bus(regs::Error),",
                    "}", "",
                    "impl From<regs::Error> for ExampleError {",
                    "    fn from(e: regs::Error) -> Self {",
                    "        ExampleError::Bus(e)",
                    "    }",
                    "}", ""]
    for p in m.peripherals:
        for k, ex in enumerate(p.examples):
            L.append(f"/// {p.name}: {ex['title']}")
            L.append(f"pub fn example_{p.name}_{k}<B: RegBus>(bus: &B) -> Result<(), ExampleError> {{")
            L.extend("    " + ln for ln in render_steps_rust(m, p, ex["steps"]))
            L.append("    Ok(())")
            L.append("}")
            L.append("")
    return "\n".join(L) + "\n"


def emit_all(m: RegMap) -> Dict[str, str]:
    return {"sf_regs.rs": emit_rust(m), "sf_regs_examples.rs": emit_examples(m)}
