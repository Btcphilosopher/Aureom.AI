#!/usr/bin/env python3
"""sfx_asm -- SilicaFlux multi-format assembler.

Translates SilicaFlux assembly into memory images for simulation and FPGA
flows: Verilog $readmemh (.hex), raw binary (.bin), Quartus MIF (.mif) and
Xilinx COE (.coe).  Every format carries the identical 32-bit word image.

This module is the normative definition of the SilicaFlux v1 instruction
encoding.  ``--emit-pkg FILE`` renders the same tables as a SystemVerilog
package (silicaflux_isa_pkg) so silicaflux_pkg.sf, scheduler.sf,
compute_tile.sf and memory_controller.sf can import, or be diffed against,
a single source of truth.

ARCHITECTURAL STATE
  r0-r31  scalar registers, 32-bit; r0 reads as zero, writes are discarded
          aliases: zero=r0, sp=r30, ra=r31 (link register)
  v0-v31  vector registers, VLEN=128: .I8 = 16 lanes, .I16 = 8, .I32 = 4
  t0-t7   tensor accumulator tiles, 4x4 x int32 (4 beats of 128 bits, row/beat)
  pc      byte address; instructions are 32 bits wide and 4-byte aligned

INSTRUCTION WORD
   31    26 25   21 20   16 15   11 10    6 5      0
  +--------+-------+-------+-------+-------+--------+
  | opcode |   A   |   B   |   C   |   D   | funct6 |   R, X
  | opcode |   A   |   B   |         imm16          |   I, M, B, S
  | opcode |   A   |              imm21             |   JL
  | opcode |                 imm26                  |   J
  opcode[5:3] is the functional-unit dispatch port, so the scheduler routes an
  instruction without further decode; opcode[2:0] selects the operation.

FORMATS
  N   all non-opcode bits zero
  R   A=rd  B=rs1  C=rs2  D=rs3 / lane  funct6=function and modifiers
  I   A=rd  B=rs1  imm16 (sign- or zero-extended per opcode)
  M   A=data register  B=base  imm16 = signed byte offset
  B   A=rs1  B=rs2  imm16 = signed word displacement from the branch pc
  J   imm26 = signed word displacement from the jump pc
  JL  A=rd  imm21 = signed word displacement from the jump pc
  X   A=first vreg / tile  B=base  C=stride reg (r0 = packed)  D=beats-1
      funct6[0]=target (0 vector registers, 1 tensor tile)
  S   A=barrier id  B=0  imm16 = {fu_mask[15:8], scope[7:6], 6'b0}
  Reserved bits encode as zero and the decoder rejects words that set them.
  Word 0x00000000 (opcode 0x00) is the architectural ILLEGAL trap, so
  uninitialised memory never executes silently.

FUNCTIONAL UNITS (dispatch port = opcode[5:3])
  0 SCHED  scheduler / dataflow sync      4 LSU   scalar load/store
  1 ALU    scalar integer                 5 VLSU  vector + burst load/store
  2 VPU    vector SIMD                    6 BRU   branch / control flow
  3 TPU    tensor / matrix                7 XU    reserved extension port

MEMORY MODEL
  Byte addressed and little-endian: the byte at address A occupies bits
  [8*(A%4)+7 : 8*(A%4)] of word A/4.  LOAD_S/STORE_S move 32-bit words
  (offset a multiple of 4); LOAD_V/STORE_V move 128-bit vectors (offset a
  multiple of 16); BURST_LOAD/BURST_STORE move 1-32 beats of 128 bits through
  consecutive vector registers, or exactly 4 beats through a tensor tile, with
  an optional stride register for 2-D tiles.

ASSEMBLY LANGUAGE
  label:  MNEMONIC[.MOD...] op, op, ...     ; comment   (# and // also start one)
  registers   r0-r31 zero sp ra | v0-v31 | t0-t7   (reserved, never symbols)
  memory      [rs1]  [rs1 + expr]  [rs1 - expr]  [expr]  expr(rs1)  (rs1)
  vector lane vN[expr]
  numbers     123  0x7F  0b1010  0o17  'c'  (underscores allowed)
  operators   + - * / % << >> & | ^ ~ ( )  %hi(e)  %lo(e)  . (current address)
  directives  .text .data .section .org .align .word .half .byte .space .zero
              .ascii .asciz .string .equ .set NAME = expr .include .global .end
  Pass 1 parses every line, lays out the sections and defines symbols.
  Pass 2 evaluates expressions, encodes, re-decodes and re-encodes every word
  (round-trip verification) and builds the memory image.
  Section bases: .text = --text-base (default 0).  .data = --data-base, else
  the first .org in .data, else the end of .text rounded up to 16 bytes.

OUTPUT FORMATS (word i holds byte address base + 4*i; base = text base by default)
  .hex  $readmemh: '//' header lines, then one 8-digit hex word per line
  .bin  raw bytes, each word little-endian (memory byte order)
  .mif  Quartus MIF: WIDTH=32, DEPTH=words, hex word addresses, runs as [a..b]
  .coe  Xilinx COE: memory_initialization_radix=16, memory_initialization_vector

EXIT STATUS
  0 success, 1 assembly or image error, 2 usage or I/O error, 3 internal error
"""

from __future__ import annotations

import argparse
import difflib
import enum
import os
import random
import re
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence, Union, cast

__version__ = "1.0.0"
TOOL = "sfx_asm"

# =============================================================================
# Architectural parameters
# =============================================================================

ILEN = 32
WORD_BYTES = 4
WORD_MASK = 0xFFFF_FFFF
ADDR_MAX = 0xFFFF_FFFF
NUM_SREGS = 32
NUM_VREGS = 32
NUM_TREGS = 8
VLEN = 128
VLEN_BYTES = VLEN // 8
TILE_DIM = 4
TILE_BEATS = 4
MAX_BURST_BEATS = 32
REG_ZERO = 0
REG_SP = 30
REG_RA = 31
DATA_AUTO_ALIGN = 16
MAX_INCLUDE_DEPTH = 32
MAX_SPACE_BYTES = 1 << 24
MAX_ALIGN = 1 << 16
EXPR_LIMIT = 1 << 64


# =============================================================================
# Bit fields and explicit packing
# =============================================================================

@dataclass(frozen=True)
class BitField:
    """An inclusive [msb:lsb] slice of the 32-bit instruction word."""

    name: str
    msb: int
    lsb: int

    def __post_init__(self) -> None:
        if not 0 <= self.lsb <= self.msb < ILEN:
            raise ValueError(f"invalid bit field {self.name}[{self.msb}:{self.lsb}]")

    @property
    def width(self) -> int:
        return self.msb - self.lsb + 1

    @property
    def limit(self) -> int:
        return (1 << self.width) - 1

    @property
    def mask(self) -> int:
        return self.limit << self.lsb

    def extract(self, word: int) -> int:
        return (word >> self.lsb) & self.limit

    def __str__(self) -> str:
        return f"{self.name}[{self.msb}:{self.lsb}]"


F_OPCODE = BitField("opcode", 31, 26)
F_A = BitField("A", 25, 21)
F_B = BitField("B", 20, 16)
F_C = BitField("C", 15, 11)
F_D = BitField("D", 10, 6)
F_FUNCT = BitField("funct6", 5, 0)
F_IMM16 = BitField("imm16", 15, 0)
F_IMM21 = BitField("imm21", 20, 0)
F_IMM26 = BitField("imm26", 25, 0)
F_N_RSVD = BitField("rsvd", 25, 0)

F_SH_RSVD = BitField("sh_rsvd", 15, 7)
F_SH_TYPE = BitField("sh_type", 6, 5)
F_SH_AMT = BitField("shamt", 4, 0)

F_SYNC_MASK = BitField("fu_mask", 15, 8)
F_SYNC_SCOPE = BitField("scope", 7, 6)
F_SYNC_RSVD = BitField("sync_rsvd", 5, 0)

F_V_EW = BitField("ew", 5, 4)
F_V_SAT = BitField("sat", 3, 3)
F_V_UNS = BitField("uns", 2, 2)
F_V_OPX = BitField("opx", 1, 0)

F_T_ITYPE = BitField("itype", 5, 4)
F_T_RSVD = BitField("tpu_rsvd", 3, 1)
F_T_ACC = BitField("acc", 0, 0)

F_X_RSVD = BitField("burst_rsvd", 5, 1)
F_X_TGT = BitField("tgt", 0, 0)


class EncodingError(Exception):
    """A value violated a bit-field constraint inside the packer."""


def pack(*fields: tuple[BitField, int]) -> int:
    """Pack (field, value) pairs into a word with explicit shifts and masks.

    Every value must fit its field and no two fields may overlap; anything
    else is an encoder defect and raises EncodingError instead of silently
    corrupting neighbouring bits.
    """
    word = 0
    used = 0
    for fld, value in fields:
        if isinstance(value, bool) or not isinstance(value, int):
            raise EncodingError(f"non-integer value {value!r} for {fld}")
        if value < 0 or value > fld.limit:
            raise EncodingError(f"value {value} does not fit {fld} (0..{fld.limit})")
        if used & fld.mask:
            raise EncodingError(f"field {fld} overlaps an already packed field")
        word |= (value << fld.lsb) & fld.mask
        used |= fld.mask
    return word


def to_twos(value: int, bits: int) -> int:
    return value & ((1 << bits) - 1)


def from_twos(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


def _align_up(value: int, align: int) -> int:
    return (value + align - 1) // align * align


def _is_pow2(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


# =============================================================================
# Enumerations: functional units, opcodes, function codes, modifiers
# =============================================================================

class FU(enum.IntEnum):
    """Functional-unit dispatch port; always equal to opcode[5:3]."""

    SCHED = 0
    ALU = 1
    VPU = 2
    TPU = 3
    LSU = 4
    VLSU = 5
    BRU = 6
    XU = 7


FU_DESCRIPTION = {
    FU.SCHED: "scheduler / dataflow synchronisation",
    FU.ALU: "scalar integer ALU",
    FU.VPU: "vector SIMD unit",
    FU.TPU: "tensor / matrix unit",
    FU.LSU: "scalar load/store unit",
    FU.VLSU: "vector and burst load/store unit",
    FU.BRU: "branch / control-flow unit",
    FU.XU: "reserved extension port",
}


class Opcode(enum.IntEnum):
    """Major opcodes, bits [31:26].  Values not listed are reserved."""

    ILLEGAL = 0x00
    NOP = 0x01
    HALT = 0x02
    DFSYNC = 0x03
    ALU_R = 0x08
    ADDI = 0x09
    ANDI = 0x0A
    ORI = 0x0B
    XORI = 0x0C
    SLTI = 0x0D
    SHIFTI = 0x0E
    LUI = 0x0F
    VADD = 0x10
    VSUB = 0x11
    VMUL = 0x12
    VDOT = 0x13
    VREDUCE = 0x14
    VBCAST = 0x15
    MATMUL_4X4_INT = 0x18
    LOAD_S = 0x20
    STORE_S = 0x21
    LOAD_V = 0x28
    STORE_V = 0x29
    BURST_LOAD = 0x2A
    BURST_STORE = 0x2B
    JMP = 0x30
    JAL = 0x31
    JALR = 0x32
    BEQ = 0x33
    BNE = 0x34
    BLT = 0x35
    BGE = 0x36

    @property
    def fu(self) -> FU:
        return FU(self.value >> 3)


class AluFn(enum.IntEnum):
    """funct6 of opcode ALU_R."""

    ADD = 0x00
    SUB = 0x01
    MUL = 0x02
    AND = 0x03
    OR = 0x04
    XOR = 0x05
    SHL = 0x06
    SHR = 0x07
    SAR = 0x08
    SLT = 0x09
    SLTU = 0x0A


class ShiftType(enum.IntEnum):
    """imm16[6:5] of opcode SHIFTI."""

    SHL = 0
    SHR = 1
    SAR = 2


class ElemWidth(enum.IntEnum):
    """funct6[5:4] of vector opcodes."""

    I8 = 0
    I16 = 1
    I32 = 2

    @property
    def bits(self) -> int:
        return 8 << self.value

    @property
    def lanes(self) -> int:
        return VLEN // self.bits


class ReduceOp(enum.IntEnum):
    """funct6[1:0] of VREDUCE."""

    SUM = 0
    MAX = 1
    MIN = 2
    XOR = 3


class TensorIType(enum.IntEnum):
    """funct6[5:4] of MATMUL_4X4_INT: element type of the 4x4 input matrices."""

    S8 = 0
    U8 = 1


class SyncScope(enum.IntEnum):
    """imm16[7:6] of DFSYNC."""

    TILE = 0
    CLUSTER = 1
    GLOBAL = 2


SYNC_MASK_RESERVED = 1 << FU.SCHED
SYNC_FU_SYMBOLS = {fu.name: 1 << fu for fu in FU}
SYNC_GROUP_SYMBOLS = {
    "MEM": (1 << FU.LSU) | (1 << FU.VLSU),
    "COMPUTE": (1 << FU.ALU) | (1 << FU.VPU) | (1 << FU.TPU),
    "ALL": (1 << FU.ALU) | (1 << FU.VPU) | (1 << FU.TPU) | (1 << FU.LSU) | (1 << FU.VLSU) | (1 << FU.BRU),
}
SYNC_MASK_SYMBOLS = {**SYNC_FU_SYMBOLS, **SYNC_GROUP_SYMBOLS}
SYNC_MASK_DEFAULT = SYNC_GROUP_SYMBOLS["ALL"]
SYNC_SCOPE_SYMBOLS = {scope.name: int(scope) for scope in SyncScope}

MOD_EW = tuple(ew.name for ew in ElemWidth)
MOD_REDOP = tuple(op.name for op in ReduceOp)
MOD_ITYPE = tuple(it.name for it in TensorIType)
MOD_SAT = ("SAT",)
MOD_UNS = ("U",)
MOD_GROUPS: tuple[tuple[str, ...], ...] = (MOD_REDOP, MOD_EW, MOD_ITYPE, MOD_SAT, MOD_UNS)


class Fmt(enum.Enum):
    N = "N"
    R = "R"
    I = "I"
    M = "M"
    B = "B"
    J = "J"
    JL = "JL"
    X = "X"
    S = "S"


FORMAT_FIELDS: dict[Fmt, tuple[BitField, ...]] = {
    Fmt.N: (F_OPCODE, F_N_RSVD),
    Fmt.R: (F_OPCODE, F_A, F_B, F_C, F_D, F_FUNCT),
    Fmt.I: (F_OPCODE, F_A, F_B, F_IMM16),
    Fmt.M: (F_OPCODE, F_A, F_B, F_IMM16),
    Fmt.B: (F_OPCODE, F_A, F_B, F_IMM16),
    Fmt.J: (F_OPCODE, F_IMM26),
    Fmt.JL: (F_OPCODE, F_A, F_IMM21),
    Fmt.X: (F_OPCODE, F_A, F_B, F_C, F_D, F_FUNCT),
    Fmt.S: (F_OPCODE, F_A, F_B, F_SYNC_MASK, F_SYNC_SCOPE, F_SYNC_RSVD),
}

SUBFIELD_GROUPS: dict[str, tuple[BitField, tuple[BitField, ...]]] = {
    "SHIFTI imm16": (F_IMM16, (F_SH_RSVD, F_SH_TYPE, F_SH_AMT)),
    "vector funct6": (F_FUNCT, (F_V_EW, F_V_SAT, F_V_UNS, F_V_OPX)),
    "tensor funct6": (F_FUNCT, (F_T_ITYPE, F_T_RSVD, F_T_ACC)),
    "burst funct6": (F_FUNCT, (F_X_RSVD, F_X_TGT)),
}


# =============================================================================
# Diagnostics
# =============================================================================

@dataclass(frozen=True)
class SourceLoc:
    file: str
    line: int
    col: int = 0
    text: str = ""

    def with_col(self, col: int) -> SourceLoc:
        return SourceLoc(self.file, self.line, col, self.text)

    def __str__(self) -> str:
        if self.line <= 0:
            return self.file
        return f"{self.file}:{self.line}:{self.col}" if self.col else f"{self.file}:{self.line}"


class AsmError(Exception):
    """A diagnosable assembly error, optionally tied to a source location."""

    def __init__(self, message: str, loc: SourceLoc | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.loc = loc

    def render(self, severity: str = "error") -> str:
        where = str(self.loc) if self.loc else TOOL
        head = f"{where}: {severity}: {self.message}"
        if self.loc and self.loc.text and self.loc.line > 0 and self.loc.col > 0:
            source = self.loc.text.rstrip("\r\n").replace("\t", " ")
            caret = " " * (self.loc.col - 1) + "^"
            return f"{head}\n    {source}\n    {caret}"
        return head

    def __str__(self) -> str:
        return self.render()


class AssemblyFailed(Exception):
    """Raised when assembly produced one or more errors."""

    def __init__(self, errors: list[AsmError], warnings: list[AsmError]) -> None:
        super().__init__(f"{len(errors)} error(s)")
        self.errors = errors
        self.warnings = warnings


class Unresolved(Exception):
    """A symbol (or '.') has no value yet; used to defer evaluation."""

    def __init__(self, name: str, loc: SourceLoc) -> None:
        super().__init__(name)
        self.name = name
        self.loc = loc


class _TooManyErrors(Exception):
    pass


def _by_location(diags: list[AsmError]) -> list[AsmError]:
    """Order diagnostics by source position; location-less ones keep their order at the end."""
    def key(item: tuple[int, AsmError]) -> tuple:
        index, diag = item
        loc = diag.loc
        return (1, "", 0, 0, index) if loc is None else (0, loc.file, loc.line, loc.col, index)
    return [diag for _, diag in sorted(enumerate(diags), key=key)]


def _suggest(name: str, candidates: Iterable[str], cutoff: float = 0.75) -> str:
    match = difflib.get_close_matches(name, sorted(candidates), n=1, cutoff=cutoff)
    return f" (did you mean '{match[0]}'?)" if match else ""


# =============================================================================
# Lexer
# =============================================================================

class TokKind(enum.Enum):
    IDENT = "identifier"
    NUMBER = "number"
    STRING = "string"
    OP = "operator"


@dataclass(frozen=True)
class Token:
    kind: TokKind
    text: str
    value: object
    loc: SourceLoc

    def is_op(self, text: str) -> bool:
        return self.kind is TokKind.OP and self.text == text


_NUMBER_RE = re.compile(r"0[xX][0-9A-Fa-f_]*|0[bB][01_]*|0[oO][0-7_]*|[0-9][0-9_]*")
_IDENT_START = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_.$")
_IDENT_BODY = _IDENT_START | frozenset("0123456789")
_DIGITS = frozenset("0123456789")
_HEXDIGITS = frozenset("0123456789abcdefABCDEF")
_TWO_CHAR_OPS = ("<<", ">>")
_ONE_CHAR_OPS = frozenset(",[]()+-*/%&|^~:=")
_ESCAPES = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, '"': 34, "'": 39}


def _parse_number(text: str, loc: SourceLoc) -> int:
    body = text.replace("_", "")
    prefix = body[:2].lower()
    radix = {"0x": 16, "0b": 2, "0o": 8}.get(prefix)
    digits = body[2:] if radix else body
    if not digits or text.endswith("_") or "__" in text:
        raise AsmError(f"malformed number '{text}'", loc)
    if radix is None:
        if len(digits) > 1 and digits[0] == "0":
            raise AsmError(f"ambiguous number '{text}': leading zeros are not allowed (use 0o for octal)", loc)
        radix = 10
    try:
        return int(digits, radix)
    except ValueError:
        raise AsmError(f"malformed number '{text}'", loc) from None


def _lex_quoted(line: str, start: int, loc: SourceLoc) -> tuple[int, bytes]:
    quote = line[start]
    kind = "string" if quote == '"' else "character"
    out = bytearray()
    j = start + 1
    while True:
        if j >= len(line):
            raise AsmError(f"unterminated {kind} literal", loc)
        ch = line[j]
        if ch == quote:
            return j + 1, bytes(out)
        if ch == "\\":
            if j + 1 >= len(line):
                raise AsmError(f"unterminated {kind} literal", loc)
            esc = line[j + 1]
            if esc == "x":
                hexd = line[j + 2:j + 4]
                if len(hexd) != 2 or not set(hexd) <= _HEXDIGITS:
                    raise AsmError("malformed \\x escape (expected two hex digits)", loc.with_col(j + 1))
                out.append(int(hexd, 16))
                j += 4
                continue
            if esc not in _ESCAPES:
                raise AsmError(f"unknown escape sequence '\\{esc}'", loc.with_col(j + 1))
            out.append(_ESCAPES[esc])
            j += 2
            continue
        out += ch.encode("utf-8")
        j += 1


def lex_line(line: str, file: str, lineno: int) -> list[Token]:
    """Split one source line into tokens, stopping at a comment."""
    tokens: list[Token] = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch in " \t\r\n\f\v":
            i += 1
            continue
        if ch in ";#" or line.startswith("//", i):
            break
        loc = SourceLoc(file, lineno, i + 1, line)
        if ch == '"':
            end, data = _lex_quoted(line, i, loc)
            tokens.append(Token(TokKind.STRING, line[i:end], data, loc))
            i = end
        elif ch == "'":
            end, data = _lex_quoted(line, i, loc)
            if len(data) != 1:
                raise AsmError("character literal must denote exactly one byte", loc)
            tokens.append(Token(TokKind.NUMBER, line[i:end], data[0], loc))
            i = end
        elif ch in _DIGITS:
            match = _NUMBER_RE.match(line, i)
            end = match.end() if match else i + 1
            if end < n and line[end] in _IDENT_BODY:
                j = end
                while j < n and line[j] in _IDENT_BODY:
                    j += 1
                raise AsmError(f"malformed number '{line[i:j]}'", loc)
            text = line[i:end]
            tokens.append(Token(TokKind.NUMBER, text, _parse_number(text, loc), loc))
            i = end
        elif ch in _IDENT_START:
            j = i + 1
            while j < n and line[j] in _IDENT_BODY:
                j += 1
            tokens.append(Token(TokKind.IDENT, line[i:j], None, loc))
            i = j
        elif line[i:i + 2] in _TWO_CHAR_OPS:
            tokens.append(Token(TokKind.OP, line[i:i + 2], None, loc))
            i += 2
        elif ch in _ONE_CHAR_OPS:
            tokens.append(Token(TokKind.OP, ch, None, loc))
            i += 1
        else:
            raise AsmError(f"unexpected character {ch!r}", loc)
    return tokens


def end_of_line_loc(tokens: Sequence[Token], fallback: SourceLoc) -> SourceLoc:
    if not tokens:
        return fallback
    last = tokens[-1]
    return last.loc.with_col(last.loc.col + len(last.text))


def split_operands(tokens: Sequence[Token], end_loc: SourceLoc) -> list[list[Token]]:
    """Split a token list at top-level commas (not inside () or [])."""
    if not tokens:
        return []
    groups: list[list[Token]] = [[]]
    stack: list[Token] = []
    pairs = {")": "(", "]": "["}
    for tok in tokens:
        if tok.kind is TokKind.OP and tok.text in "([":
            stack.append(tok)
        elif tok.kind is TokKind.OP and tok.text in ")]":
            if not stack or stack[-1].text != pairs[tok.text]:
                raise AsmError(f"unbalanced '{tok.text}'", tok.loc)
            stack.pop()
        if tok.is_op(",") and not stack:
            if not groups[-1]:
                raise AsmError("empty operand before ','", tok.loc)
            groups.append([])
            continue
        groups[-1].append(tok)
    if stack:
        raise AsmError(f"unclosed '{stack[-1].text}'", stack[-1].loc)
    if not groups[-1]:
        raise AsmError("missing operand after ','", end_loc)
    return groups


# =============================================================================
# Expressions
# =============================================================================

@dataclass(frozen=True)
class Num:
    value: int
    loc: SourceLoc


@dataclass(frozen=True)
class Sym:
    name: str
    loc: SourceLoc


@dataclass(frozen=True)
class Here:
    loc: SourceLoc


@dataclass(frozen=True)
class Unary:
    op: str
    operand: Expr
    loc: SourceLoc


@dataclass(frozen=True)
class Binary:
    op: str
    left: Expr
    right: Expr
    loc: SourceLoc


@dataclass(frozen=True)
class Func:
    name: str
    arg: Expr
    loc: SourceLoc


Expr = Union[Num, Sym, Here, Unary, Binary, Func]
EXPR_TYPES = (Num, Sym, Here, Unary, Binary, Func)
Resolver = Callable[[str, SourceLoc], int]

_BINARY_PREC = {"|": 1, "^": 2, "&": 3, "<<": 4, ">>": 4, "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}
_FUNCS = ("hi", "lo")


class TokenStream:
    def __init__(self, tokens: Sequence[Token], end_loc: SourceLoc) -> None:
        self._tokens = tokens
        self._pos = 0
        self.end_loc = end_loc

    def peek(self) -> Token | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def next(self, what: str) -> Token:
        tok = self.peek()
        if tok is None:
            raise AsmError(f"expected {what}", self.end_loc)
        self._pos += 1
        return tok

    def expect_op(self, text: str, context: str) -> Token:
        tok = self.peek()
        if tok is None or not tok.is_op(text):
            raise AsmError(f"expected '{text}' {context}", tok.loc if tok else self.end_loc)
        self._pos += 1
        return tok


def _parse_binary(ts: TokenStream, min_prec: int) -> Expr:
    left = _parse_unary(ts)
    while True:
        tok = ts.peek()
        if tok is None or tok.kind is not TokKind.OP or tok.text not in _BINARY_PREC:
            return left
        prec = _BINARY_PREC[tok.text]
        if prec < min_prec:
            return left
        ts.next("operator")
        right = _parse_binary(ts, prec + 1)
        left = Binary(tok.text, left, right, tok.loc)


def _parse_unary(ts: TokenStream) -> Expr:
    tok = ts.next("an expression")
    if tok.kind is TokKind.OP:
        if tok.text in ("-", "+", "~"):
            return Unary(tok.text, _parse_unary(ts), tok.loc)
        if tok.text == "%":
            name_tok = ts.next("'hi' or 'lo' after '%'")
            name = name_tok.text.lower()
            if name_tok.kind is not TokKind.IDENT or name not in _FUNCS:
                raise AsmError(f"unknown operator '%{name_tok.text}' (expected %hi or %lo)", name_tok.loc)
            ts.expect_op("(", f"after %{name}")
            arg = _parse_binary(ts, 1)
            ts.expect_op(")", f"to close %{name}(")
            return Func(name, arg, tok.loc)
        if tok.text == "(":
            inner = _parse_binary(ts, 1)
            ts.expect_op(")", "to close '('")
            return inner
        raise AsmError(f"unexpected '{tok.text}' in expression", tok.loc)
    if tok.kind is TokKind.NUMBER:
        return Num(cast(int, tok.value), tok.loc)
    if tok.kind is TokKind.IDENT:
        if tok.text == ".":
            return Here(tok.loc)
        if is_register_name(tok.text):
            raise AsmError(f"register '{tok.text}' is not allowed in an expression", tok.loc)
        return Sym(tok.text, tok.loc)
    raise AsmError("string literal is not allowed in an expression", tok.loc)


def parse_expression(tokens: Sequence[Token], end_loc: SourceLoc) -> Expr:
    ts = TokenStream(tokens, end_loc)
    expr = _parse_binary(ts, 1)
    extra = ts.peek()
    if extra is not None:
        raise AsmError(f"unexpected '{extra.text}' after expression", extra.loc)
    return expr


def evaluate(expr: Expr, resolve: Resolver, here: int | None) -> int:
    """Evaluate an expression tree with arbitrary-precision integers."""
    if isinstance(expr, Num):
        return expr.value
    if isinstance(expr, Sym):
        return resolve(expr.name, expr.loc)
    if isinstance(expr, Here):
        if here is None:
            raise Unresolved(".", expr.loc)
        return here
    if isinstance(expr, Unary):
        value = evaluate(expr.operand, resolve, here)
        if expr.op == "-":
            return -value
        if expr.op == "~":
            return ~value
        return value
    if isinstance(expr, Func):
        value = evaluate(expr.arg, resolve, here)
        if not -(1 << 31) <= value <= WORD_MASK:
            raise AsmError(f"%{expr.name}() operand {value} is outside the 32-bit range", expr.loc)
        value &= WORD_MASK
        return (value >> 16) & 0xFFFF if expr.name == "hi" else value & 0xFFFF
    if isinstance(expr, Binary):
        a = evaluate(expr.left, resolve, here)
        b = evaluate(expr.right, resolve, here)
        op = expr.op
        if op == "+":
            result = a + b
        elif op == "-":
            result = a - b
        elif op == "*":
            result = a * b
        elif op in ("/", "%"):
            if b == 0:
                raise AsmError("division by zero in expression", expr.loc)
            quotient = abs(a) // abs(b)
            if (a < 0) != (b < 0):
                quotient = -quotient
            result = quotient if op == "/" else a - quotient * b
        elif op in ("<<", ">>"):
            if not 0 <= b < 64:
                raise AsmError(f"shift count {b} out of range 0..63", expr.loc)
            result = a << b if op == "<<" else a >> b
        elif op == "&":
            result = a & b
        elif op == "|":
            result = a | b
        elif op == "^":
            result = a ^ b
        else:
            raise AsmError(f"internal error: unknown operator '{op}'", expr.loc)
        if abs(result) >= EXPR_LIMIT:
            raise AsmError("expression value exceeds the 64-bit range", expr.loc)
        return result
    raise TypeError(f"not an expression node: {expr!r}")


# =============================================================================
# Registers and operands
# =============================================================================

class RegClass(enum.Enum):
    SCALAR = "r"
    VECTOR = "v"
    TENSOR = "t"


REG_LIMITS = {RegClass.SCALAR: NUM_SREGS, RegClass.VECTOR: NUM_VREGS, RegClass.TENSOR: NUM_TREGS}
REG_DESCRIPTIONS = {
    RegClass.SCALAR: "scalar register",
    RegClass.VECTOR: "vector register",
    RegClass.TENSOR: "tensor register",
}
REG_ALIASES = {"zero": (RegClass.SCALAR, REG_ZERO), "sp": (RegClass.SCALAR, REG_SP), "ra": (RegClass.SCALAR, REG_RA)}
_REG_RE = re.compile(r"([rvt])([0-9]+)\Z")


@dataclass(frozen=True)
class Reg:
    cls: RegClass
    index: int
    loc: SourceLoc

    def __str__(self) -> str:
        return f"{self.cls.value}{self.index}"


@dataclass(frozen=True)
class ImmOp:
    expr: Expr
    loc: SourceLoc


@dataclass(frozen=True)
class MemOp:
    base: Reg
    offset: Expr | None
    loc: SourceLoc


@dataclass(frozen=True)
class LaneOp:
    reg: Reg
    lane: Expr
    loc: SourceLoc


Operand = Union[Reg, ImmOp, MemOp, LaneOp]


def is_register_name(name: str) -> bool:
    low = name.lower()
    return low in REG_ALIASES or _REG_RE.match(low) is not None


def parse_register(name: str, loc: SourceLoc) -> Reg | None:
    """Return the register named `name`, None if it is not register-shaped."""
    low = name.lower()
    if low in REG_ALIASES:
        cls, index = REG_ALIASES[low]
        return Reg(cls, index, loc)
    match = _REG_RE.match(low)
    if match is None:
        return None
    cls = RegClass(match.group(1))
    digits = match.group(2)
    limit = REG_LIMITS[cls]
    if len(digits) > 1 and digits[0] == "0":
        raise AsmError(f"malformed register name '{name}' (leading zero)", loc)
    index = int(digits)
    if index >= limit:
        raise AsmError(
            f"invalid {REG_DESCRIPTIONS[cls]} '{name}' (valid: {cls.value}0-{cls.value}{limit - 1})", loc)
    return Reg(cls, index, loc)


def _matching_open(tokens: Sequence[Token], close_index: int) -> int:
    depth = 0
    for i in range(close_index, -1, -1):
        tok = tokens[i]
        if tok.is_op(")") or tok.is_op("]"):
            depth += 1
        elif tok.is_op("(") or tok.is_op("["):
            depth -= 1
            if depth == 0:
                return i
    return -1


def _scalar_base(reg: Reg) -> Reg:
    if reg.cls is not RegClass.SCALAR:
        raise AsmError(f"memory base must be a scalar register, got {REG_DESCRIPTIONS[reg.cls]} '{reg}'", reg.loc)
    return reg


def _parse_bracket_memory(inner: Sequence[Token], open_tok: Token, end_loc: SourceLoc) -> MemOp:
    if not inner:
        raise AsmError("empty memory operand '[]'", open_tok.loc)
    first = inner[0]
    reg = parse_register(first.text, first.loc) if first.kind is TokKind.IDENT else None
    if reg is None:
        return MemOp(Reg(RegClass.SCALAR, REG_ZERO, open_tok.loc), parse_expression(inner, end_loc), open_tok.loc)
    base = _scalar_base(reg)
    rest = inner[1:]
    if not rest:
        return MemOp(base, None, open_tok.loc)
    sign = rest[0]
    if not (sign.is_op("+") or sign.is_op("-")):
        raise AsmError(f"expected '+' or '-' after base register in memory operand, got '{sign.text}'", sign.loc)
    if len(rest) == 1:
        raise AsmError(f"missing offset after '{sign.text}'", sign.loc)
    offset = parse_expression(rest[1:], end_loc)
    if sign.text == "-":
        offset = Unary("-", offset, sign.loc)
    return MemOp(base, offset, open_tok.loc)


def parse_operand(tokens: Sequence[Token], end_loc: SourceLoc) -> Operand:
    if not tokens:
        raise AsmError("empty operand", end_loc)
    first, last = tokens[0], tokens[-1]
    if first.kind is TokKind.IDENT:
        reg = parse_register(first.text, first.loc)
        if reg is not None:
            if len(tokens) == 1:
                return reg
            if tokens[1].is_op("[") and last.is_op("]") and _matching_open(tokens, len(tokens) - 1) == 1:
                if reg.cls is not RegClass.VECTOR:
                    raise AsmError(f"lane selection requires a vector register, got '{reg}'", reg.loc)
                if len(tokens) == 3:
                    raise AsmError("missing lane index in '[]'", tokens[1].loc)
                return LaneOp(reg, parse_expression(tokens[2:-1], end_loc), first.loc)
            raise AsmError(f"unexpected '{tokens[1].text}' after register '{first.text}'", tokens[1].loc)
    if first.is_op("["):
        close = len(tokens) - 1
        if not last.is_op("]") or _matching_open(tokens, close) != 0:
            raise AsmError("memory operand must be enclosed in '[' ... ']'", first.loc)
        return _parse_bracket_memory(tokens[1:-1], first, end_loc)
    if last.is_op(")"):
        open_index = _matching_open(tokens, len(tokens) - 1)
        inner = tokens[open_index + 1:-1] if open_index >= 0 else []
        if len(inner) == 1 and inner[0].kind is TokKind.IDENT:
            reg = parse_register(inner[0].text, inner[0].loc)
            if reg is not None:
                base = _scalar_base(reg)
                offset = parse_expression(tokens[:open_index], end_loc) if open_index > 0 else None
                return MemOp(base, offset, first.loc)
    return ImmOp(parse_expression(tokens, end_loc), first.loc)


def operand_kind(op: Operand) -> str:
    if isinstance(op, Reg):
        return {RegClass.SCALAR: "R", RegClass.VECTOR: "V", RegClass.TENSOR: "T"}[op.cls]
    if isinstance(op, ImmOp):
        return "E"
    if isinstance(op, MemOp):
        return "M"
    return "VL"


def describe_operand(op: Operand) -> str:
    if isinstance(op, Reg):
        return f"{REG_DESCRIPTIONS[op.cls]} '{op}'"
    if isinstance(op, ImmOp):
        return "an expression"
    if isinstance(op, MemOp):
        return "a memory operand"
    return "a vector lane"


KIND_TEXT = {
    "R": "a scalar register (r0-r31)",
    "V": "a vector register (v0-v31)",
    "T": "a tensor register (t0-t7)",
    "E": "an immediate or label expression",
    "M": "a memory operand ([rs1 + offset])",
    "VL": "a vector lane (vN[lane])",
}


@dataclass(frozen=True)
class Slot:
    kinds: tuple[str, ...]
    name: str
    optional: bool = False


def slots(*specs: str) -> tuple[Slot, ...]:
    """Build an operand signature from 'KINDS[?]:name' strings."""
    out: list[Slot] = []
    for spec in specs:
        kinds_text, name = spec.split(":", 1)
        optional = kinds_text.endswith("?")
        kinds = tuple(kinds_text.rstrip("?").split("|"))
        if out and out[-1].optional and not optional:
            raise ValueError(f"required operand '{name}' follows an optional one")
        if any(k not in KIND_TEXT for k in kinds):
            raise ValueError(f"unknown operand kind in '{spec}'")
        out.append(Slot(kinds, name, optional))
    return tuple(out)


def render_syntax(mnemonic: str, modifiers: Sequence[str], sig: Sequence[Slot]) -> str:
    text = mnemonic
    for group in MOD_GROUPS:
        present = [m for m in group if m in modifiers]
        if present:
            text += "[" + "|".join("." + m for m in present) + "]"
    required = [s.name for s in sig if not s.optional]
    optional = [s.name for s in sig if s.optional]
    if required:
        text += " " + ", ".join(required)
    for i, name in enumerate(optional):
        text += f" [{name}]" if not required and i == 0 else f"[, {name}]"
    return text


def validate_operands(mnemonic: str, sig: Sequence[Slot], syntax: str,
                      ops: Sequence[Operand], loc: SourceLoc) -> None:
    required = sum(1 for s in sig if not s.optional)
    if not required <= len(ops) <= len(sig):
        expected = str(required) if required == len(sig) else f"{required} to {len(sig)}"
        plural = "" if len(sig) == 1 and required == 1 else "s"
        raise AsmError(f"{mnemonic} expects {expected} operand{plural} ({syntax}), got {len(ops)}", loc)
    for position, (slot, op) in enumerate(zip(sig, ops), 1):
        if operand_kind(op) not in slot.kinds:
            wanted = " or ".join(KIND_TEXT[k] for k in slot.kinds)
            raise AsmError(
                f"operand {position} ({slot.name}) of {mnemonic} must be {wanted}; got {describe_operand(op)}",
                op.loc)


# =============================================================================
# Modifiers
# =============================================================================

@dataclass(frozen=True)
class Mods:
    ew: ElemWidth = ElemWidth.I32
    sat: bool = False
    uns: bool = False
    redop: ReduceOp = ReduceOp.SUM
    itype: TensorIType = TensorIType.S8


NO_MODS = Mods()


def parse_mods(spec: InsnSpec, raw: Sequence[str], loc: SourceLoc) -> Mods:
    if raw and not spec.modifiers:
        raise AsmError(f"{spec.mnemonic} takes no modifiers (got '.{raw[0]}')", loc)
    chosen: dict[tuple[str, ...], str] = {}
    for item in raw:
        if not item:
            raise AsmError(f"empty modifier in '{spec.mnemonic}.{'.'.join(raw)}'", loc)
        mod = item.upper()
        if mod not in spec.modifiers:
            allowed = ", ".join("." + m for m in spec.modifiers)
            raise AsmError(f"invalid modifier '.{item}' for {spec.mnemonic} (allowed: {allowed})", loc)
        group = next(g for g in MOD_GROUPS if mod in g)
        if group in chosen:
            if chosen[group] == mod:
                raise AsmError(f"duplicate modifier '.{mod}'", loc)
            raise AsmError(f"conflicting modifiers '.{chosen[group]}' and '.{mod}'", loc)
        chosen[group] = mod
    mods = Mods(
        ew=ElemWidth[chosen[MOD_EW]] if MOD_EW in chosen else ElemWidth.I32,
        sat=MOD_SAT in chosen,
        uns=MOD_UNS in chosen,
        redop=ReduceOp[chosen[MOD_REDOP]] if MOD_REDOP in chosen else ReduceOp.SUM,
        itype=TensorIType[chosen[MOD_ITYPE]] if MOD_ITYPE in chosen else TensorIType.S8,
    )
    if spec.opcode in (Opcode.VADD, Opcode.VSUB) and mods.uns and not mods.sat:
        raise AsmError(f"{spec.mnemonic}.U requires .SAT (wrapping add/sub is signedness-agnostic)", loc)
    if spec.opcode is Opcode.VREDUCE and mods.uns and mods.redop not in (ReduceOp.MAX, ReduceOp.MIN):
        raise AsmError(".U applies only to VREDUCE.MAX and VREDUCE.MIN", loc)
    return mods


# =============================================================================
# Encoding context
# =============================================================================

Warn = Callable[[str, SourceLoc], None]


def _expr_loc(item: Operand | Expr) -> tuple[Expr, SourceLoc]:
    if isinstance(item, ImmOp):
        return item.expr, item.loc
    if isinstance(item, EXPR_TYPES):
        return cast(Expr, item), item.loc
    raise EncodingError(f"expected an expression operand, got {item!r}")


class EncodeCtx:
    """Evaluation and range-checking services for one instruction word."""

    def __init__(self, resolve: Resolver, pc: int, here: int, loc: SourceLoc, warn: Warn) -> None:
        self._resolve = resolve
        self.pc = pc
        self.here = here
        self.loc = loc
        self.warn = warn

    def value(self, item: Operand | Expr, extra: dict[str, int] | None = None) -> int:
        expr, _ = _expr_loc(item)

        def resolver(name: str, loc: SourceLoc) -> int:
            if extra is not None and name.upper() in extra:
                return extra[name.upper()]
            return self._resolve(name, loc)

        try:
            return evaluate(expr, resolver, self.here)
        except Unresolved as exc:
            raise AsmError(f"undefined symbol '{exc.name}'", exc.loc) from None

    def unsigned(self, item: Operand | Expr, bits: int, what: str, extra: dict[str, int] | None = None) -> int:
        _, loc = _expr_loc(item)
        value = self.value(item, extra)
        if not 0 <= value < (1 << bits):
            raise AsmError(f"{what} {value} out of range 0..{(1 << bits) - 1}", loc)
        return value

    def signed(self, item: Operand | Expr, bits: int, what: str) -> int:
        _, loc = _expr_loc(item)
        value = self.value(item)
        lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
        if not lo <= value <= hi:
            raise AsmError(f"{what} {value} out of range {lo}..{hi}", loc)
        return to_twos(value, bits)

    def displacement(self, item: Operand | Expr, bits: int, what: str) -> int:
        _, loc = _expr_loc(item)
        target = self.value(item)
        delta = target - self.pc
        if delta % WORD_BYTES:
            raise AsmError(f"{what} {target:#x} is not 4-byte aligned", loc)
        words = delta // WORD_BYTES
        lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
        if not lo <= words <= hi:
            raise AsmError(
                f"{what} {target:#x} is out of range from pc {self.pc:#x}: displacement {words} words "
                f"does not fit a signed {bits}-bit field ({lo}..{hi})", loc)
        return to_twos(words, bits)

    def note_dest(self, spec: InsnSpec, rd: Reg) -> None:
        if spec.writes_rd and rd.cls is RegClass.SCALAR and rd.index == REG_ZERO:
            self.warn(f"{spec.mnemonic} writes r0; the result is discarded", rd.loc)


# =============================================================================
# Encoders (one per encoding family; every field is packed explicitly)
# =============================================================================

def _regs(ops: Sequence[Operand], count: int) -> list[Reg]:
    return [cast(Reg, op) for op in ops[:count]]


def _vec_funct(ew: ElemWidth, sat: bool, uns: bool, opx: int) -> int:
    return pack((F_V_EW, int(ew)), (F_V_SAT, int(sat)), (F_V_UNS, int(uns)), (F_V_OPX, opx))


def enc_nop(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    return pack((F_OPCODE, int(spec.opcode)), (F_N_RSVD, 0))


def enc_halt(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    code = ctx.unsigned(ops[0], 16, "HALT exit code") if ops else 0
    return pack((F_OPCODE, int(spec.opcode)), (F_A, 0), (F_B, 0), (F_IMM16, code))


def enc_dfsync(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    barrier = ctx.unsigned(ops[0], F_A.width, "DFSYNC barrier id")
    mask = SYNC_MASK_DEFAULT
    if len(ops) > 1:
        mask = ctx.unsigned(ops[1], F_SYNC_MASK.width, "DFSYNC FU mask", SYNC_MASK_SYMBOLS)
    scope = int(SyncScope.TILE)
    if len(ops) > 2:
        scope = ctx.unsigned(ops[2], F_SYNC_SCOPE.width, "DFSYNC scope", SYNC_SCOPE_SYMBOLS)
    if mask & SYNC_MASK_RESERVED:
        raise AsmError("DFSYNC FU mask bit 0 (SCHED) is reserved and must be zero", ops[1].loc)
    if scope not in SYNC_SCOPE_SYMBOLS.values():
        raise AsmError(f"DFSYNC scope {scope} is reserved (TILE, CLUSTER or GLOBAL)", ops[2].loc)
    if mask == 0 and scope == SyncScope.TILE:
        ctx.warn("DFSYNC with an empty FU mask at TILE scope has no effect", ctx.loc)
    return pack((F_OPCODE, int(spec.opcode)), (F_A, barrier), (F_B, 0),
                (F_SYNC_MASK, mask), (F_SYNC_SCOPE, scope), (F_SYNC_RSVD, 0))


def enc_alu_r(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    rd, rs1, rs2 = _regs(ops, 3)
    ctx.note_dest(spec, rd)
    return pack((F_OPCODE, int(spec.opcode)), (F_A, rd.index), (F_B, rs1.index),
                (F_C, rs2.index), (F_D, 0), (F_FUNCT, cast(int, spec.funct)))


def enc_alu_i(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    rd, rs1 = _regs(ops, 2)
    ctx.note_dest(spec, rd)
    if spec.imm == "s16":
        imm = ctx.signed(ops[2], 16, f"{spec.mnemonic} immediate")
    else:
        imm = ctx.unsigned(ops[2], 16, f"{spec.mnemonic} immediate (zero-extended)")
    return pack((F_OPCODE, int(spec.opcode)), (F_A, rd.index), (F_B, rs1.index), (F_IMM16, imm))


def enc_shift_i(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    rd, rs1 = _regs(ops, 2)
    ctx.note_dest(spec, rd)
    shamt = ctx.unsigned(ops[2], F_SH_AMT.width, f"{spec.mnemonic} shift amount")
    return pack((F_OPCODE, int(spec.opcode)), (F_A, rd.index), (F_B, rs1.index),
                (F_SH_RSVD, 0), (F_SH_TYPE, cast(int, spec.funct)), (F_SH_AMT, shamt))


def enc_lui(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    (rd,) = _regs(ops, 1)
    ctx.note_dest(spec, rd)
    imm = ctx.unsigned(ops[1], 16, "LUI immediate")
    return pack((F_OPCODE, int(spec.opcode)), (F_A, rd.index), (F_B, 0), (F_IMM16, imm))


def enc_vec_arith(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    vd, vs1, vs2 = _regs(ops, 3)
    funct = _vec_funct(mods.ew, mods.sat, mods.uns, 0)
    return pack((F_OPCODE, int(spec.opcode)), (F_A, vd.index), (F_B, vs1.index),
                (F_C, vs2.index), (F_D, 0), (F_FUNCT, funct))


def enc_vdot(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    rd, vs1, vs2 = _regs(ops, 3)
    rs3 = cast(Reg, ops[3]).index if len(ops) > 3 else REG_ZERO
    ctx.note_dest(spec, rd)
    funct = _vec_funct(mods.ew, False, mods.uns, 0)
    return pack((F_OPCODE, int(spec.opcode)), (F_A, rd.index), (F_B, vs1.index),
                (F_C, vs2.index), (F_D, rs3), (F_FUNCT, funct))


def enc_vreduce(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    rd, vs1 = _regs(ops, 2)
    ctx.note_dest(spec, rd)
    funct = _vec_funct(mods.ew, False, mods.uns, int(mods.redop))
    return pack((F_OPCODE, int(spec.opcode)), (F_A, rd.index), (F_B, vs1.index),
                (F_C, 0), (F_D, 0), (F_FUNCT, funct))


def enc_vbcast(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    (vd,) = _regs(ops, 1)
    src = ops[1]
    if isinstance(src, LaneOp):
        lane = ctx.unsigned(src.lane, F_D.width, "lane index")
        if lane >= mods.ew.lanes:
            raise AsmError(f"lane {lane} out of range for .{mods.ew.name} (0..{mods.ew.lanes - 1})", src.loc)
        source, d_field, opx = src.reg.index, lane, 1
    else:
        source, d_field, opx = cast(Reg, src).index, 0, 0
    funct = _vec_funct(mods.ew, False, False, opx)
    return pack((F_OPCODE, int(spec.opcode)), (F_A, vd.index), (F_B, source),
                (F_C, 0), (F_D, d_field), (F_FUNCT, funct))


def enc_matmul(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    td, va, vb = _regs(ops, 3)
    accumulate = len(ops) > 3
    tc = cast(Reg, ops[3]).index if accumulate else 0
    funct = pack((F_T_ITYPE, int(mods.itype)), (F_T_RSVD, 0), (F_T_ACC, int(accumulate)))
    return pack((F_OPCODE, int(spec.opcode)), (F_A, td.index), (F_B, va.index),
                (F_C, vb.index), (F_D, tc), (F_FUNCT, funct))


def enc_mem(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    data = cast(Reg, ops[0])
    mem = cast(MemOp, ops[1])
    if spec.writes_rd:
        ctx.note_dest(spec, data)
    align = WORD_BYTES if data.cls is RegClass.SCALAR else VLEN_BYTES
    offset = 0
    if mem.offset is not None:
        offset = ctx.value(mem.offset)
        if not -0x8000 <= offset <= 0x7FFF:
            raise AsmError(f"{spec.mnemonic} offset {offset} out of range -32768..32767", mem.loc)
        if offset % align:
            raise AsmError(f"{spec.mnemonic} offset {offset} must be a multiple of {align} ({align}-byte aligned access)",
                           mem.loc)
    return pack((F_OPCODE, int(spec.opcode)), (F_A, data.index), (F_B, mem.base.index),
                (F_IMM16, to_twos(offset, 16)))


def enc_burst(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    reg = cast(Reg, ops[0])
    mem = cast(MemOp, ops[1])
    if mem.offset is not None and ctx.value(mem.offset) != 0:
        raise AsmError(f"{spec.mnemonic} takes no address offset; use [rs1]", mem.loc)
    beats: int | None = None
    stride = REG_ZERO
    extra = list(ops[2:])
    if extra and isinstance(extra[0], ImmOp):
        beats = ctx.unsigned(extra.pop(0), 6, "burst beat count")
    if extra:
        stride_op = extra.pop(0)
        if not isinstance(stride_op, Reg):
            raise AsmError("burst stride must be a scalar register", stride_op.loc)
        stride = stride_op.index
    if extra:
        raise AsmError(f"unexpected operand after the stride register of {spec.mnemonic}", extra[0].loc)
    if reg.cls is RegClass.TENSOR:
        target = 1
        if beats is None:
            beats = TILE_BEATS
        if beats != TILE_BEATS:
            raise AsmError(f"tensor tile bursts transfer exactly {TILE_BEATS} beats (one 4 x int32 row per beat)",
                           ops[2].loc)
    else:
        target = 0
        if beats is None:
            raise AsmError(f"vector {spec.mnemonic} requires a beat count (1..{MAX_BURST_BEATS})", reg.loc)
        if not 1 <= beats <= MAX_BURST_BEATS:
            raise AsmError(f"burst beat count {beats} out of range 1..{MAX_BURST_BEATS}", ops[2].loc)
        if reg.index + beats > NUM_VREGS:
            raise AsmError(
                f"burst of {beats} beats from {reg} exceeds the vector register file (v{reg.index}..v{reg.index + beats - 1})",
                reg.loc)
    funct = pack((F_X_RSVD, 0), (F_X_TGT, target))
    return pack((F_OPCODE, int(spec.opcode)), (F_A, reg.index), (F_B, mem.base.index),
                (F_C, stride), (F_D, beats - 1), (F_FUNCT, funct))


def enc_jmp(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    disp = ctx.displacement(ops[0], F_IMM26.width, "jump target")
    return pack((F_OPCODE, int(spec.opcode)), (F_IMM26, disp))


def enc_jal(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    (rd,) = _regs(ops, 1)
    disp = ctx.displacement(ops[1], F_IMM21.width, "call target")
    return pack((F_OPCODE, int(spec.opcode)), (F_A, rd.index), (F_IMM21, disp))


def enc_jalr(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    rd, rs1 = _regs(ops, 2)
    imm = ctx.signed(ops[2], 16, "JALR offset") if len(ops) > 2 else 0
    return pack((F_OPCODE, int(spec.opcode)), (F_A, rd.index), (F_B, rs1.index), (F_IMM16, imm))


def enc_branch(spec: InsnSpec, mods: Mods, ops: Sequence[Operand], ctx: EncodeCtx) -> int:
    rs1, rs2 = _regs(ops, 2)
    disp = ctx.displacement(ops[2], F_IMM16.width, "branch target")
    return pack((F_OPCODE, int(spec.opcode)), (F_A, rs1.index), (F_B, rs2.index), (F_IMM16, disp))


Encoder = Callable[["InsnSpec", Mods, Sequence[Operand], EncodeCtx], int]


# =============================================================================
# Instruction table (complete and explicit)
# =============================================================================

@dataclass(frozen=True)
class InsnSpec:
    mnemonic: str
    opcode: Opcode
    fmt: Fmt
    sig: tuple[Slot, ...]
    encoder: Encoder
    summary: str
    funct: int | None = None
    imm: str | None = None
    modifiers: tuple[str, ...] = ()
    writes_rd: bool = False

    @property
    def fu(self) -> FU:
        return self.opcode.fu

    @property
    def syntax(self) -> str:
        return render_syntax(self.mnemonic, self.modifiers, self.sig)


def _alu_r(fn: AluFn, summary: str) -> InsnSpec:
    return InsnSpec(fn.name, Opcode.ALU_R, Fmt.R, slots("R:rd", "R:rs1", "R:rs2"), enc_alu_r, summary,
                    funct=int(fn), writes_rd=True)


def _alu_i(opcode: Opcode, imm: str, summary: str) -> InsnSpec:
    return InsnSpec(opcode.name, opcode, Fmt.I, slots("R:rd", "R:rs1", "E:imm"), enc_alu_i, summary,
                    imm=imm, writes_rd=True)


def _shift_i(mnemonic: str, kind: ShiftType, summary: str) -> InsnSpec:
    return InsnSpec(mnemonic, Opcode.SHIFTI, Fmt.I, slots("R:rd", "R:rs1", "E:shamt"), enc_shift_i, summary,
                    funct=int(kind), writes_rd=True)


def _branch(opcode: Opcode, summary: str) -> InsnSpec:
    return InsnSpec(opcode.name, opcode, Fmt.B, slots("R:rs1", "R:rs2", "E:target"), enc_branch, summary)


INSTRUCTIONS: tuple[InsnSpec, ...] = (
    InsnSpec("NOP", Opcode.NOP, Fmt.N, (), enc_nop, "no operation"),
    InsnSpec("HALT", Opcode.HALT, Fmt.I, slots("E?:code"), enc_halt,
             "retire all work and stop the thread; imm16 = exit status"),
    InsnSpec("DFSYNC", Opcode.DFSYNC, Fmt.S, slots("E:barrier", "E?:fu_mask", "E?:scope"), enc_dfsync,
             "drain the FUs in fu_mask (default ALL), then rendezvous on barrier at scope (default TILE)"),
    _alu_r(AluFn.ADD, "rd = rs1 + rs2"),
    _alu_r(AluFn.SUB, "rd = rs1 - rs2"),
    _alu_r(AluFn.MUL, "rd = low32(rs1 * rs2)"),
    _alu_r(AluFn.AND, "rd = rs1 & rs2"),
    _alu_r(AluFn.OR, "rd = rs1 | rs2"),
    _alu_r(AluFn.XOR, "rd = rs1 ^ rs2"),
    _alu_r(AluFn.SHL, "rd = rs1 << rs2[4:0]"),
    _alu_r(AluFn.SHR, "rd = rs1 >> rs2[4:0] (logical)"),
    _alu_r(AluFn.SAR, "rd = rs1 >>> rs2[4:0] (arithmetic)"),
    _alu_r(AluFn.SLT, "rd = (signed rs1 < signed rs2)"),
    _alu_r(AluFn.SLTU, "rd = (unsigned rs1 < unsigned rs2)"),
    _alu_i(Opcode.ADDI, "s16", "rd = rs1 + sext(imm16)"),
    _alu_i(Opcode.ANDI, "u16", "rd = rs1 & zext(imm16)"),
    _alu_i(Opcode.ORI, "u16", "rd = rs1 | zext(imm16)"),
    _alu_i(Opcode.XORI, "u16", "rd = rs1 ^ zext(imm16)"),
    _alu_i(Opcode.SLTI, "s16", "rd = (signed rs1 < sext(imm16))"),
    _shift_i("SHLI", ShiftType.SHL, "rd = rs1 << shamt"),
    _shift_i("SHRI", ShiftType.SHR, "rd = rs1 >> shamt (logical)"),
    _shift_i("SARI", ShiftType.SAR, "rd = rs1 >>> shamt (arithmetic)"),
    InsnSpec("LUI", Opcode.LUI, Fmt.I, slots("R:rd", "E:imm"), enc_lui, "rd = imm16 << 16", writes_rd=True),
    InsnSpec("VADD", Opcode.VADD, Fmt.R, slots("V:vd", "V:vs1", "V:vs2"), enc_vec_arith,
             "vd[i] = vs1[i] + vs2[i] (wrapping, or saturating with .SAT; .U = unsigned saturation)",
             modifiers=MOD_EW + MOD_SAT + MOD_UNS),
    InsnSpec("VSUB", Opcode.VSUB, Fmt.R, slots("V:vd", "V:vs1", "V:vs2"), enc_vec_arith,
             "vd[i] = vs1[i] - vs2[i] (wrapping, or saturating with .SAT; .U = unsigned saturation)",
             modifiers=MOD_EW + MOD_SAT + MOD_UNS),
    InsnSpec("VMUL", Opcode.VMUL, Fmt.R, slots("V:vd", "V:vs1", "V:vs2"), enc_vec_arith,
             "vd[i] = low(vs1[i] * vs2[i])", modifiers=MOD_EW),
    InsnSpec("VDOT", Opcode.VDOT, Fmt.R, slots("R:rd", "V:vs1", "V:vs2", "R?:rs3"), enc_vdot,
             "rd = rs3 + sum(vs1[i] * vs2[i]) widened to 32 bits (rs3 defaults to r0)",
             modifiers=MOD_EW + MOD_UNS, writes_rd=True),
    InsnSpec("VREDUCE", Opcode.VREDUCE, Fmt.R, slots("R:rd", "V:vs1"), enc_vreduce,
             "rd = reduce(op, vs1[*]) extended to 32 bits (op defaults to .SUM)",
             modifiers=MOD_REDOP + MOD_EW + MOD_UNS, writes_rd=True),
    InsnSpec("VBCAST", Opcode.VBCAST, Fmt.R, slots("V:vd", "R|VL:rs1|vs1[lane]"), enc_vbcast,
             "vd[*] = rs1[ew-1:0], or vd[*] = vs1[lane]", modifiers=MOD_EW),
    InsnSpec("MATMUL_4X4_INT", Opcode.MATMUL_4X4_INT, Fmt.R, slots("T:td", "V:va", "V:vb", "T?:tc"), enc_matmul,
             "td = va(4x4 int8) x vb(4x4 int8) [+ tc], int32 accumulate", modifiers=MOD_ITYPE),
    InsnSpec("LOAD_S", Opcode.LOAD_S, Fmt.M, slots("R:rd", "M:[rs1+off]"), enc_mem,
             "rd = mem32[rs1 + sext(off)]", writes_rd=True),
    InsnSpec("STORE_S", Opcode.STORE_S, Fmt.M, slots("R:rs", "M:[rs1+off]"), enc_mem,
             "mem32[rs1 + sext(off)] = rs"),
    InsnSpec("LOAD_V", Opcode.LOAD_V, Fmt.M, slots("V:vd", "M:[rs1+off]"), enc_mem,
             "vd = mem128[rs1 + sext(off)]"),
    InsnSpec("STORE_V", Opcode.STORE_V, Fmt.M, slots("V:vs", "M:[rs1+off]"), enc_mem,
             "mem128[rs1 + sext(off)] = vs"),
    InsnSpec("BURST_LOAD", Opcode.BURST_LOAD, Fmt.X, slots("V|T:vd|td", "M:[rs1]", "E|R?:beats", "R?:stride"),
             enc_burst, "beat k: dst[k] = mem128[rs1 + k * (stride ? rstride : 16)]"),
    InsnSpec("BURST_STORE", Opcode.BURST_STORE, Fmt.X, slots("V|T:vs|ts", "M:[rs1]", "E|R?:beats", "R?:stride"),
             enc_burst, "beat k: mem128[rs1 + k * (stride ? rstride : 16)] = src[k]"),
    InsnSpec("JMP", Opcode.JMP, Fmt.J, slots("E:target"), enc_jmp, "pc = target (pc-relative, +/-128 MiB)"),
    InsnSpec("JAL", Opcode.JAL, Fmt.JL, slots("R:rd", "E:target"), enc_jal,
             "rd = pc + 4; pc = target (pc-relative, +/-4 MiB)"),
    InsnSpec("JALR", Opcode.JALR, Fmt.I, slots("R:rd", "R:rs1", "E?:imm"), enc_jalr,
             "rd = pc + 4; pc = (rs1 + sext(imm16)) & ~3", imm="s16"),
    _branch(Opcode.BEQ, "if rs1 == rs2: pc = target (+/-128 KiB)"),
    _branch(Opcode.BNE, "if rs1 != rs2: pc = target"),
    _branch(Opcode.BLT, "if signed rs1 < signed rs2: pc = target"),
    _branch(Opcode.BGE, "if signed rs1 >= signed rs2: pc = target"),
)

INSN_BY_MNEMONIC: dict[str, InsnSpec] = {spec.mnemonic: spec for spec in INSTRUCTIONS}
ALU_R_BY_FUNCT: dict[int, InsnSpec] = {cast(int, s.funct): s for s in INSTRUCTIONS if s.opcode is Opcode.ALU_R}
SHIFT_BY_TYPE: dict[int, InsnSpec] = {cast(int, s.funct): s for s in INSTRUCTIONS if s.opcode is Opcode.SHIFTI}
INSN_BY_OPCODE: dict[Opcode, InsnSpec] = {
    s.opcode: s for s in INSTRUCTIONS if s.opcode not in (Opcode.ALU_R, Opcode.SHIFTI)}


# =============================================================================
# Pseudo-instructions
# =============================================================================

@dataclass(frozen=True)
class Lowered:
    """One machine instruction ready for pass-2 encoding."""

    spec: InsnSpec
    mods: Mods
    operands: tuple[Operand, ...]


TryEval = Callable[[Expr], "int | None"]
Expander = Callable[[Sequence[Operand], SourceLoc, TryEval], list[Lowered]]


def _zero_reg(loc: SourceLoc) -> Reg:
    return Reg(RegClass.SCALAR, REG_ZERO, loc)


def _num(value: int, loc: SourceLoc) -> ImmOp:
    return ImmOp(Num(value, loc), loc)


def _low(mnemonic: str, *operands: Operand) -> Lowered:
    return Lowered(INSN_BY_MNEMONIC[mnemonic], NO_MODS, tuple(operands))


def _expand_li(ops: Sequence[Operand], loc: SourceLoc, try_eval: TryEval) -> list[Lowered]:
    rd = cast(Reg, ops[0])
    src = cast(ImmOp, ops[1])
    value = try_eval(src.expr)
    if value is None:
        return [_low("LUI", rd, ImmOp(Func("hi", src.expr, src.loc), src.loc)),
                _low("ORI", rd, rd, ImmOp(Func("lo", src.expr, src.loc), src.loc))]
    if not -(1 << 31) <= value <= WORD_MASK:
        raise AsmError(f"value {value} does not fit in 32 bits", src.loc)
    zero = _zero_reg(loc)
    if -0x8000 <= value <= 0x7FFF:
        return [_low("ADDI", rd, zero, _num(value, src.loc))]
    if 0 <= value <= 0xFFFF:
        return [_low("ORI", rd, zero, _num(value, src.loc))]
    word = value & WORD_MASK
    if word & 0xFFFF == 0:
        return [_low("LUI", rd, _num(word >> 16, src.loc))]
    return [_low("LUI", rd, _num(word >> 16, src.loc)), _low("ORI", rd, rd, _num(word & 0xFFFF, src.loc))]


def _expand_mov(ops: Sequence[Operand], loc: SourceLoc, try_eval: TryEval) -> list[Lowered]:
    return [_low("ADDI", ops[0], ops[1], _num(0, loc))]


def _expand_neg(ops: Sequence[Operand], loc: SourceLoc, try_eval: TryEval) -> list[Lowered]:
    return [_low("SUB", ops[0], _zero_reg(loc), ops[1])]


def _expand_subi(ops: Sequence[Operand], loc: SourceLoc, try_eval: TryEval) -> list[Lowered]:
    imm = cast(ImmOp, ops[2])
    return [_low("ADDI", ops[0], ops[1], ImmOp(Unary("-", imm.expr, imm.loc), imm.loc))]


def _expand_swapped(mnemonic: str) -> Expander:
    def expand(ops: Sequence[Operand], loc: SourceLoc, try_eval: TryEval) -> list[Lowered]:
        return [_low(mnemonic, ops[1], ops[0], ops[2])]
    return expand


def _expand_vs_zero(mnemonic: str) -> Expander:
    def expand(ops: Sequence[Operand], loc: SourceLoc, try_eval: TryEval) -> list[Lowered]:
        return [_low(mnemonic, ops[0], _zero_reg(loc), ops[1])]
    return expand


def _expand_j(ops: Sequence[Operand], loc: SourceLoc, try_eval: TryEval) -> list[Lowered]:
    return [_low("JMP", ops[0])]


def _expand_call(ops: Sequence[Operand], loc: SourceLoc, try_eval: TryEval) -> list[Lowered]:
    return [_low("JAL", Reg(RegClass.SCALAR, REG_RA, loc), ops[0])]


def _expand_ret(ops: Sequence[Operand], loc: SourceLoc, try_eval: TryEval) -> list[Lowered]:
    return [_low("JALR", _zero_reg(loc), Reg(RegClass.SCALAR, REG_RA, loc), _num(0, loc))]


@dataclass(frozen=True)
class PseudoSpec:
    mnemonic: str
    sig: tuple[Slot, ...]
    expand: Expander
    summary: str

    @property
    def syntax(self) -> str:
        return render_syntax(self.mnemonic, (), self.sig)


PSEUDO_INSTRUCTIONS: tuple[PseudoSpec, ...] = (
    PseudoSpec("LI", slots("R:rd", "E:value"), _expand_li,
               "rd = 32-bit value: ADDI | ORI | LUI | LUI+ORI (2 words when not known in pass 1)"),
    PseudoSpec("LA", slots("R:rd", "E:address"), _expand_li, "rd = address (same lowering as LI)"),
    PseudoSpec("MOV", slots("R:rd", "R:rs"), _expand_mov, "ADDI rd, rs, 0"),
    PseudoSpec("NEG", slots("R:rd", "R:rs"), _expand_neg, "SUB rd, r0, rs"),
    PseudoSpec("SUBI", slots("R:rd", "R:rs1", "E:imm"), _expand_subi, "ADDI rd, rs1, -imm"),
    PseudoSpec("BGT", slots("R:rs1", "R:rs2", "E:target"), _expand_swapped("BLT"), "BLT rs2, rs1, target"),
    PseudoSpec("BLE", slots("R:rs1", "R:rs2", "E:target"), _expand_swapped("BGE"), "BGE rs2, rs1, target"),
    PseudoSpec("BEQZ", slots("R:rs1", "E:target"), _expand_vs_zero("BEQ"), "BEQ rs1, r0, target"),
    PseudoSpec("BNEZ", slots("R:rs1", "E:target"), _expand_vs_zero("BNE"), "BNE rs1, r0, target"),
    PseudoSpec("J", slots("E:target"), _expand_j, "JMP target"),
    PseudoSpec("CALL", slots("E:target"), _expand_call, "JAL ra, target"),
    PseudoSpec("RET", (), _expand_ret, "JALR r0, ra, 0"),
)

PSEUDO_BY_MNEMONIC: dict[str, PseudoSpec] = {p.mnemonic: p for p in PSEUDO_INSTRUCTIONS}
ALL_MNEMONICS = tuple(sorted(set(INSN_BY_MNEMONIC) | set(PSEUDO_BY_MNEMONIC)))


# =============================================================================
# Decoder (inverse of the encoders; used for verification, listings and
# disassembly)
# =============================================================================

@dataclass(frozen=True)
class Decoded:
    word: int
    valid: bool
    text: str
    spec: InsnSpec | None = None
    reason: str = ""

    @property
    def fu(self) -> FU | None:
        return self.spec.fu if self.spec is not None else None


def _target_text(target: int) -> str:
    return f"0x{target:08X}" if 0 <= target <= ADDR_MAX else str(target)


def _mem_text(base: int, offset: int) -> str:
    if offset == 0:
        return f"[r{base}]"
    return f"[r{base} + {offset}]" if offset > 0 else f"[r{base} - {-offset}]"


def decode(word: int, pc: int = 0) -> Decoded:
    """Decode one word into canonical, re-assemblable text."""
    if not 0 <= word <= WORD_MASK:
        raise ValueError(f"not a 32-bit word: {word!r}")

    def illegal(reason: str) -> Decoded:
        return Decoded(word, False, f".word 0x{word:08X}", None, reason)

    raw_opcode = F_OPCODE.extract(word)
    try:
        op = Opcode(raw_opcode)
    except ValueError:
        return illegal(f"reserved opcode 0x{raw_opcode:02X}")
    a, b, c, d = F_A.extract(word), F_B.extract(word), F_C.extract(word), F_D.extract(word)
    fn = F_FUNCT.extract(word)
    imm16 = F_IMM16.extract(word)
    spec = INSN_BY_OPCODE.get(op)

    def ok(text: str, which: InsnSpec | None = None) -> Decoded:
        return Decoded(word, True, text, which or spec)

    if op is Opcode.ILLEGAL:
        return illegal("opcode 0x00 is the architectural ILLEGAL trap")
    if op is Opcode.NOP:
        return ok("NOP") if F_N_RSVD.extract(word) == 0 else illegal("NOP with non-zero reserved bits")
    if op is Opcode.HALT:
        return ok(f"HALT {imm16}") if a == 0 and b == 0 else illegal("HALT with non-zero register fields")
    if op is Opcode.DFSYNC:
        mask, scope = F_SYNC_MASK.extract(word), F_SYNC_SCOPE.extract(word)
        if b or F_SYNC_RSVD.extract(word) or mask & SYNC_MASK_RESERVED:
            return illegal("DFSYNC with non-zero reserved bits")
        if scope not in SYNC_SCOPE_SYMBOLS.values():
            return illegal(f"DFSYNC reserved scope {scope}")
        mask_text = "|".join(fu.name for fu in FU if mask & (1 << fu)) or "0"
        return ok(f"DFSYNC {a}, {mask_text}, {SyncScope(scope).name}")
    if op is Opcode.ALU_R:
        alu = ALU_R_BY_FUNCT.get(fn)
        if alu is None:
            return illegal(f"undefined ALU function 0x{fn:02X}")
        if d:
            return illegal("ALU register operation with non-zero D field")
        return ok(f"{alu.mnemonic} r{a}, r{b}, r{c}", alu)
    if op in (Opcode.ADDI, Opcode.SLTI):
        return ok(f"{op.name} r{a}, r{b}, {from_twos(imm16, 16)}")
    if op in (Opcode.ANDI, Opcode.ORI, Opcode.XORI):
        return ok(f"{op.name} r{a}, r{b}, 0x{imm16:04X}")
    if op is Opcode.SHIFTI:
        shift = SHIFT_BY_TYPE.get(F_SH_TYPE.extract(word))
        if shift is None or F_SH_RSVD.extract(word):
            return illegal("SHIFTI with reserved shift type or bits")
        return ok(f"{shift.mnemonic} r{a}, r{b}, {F_SH_AMT.extract(word)}", shift)
    if op is Opcode.LUI:
        return ok(f"LUI r{a}, 0x{imm16:04X}") if b == 0 else illegal("LUI with non-zero B field")
    if op in (Opcode.VADD, Opcode.VSUB, Opcode.VMUL, Opcode.VDOT, Opcode.VREDUCE, Opcode.VBCAST):
        ew_raw = F_V_EW.extract(fn)
        if ew_raw not in (e.value for e in ElemWidth):
            return illegal(f"reserved element width {ew_raw}")
        ew = ElemWidth(ew_raw)
        sat, uns, opx = bool(F_V_SAT.extract(fn)), bool(F_V_UNS.extract(fn)), F_V_OPX.extract(fn)
        if op in (Opcode.VADD, Opcode.VSUB):
            if d or opx or (uns and not sat):
                return illegal(f"{op.name} with reserved bits or .U without .SAT")
            sfx = f".{ew.name}" + (".SAT" if sat else "") + (".U" if uns else "")
            return ok(f"{op.name}{sfx} v{a}, v{b}, v{c}")
        if op is Opcode.VMUL:
            if d or opx or sat or uns:
                return illegal("VMUL with reserved bits")
            return ok(f"VMUL.{ew.name} v{a}, v{b}, v{c}")
        if op is Opcode.VDOT:
            if sat or opx:
                return illegal("VDOT with reserved bits")
            return ok(f"VDOT.{ew.name}{'.U' if uns else ''} r{a}, v{b}, v{c}, r{d}")
        if op is Opcode.VREDUCE:
            red = ReduceOp(opx)
            if c or d or sat or (uns and red not in (ReduceOp.MAX, ReduceOp.MIN)):
                return illegal("VREDUCE with reserved bits")
            return ok(f"VREDUCE.{red.name}.{ew.name}{'.U' if uns else ''} r{a}, v{b}")
        if c or sat or uns or opx > 1:
            return illegal("VBCAST with reserved bits")
        if opx == 0:
            return ok(f"VBCAST.{ew.name} v{a}, r{b}") if d == 0 else illegal("VBCAST scalar with lane bits")
        if d >= ew.lanes:
            return illegal(f"VBCAST lane {d} out of range for .{ew.name}")
        return ok(f"VBCAST.{ew.name} v{a}, v{b}[{d}]")
    if op is Opcode.MATMUL_4X4_INT:
        itype_raw, acc = F_T_ITYPE.extract(fn), F_T_ACC.extract(fn)
        if itype_raw not in (t.value for t in TensorIType) or F_T_RSVD.extract(fn):
            return illegal("MATMUL with reserved type or bits")
        if a >= NUM_TREGS or (acc and d >= NUM_TREGS) or (not acc and d):
            return illegal("MATMUL with invalid tile register")
        text = f"MATMUL_4X4_INT.{TensorIType(itype_raw).name} t{a}, v{b}, v{c}"
        return ok(text + (f", t{d}" if acc else ""))
    if op in (Opcode.LOAD_S, Opcode.STORE_S, Opcode.LOAD_V, Opcode.STORE_V):
        offset = from_twos(imm16, 16)
        scalar = op in (Opcode.LOAD_S, Opcode.STORE_S)
        if offset % (WORD_BYTES if scalar else VLEN_BYTES):
            return illegal(f"{op.name} with misaligned offset {offset}")
        return ok(f"{op.name} {'r' if scalar else 'v'}{a}, {_mem_text(b, offset)}")
    if op in (Opcode.BURST_LOAD, Opcode.BURST_STORE):
        if F_X_RSVD.extract(fn):
            return illegal("burst with reserved bits")
        beats = d + 1
        if F_X_TGT.extract(fn):
            if a >= NUM_TREGS or beats != TILE_BEATS:
                return illegal("tile burst with invalid tile or beat count")
            reg = f"t{a}"
        else:
            if a + beats > NUM_VREGS:
                return illegal("vector burst past v31")
            reg = f"v{a}"
        return ok(f"{op.name} {reg}, [r{b}], {beats}" + (f", r{c}" if c else ""))
    if op is Opcode.JMP:
        return ok(f"JMP {_target_text(pc + 4 * from_twos(F_IMM26.extract(word), 26))}")
    if op is Opcode.JAL:
        return ok(f"JAL r{a}, {_target_text(pc + 4 * from_twos(F_IMM21.extract(word), 21))}")
    if op is Opcode.JALR:
        return ok(f"JALR r{a}, r{b}, {from_twos(imm16, 16)}")
    if op in (Opcode.BEQ, Opcode.BNE, Opcode.BLT, Opcode.BGE):
        return ok(f"{op.name} r{a}, r{b}, {_target_text(pc + 4 * from_twos(imm16, 16))}")
    return illegal(f"opcode {op.name} has no decoder")


def assemble_canonical(text: str, pc: int) -> int:
    """Assemble one symbol-free machine instruction (decoder output) at pc."""
    tokens = lex_line(text, "<canonical>", 1)
    if not tokens or tokens[0].kind is not TokKind.IDENT:
        raise AsmError(f"not an instruction: '{text}'")
    head = tokens[0]
    base, *raw = head.text.split(".")
    spec = INSN_BY_MNEMONIC.get(base.upper())
    if spec is None:
        raise AsmError(f"unknown machine instruction '{base}'", head.loc)
    end = end_of_line_loc(tokens, head.loc)
    ops = tuple(parse_operand(group, end) for group in split_operands(tokens[1:], end))
    mods = parse_mods(spec, raw, head.loc)
    validate_operands(spec.mnemonic, spec.sig, spec.syntax, ops, head.loc)

    def no_symbols(name: str, loc: SourceLoc) -> int:
        raise AsmError(f"symbol '{name}' in canonical text", loc)

    ctx = EncodeCtx(no_symbols, pc, pc, head.loc, lambda message, loc: None)
    return spec.encoder(spec, mods, ops, ctx)


# =============================================================================
# Table self-consistency
# =============================================================================

def _check_coverage(fields: Iterable[BitField], expected: int, what: str) -> None:
    used = 0
    for fld in fields:
        if used & fld.mask:
            raise RuntimeError(f"{what}: field {fld} overlaps another field")
        used |= fld.mask
    if used != expected:
        raise RuntimeError(f"{what}: fields cover 0x{used:08X}, expected 0x{expected:08X}")


def check_isa_tables() -> None:
    """Fail fast if the opcode tables or field layouts are inconsistent."""
    for fmt, fields in FORMAT_FIELDS.items():
        _check_coverage(fields, WORD_MASK, f"format {fmt.value}")
    for name, (parent, children) in SUBFIELD_GROUPS.items():
        _check_coverage(children, parent.mask, name)
    seen: set[str] = set()
    for spec in INSTRUCTIONS:
        if spec.mnemonic in seen or spec.mnemonic != spec.mnemonic.upper() or "." in spec.mnemonic:
            raise RuntimeError(f"bad or duplicate mnemonic {spec.mnemonic}")
        seen.add(spec.mnemonic)
        if spec.fu is FU.XU:
            raise RuntimeError(f"{spec.mnemonic} uses the reserved XU port")
        if any(m not in sum(MOD_GROUPS, ()) for m in spec.modifiers):
            raise RuntimeError(f"{spec.mnemonic} lists an unknown modifier")
        if spec.fmt is Fmt.I and spec.encoder in (enc_alu_i,) and spec.imm not in ("s16", "u16"):
            raise RuntimeError(f"{spec.mnemonic} lacks an immediate kind")
    clash = seen & set(PSEUDO_BY_MNEMONIC)
    if clash:
        raise RuntimeError(f"pseudo-instructions shadow machine instructions: {sorted(clash)}")
    used_opcodes = {spec.opcode for spec in INSTRUCTIONS}
    for op in Opcode:
        if op is not Opcode.ILLEGAL and op not in used_opcodes:
            raise RuntimeError(f"opcode {op.name} has no instruction")
    if Opcode.ILLEGAL in used_opcodes:
        raise RuntimeError("opcode 0x00 must stay ILLEGAL")
    for op, group in ((Opcode.ALU_R, ALU_R_BY_FUNCT), (Opcode.SHIFTI, SHIFT_BY_TYPE)):
        members = [s for s in INSTRUCTIONS if s.opcode is op]
        if len(members) != len(group) or any(s.funct is None for s in members):
            raise RuntimeError(f"function codes under {op.name} are missing or duplicated")
    singles = [s.opcode for s in INSTRUCTIONS if s.opcode not in (Opcode.ALU_R, Opcode.SHIFTI)]
    if len(singles) != len(set(singles)):
        raise RuntimeError("an opcode is assigned to more than one instruction")
    for fn in AluFn:
        if fn.value not in ALU_R_BY_FUNCT:
            raise RuntimeError(f"ALU function {fn.name} has no instruction")
    for kind in ShiftType:
        if kind.value not in SHIFT_BY_TYPE:
            raise RuntimeError(f"shift type {kind.name} has no instruction")


# =============================================================================
# Sections, symbols and items
# =============================================================================

class SymKind(enum.Enum):
    LABEL = "label"
    EQU = "equ"
    DEFINE = "define"


@dataclass
class Symbol:
    name: str
    kind: SymKind
    loc: SourceLoc | None
    section: str | None = None
    offset: int = 0
    expr: Expr | None = None
    value: int | None = None


@dataclass
class Section:
    name: str
    base: int | None
    pad_with_nop: bool
    offset: int = 0
    high_water: int = 0
    emitted: bool = False

    @property
    def address(self) -> int | None:
        return None if self.base is None else self.base + self.offset

    @property
    def directive(self) -> str:
        return "." + self.name


@dataclass
class Item:
    loc: SourceLoc
    section: str
    offset: int
    size: int


@dataclass
class InsnItem(Item):
    lowered: list[Lowered]


@dataclass
class DataItem(Item):
    width: int
    exprs: list[Expr]


@dataclass
class BytesItem(Item):
    data: bytes
    note: str


@dataclass(frozen=True)
class ListingRow:
    loc: SourceLoc
    address: int
    data: bytes
    disasm: str | None
    fu: FU | None
    first: bool


# =============================================================================
# Sparse memory image
# =============================================================================

class SparseImage:
    """Byte-addressed image that refuses to initialise any byte twice."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._data: dict[int, int] = {}
        self._owner: dict[int, SourceLoc] = {}

    @property
    def empty(self) -> bool:
        return not self._data

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def low(self) -> int:
        return min(self._data)

    @property
    def high(self) -> int:
        return max(self._data)

    def write(self, address: int, data: bytes, loc: SourceLoc) -> None:
        if not data:
            return
        if address < 0 or address + len(data) - 1 > ADDR_MAX:
            raise AsmError(f"{len(data)} byte(s) at 0x{address:X} fall outside the 32-bit address space", loc)
        for i in range(len(data)):
            owner = self._owner.get(address + i)
            if owner is not None:
                raise AsmError(
                    f"address 0x{address + i:08X} in {self.name} is already initialised by "
                    f"{owner.file}:{owner.line}", loc)
        for i, byte in enumerate(data):
            self._data[address + i] = byte
            self._owner[address + i] = loc

    def merge(self, other: SparseImage) -> None:
        for address in sorted(other._data):
            self.write(address, bytes((other._data[address],)), other._owner[address])

    def to_words(self, base: int, depth: int | None, fill: int) -> list[int]:
        if base % WORD_BYTES:
            raise AsmError(f"image base 0x{base:X} is not 4-byte aligned")
        count = 0
        if self._data:
            if self.low < base:
                raise AsmError(
                    f"{self.name} has data at 0x{self.low:08X}, below the image base 0x{base:08X} (adjust --base)")
            count = (self.high - base) // WORD_BYTES + 1
        if depth is not None:
            if count > depth:
                raise AsmError(f"{self.name} needs {count} words but --depth is {depth}")
            count = depth
        fill_bytes = fill.to_bytes(WORD_BYTES, "little")
        words: list[int] = []
        for index in range(count):
            address = base + index * WORD_BYTES
            raw = bytes(self._data.get(address + k, fill_bytes[k]) for k in range(WORD_BYTES))
            words.append(int.from_bytes(raw, "little"))
        return words


# =============================================================================
# Assembler
# =============================================================================

@dataclass
class AsmOptions:
    text_base: int = 0
    data_base: int | None = None
    include_dirs: tuple[str, ...] = ()
    defines: dict[str, int] = field(default_factory=dict)
    verify: bool = True
    split_sections: bool = False
    max_errors: int = 100


@dataclass
class Program:
    source_name: str
    sections: dict[str, Section]
    symbols: dict[str, Symbol]
    symbol_values: dict[str, int]
    globals: set[str]
    images: dict[str, SparseImage]
    listing: list[ListingRow]
    warnings: list[AsmError]
    split_sections: bool

    def merged_image(self) -> SparseImage:
        merged = SparseImage("memory image")
        for name in ("text", "data"):
            merged.merge(self.images[name])
        return merged


_END_OF_FILE = object()
NOP_WORD = pack((F_OPCODE, int(Opcode.NOP)), (F_N_RSVD, 0))


class Assembler:
    """Two-pass SilicaFlux assembler.

    Pass 1 lexes and parses every line, validates mnemonics, modifiers and
    operand shapes, lowers pseudo-instructions, assigns each statement a
    section offset and records symbols.  Section bases are then fixed.
    Pass 2 evaluates every expression against the complete symbol table,
    encodes instruction words, verifies each word by decoding it and
    re-encoding the canonical text, and writes bytes into the per-section
    images with overlap detection.
    """

    def __init__(self, options: AsmOptions | None = None) -> None:
        self.opt = options or AsmOptions()
        for name, value in (("text base", self.opt.text_base), ("data base", self.opt.data_base)):
            if value is not None and (not 0 <= value <= ADDR_MAX or value % WORD_BYTES):
                raise AsmError(f"{name} 0x{value:X} must be a 4-byte aligned 32-bit address")
        data_base = self.opt.data_base
        if data_base is None and self.opt.split_sections:
            data_base = 0
        self.sections = {
            "text": Section("text", self.opt.text_base, pad_with_nop=True),
            "data": Section("data", data_base, pad_with_nop=False),
        }
        self.cur = self.sections["text"]
        self.symbols: dict[str, Symbol] = {}
        self.globals: dict[str, SourceLoc] = {}
        self.items: list[Item] = []
        self.errors: list[AsmError] = []
        self.warnings: list[AsmError] = []
        self._include_real: list[str] = []
        self._resolving: list[str] = []
        for name, value in sorted(self.opt.defines.items()):
            if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_.$]*", name) or is_register_name(name):
                raise AsmError(f"invalid symbol name '{name}' in -D")
            self.symbols[name] = Symbol(name, SymKind.DEFINE, None, value=value)

    # ---------------------------------------------------------------- driver

    def assemble_file(self, path: str) -> Program:
        return self.assemble_source(read_source(path), path)

    def assemble_source(self, text: str, filename: str = "<input>") -> Program:
        images: dict[str, SparseImage] = {}
        listing: list[ListingRow] = []
        values: dict[str, int] = {}
        try:
            if os.path.isfile(filename):
                self._include_real.append(os.path.realpath(filename))
            self._pass1_text(text, filename)
            self._finish_layout()
            images, listing = self._pass2()
            if not self.errors:
                for name, sym in self.symbols.items():
                    try:
                        values[name] = self._resolve(name, sym.loc or SourceLoc(filename, 0), final=True)
                    except AsmError as exc:
                        self._record(exc)
        except _TooManyErrors:
            pass
        if self.errors:
            raise AssemblyFailed(_by_location(self.errors), _by_location(self.warnings))
        self.warnings = _by_location(self.warnings)
        return Program(filename, self.sections, self.symbols, values, set(self.globals), images, listing,
                       self.warnings, self.opt.split_sections)

    def _record(self, error: AsmError) -> None:
        self.errors.append(error)
        if len(self.errors) >= self.opt.max_errors:
            self.errors.append(AsmError(f"too many errors ({self.opt.max_errors}); stopping"))
            raise _TooManyErrors()

    def _warn(self, message: str, loc: SourceLoc | None) -> None:
        self.warnings.append(AsmError(message, loc))

    # ---------------------------------------------------------------- pass 1

    def _pass1_text(self, text: str, filename: str) -> None:
        for lineno, line in enumerate(text.splitlines(), 1):
            try:
                if self._process_line(line, filename, lineno) is _END_OF_FILE:
                    return
            except AsmError as exc:
                self._record(exc)

    def _process_line(self, line: str, filename: str, lineno: int) -> object:
        tokens = lex_line(line, filename, lineno)
        if not tokens:
            return None
        end = end_of_line_loc(tokens, SourceLoc(filename, lineno, 1, line))
        i = 0
        while i + 1 < len(tokens) and tokens[i].kind is TokKind.IDENT and tokens[i + 1].is_op(":"):
            self._define_label(tokens[i])
            i += 2
        rest = tokens[i:]
        if not rest:
            return None
        head = rest[0]
        if head.kind is not TokKind.IDENT:
            raise AsmError(f"expected an instruction, directive or label, found '{head.text}'", head.loc)
        if len(rest) >= 2 and rest[1].is_op("="):
            self._define_equ(head, rest[2:], end)
            return None
        if head.text.startswith(".") and head.text != ".":
            return self._directive(head, rest[1:], end)
        self._instruction(head, rest[1:], end)
        return None

    def _check_symbol_name(self, tok: Token) -> None:
        if tok.kind is not TokKind.IDENT or tok.text == ".":
            raise AsmError(f"invalid symbol name '{tok.text}'", tok.loc)
        if is_register_name(tok.text):
            raise AsmError(f"'{tok.text}' is a register name and cannot be used as a symbol", tok.loc)
        prev = self.symbols.get(tok.text)
        if prev is not None:
            where = f"first defined at {prev.loc}" if prev.loc else "defined on the command line"
            raise AsmError(f"duplicate symbol '{tok.text}' ({where})", tok.loc)

    def _define_label(self, tok: Token) -> None:
        self._check_symbol_name(tok)
        self.symbols[tok.text] = Symbol(tok.text, SymKind.LABEL, tok.loc, self.cur.name, self.cur.offset)

    def _define_equ(self, name_tok: Token, expr_tokens: Sequence[Token], end: SourceLoc) -> None:
        self._check_symbol_name(name_tok)
        if not expr_tokens:
            raise AsmError(f"missing value for '{name_tok.text}'", end)
        expr = parse_expression(expr_tokens, end)
        self.symbols[name_tok.text] = Symbol(name_tok.text, SymKind.EQU, name_tok.loc, self.cur.name,
                                             self.cur.offset, expr=expr)

    def _resolve(self, name: str, loc: SourceLoc, final: bool) -> int:
        sym = self.symbols.get(name)
        if sym is None:
            if final:
                raise AsmError(f"undefined symbol '{name}'{_suggest(name, self.symbols)}", loc)
            raise Unresolved(name, loc)
        if sym.kind is SymKind.DEFINE:
            return cast(int, sym.value)
        section = self.sections[cast(str, sym.section)]
        if sym.kind is SymKind.LABEL:
            if section.base is None:
                raise Unresolved(name, loc)
            return section.base + sym.offset
        if sym.value is not None:
            return sym.value
        if name in self._resolving:
            chain = " -> ".join(self._resolving[self._resolving.index(name):] + [name])
            raise AsmError(f"circular symbol definition: {chain}", loc)
        self._resolving.append(name)
        try:
            here = None if section.base is None else section.base + sym.offset
            value = evaluate(cast(Expr, sym.expr), lambda n, l: self._resolve(n, l, final), here)
        finally:
            self._resolving.pop()
        sym.value = value
        return value

    def _eval_pass1(self, expr: Expr, context: str) -> int:
        try:
            return evaluate(expr, lambda n, l: self._resolve(n, l, final=False), self.cur.address)
        except Unresolved as exc:
            if exc.name == ".":
                raise AsmError(f"{context} uses '.', which is unknown until the {self.cur.directive} base is fixed",
                               exc.loc) from None
            raise AsmError(
                f"{context} must be computable in pass 1, but '{exc.name}' is not defined yet "
                f"(or lies in a section whose base is not fixed yet)", exc.loc) from None

    def _try_eval_pass1(self, expr: Expr) -> int | None:
        try:
            return evaluate(expr, lambda n, l: self._resolve(n, l, final=False), self.cur.address)
        except Unresolved:
            return None

    def _emit(self, item: Item) -> None:
        sec = self.sections[item.section]
        end = item.offset + item.size
        limit = ADDR_MAX + 1 - (sec.base or 0)
        if end > limit:
            raise AsmError(f"{sec.directive} section grows past the end of the 32-bit address space", item.loc)
        self.items.append(item)
        sec.offset = end
        sec.high_water = max(sec.high_water, end)
        sec.emitted = True

    def _instruction(self, head: Token, operand_tokens: Sequence[Token], end: SourceLoc) -> None:
        base, *raw_mods = head.text.split(".")
        key = base.upper()
        pseudo = PSEUDO_BY_MNEMONIC.get(key)
        spec = INSN_BY_MNEMONIC.get(key)
        if pseudo is None and spec is None:
            raise AsmError(f"unknown instruction '{base}'{_suggest(key, ALL_MNEMONICS, 0.6)}", head.loc)
        if pseudo is not None and raw_mods:
            raise AsmError(f"pseudo-instruction {key} takes no modifiers", head.loc)
        mods = parse_mods(spec, raw_mods, head.loc) if spec is not None else NO_MODS
        ops = tuple(parse_operand(group, end) for group in split_operands(operand_tokens, end))
        if pseudo is not None:
            validate_operands(key, pseudo.sig, pseudo.syntax, ops, head.loc)
            lowered = pseudo.expand(ops, head.loc, self._try_eval_pass1)
        else:
            spec = cast(InsnSpec, spec)
            validate_operands(spec.mnemonic, spec.sig, spec.syntax, ops, head.loc)
            lowered = [Lowered(spec, mods, ops)]
        if self.cur.offset % WORD_BYTES:
            raise AsmError(
                f"instruction at unaligned {self.cur.directive} offset 0x{self.cur.offset:X}; "
                f"insert '.align 4' before it", head.loc)
        loc = head.loc.with_col(1)
        self._emit(InsnItem(loc, self.cur.name, self.cur.offset, WORD_BYTES * len(lowered), lowered))

    # ------------------------------------------------------------ directives

    def _directive(self, head: Token, arg_tokens: Sequence[Token], end: SourceLoc) -> object:
        name = head.text.lower()
        handler = _DIRECTIVES.get(name)
        if handler is None:
            raise AsmError(f"unknown directive '{head.text}'{_suggest(name, _DIRECTIVES, 0.6)}", head.loc)
        return handler(self, head, split_operands(arg_tokens, end), end)

    def _exprs(self, args: Sequence[Sequence[Token]], end: SourceLoc) -> list[Expr]:
        return [parse_expression(arg, end) for arg in args]

    def _arg_count(self, head: Token, args: Sequence[Sequence[Token]], low: int, high: int, usage: str) -> None:
        if not low <= len(args) <= high:
            raise AsmError(f"usage: {usage}", head.loc)

    def _d_text(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        self._arg_count(head, args, 0, 0, head.text.lower())
        self.cur = self.sections["text"]

    def _d_data(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        self._arg_count(head, args, 0, 0, head.text.lower())
        self.cur = self.sections["data"]

    def _d_section(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        self._arg_count(head, args, 1, 1, ".section .text|.data")
        if len(args[0]) != 1 or args[0][0].kind is not TokKind.IDENT:
            raise AsmError("usage: .section .text|.data", head.loc)
        name = args[0][0].text.lower().lstrip(".")
        if name not in self.sections:
            raise AsmError(f"unknown section '{args[0][0].text}' (supported: .text, .data)", args[0][0].loc)
        self.cur = self.sections[name]

    def _d_org(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        self._arg_count(head, args, 1, 1, ".org address")
        value = self._eval_pass1(parse_expression(args[0], end), ".org")
        if not 0 <= value <= ADDR_MAX:
            raise AsmError(f".org address {value:#x} is outside the 32-bit address space", head.loc)
        sec = self.cur
        if sec.base is None:
            if sec.emitted:
                raise AsmError(
                    f".org after content in {sec.directive}, whose base is automatic; place .org first or "
                    f"give --data-base", head.loc)
            if value % WORD_BYTES:
                raise AsmError(f".org {value:#x} fixes the {sec.directive} base and must be 4-byte aligned", head.loc)
            sec.base = value
            sec.offset = 0
            return
        if value < sec.base:
            raise AsmError(f".org {value:#x} is below the {sec.directive} base 0x{sec.base:X}", head.loc)
        sec.offset = value - sec.base

    def _d_align(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        self._arg_count(head, args, 1, 2, ".align bytes[, fill_byte]")
        exprs = self._exprs(args, end)
        align = self._eval_pass1(exprs[0], ".align")
        if not _is_pow2(align) or align > MAX_ALIGN:
            raise AsmError(f".align {align}: alignment must be a power of two between 1 and {MAX_ALIGN}", head.loc)
        fill = None
        if len(exprs) == 2:
            fill = self._eval_pass1(exprs[1], ".align fill")
            if not 0 <= fill <= 0xFF:
                raise AsmError(f".align fill byte {fill} out of range 0..255", exprs[1].loc)
        sec = self.cur
        if sec.base is None and align > DATA_AUTO_ALIGN:
            raise AsmError(
                f".align {align} in {sec.directive} needs a fixed base (give --data-base or a leading .org); "
                f"automatic placement only guarantees {DATA_AUTO_ALIGN}-byte alignment", head.loc)
        address = (sec.base or 0) + sec.offset
        pad = (-address) % align
        if pad:
            data = self._padding(sec, address, pad, fill)
            self._emit(BytesItem(head.loc.with_col(1), sec.name, sec.offset, pad, data, "align"))

    @staticmethod
    def _padding(sec: Section, address: int, pad: int, fill: int | None) -> bytes:
        if fill is not None or not sec.pad_with_nop:
            return bytes((fill or 0,)) * pad
        lead = min((-address) % WORD_BYTES, pad)
        out = bytearray(lead)
        nop = NOP_WORD.to_bytes(WORD_BYTES, "little")
        while pad - len(out) >= WORD_BYTES:
            out += nop
        out += bytes(pad - len(out))
        return bytes(out)

    def _d_values(self, head: Token, args: list[list[Token]], end: SourceLoc, width: int) -> None:
        if not args:
            raise AsmError(f"{head.text} requires at least one value", head.loc)
        exprs = self._exprs(args, end)
        sec = self.cur
        if width > 1 and ((sec.base or 0) + sec.offset) % width:
            self._warn(f"{head.text.lower()} data at unaligned {sec.directive} offset 0x{sec.offset:X}", head.loc)
        self._emit(DataItem(head.loc.with_col(1), sec.name, sec.offset, width * len(exprs), width, exprs))

    def _d_word(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        self._d_values(head, args, end, 4)

    def _d_half(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        self._d_values(head, args, end, 2)

    def _d_byte(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        self._d_values(head, args, end, 1)

    def _d_space(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        self._arg_count(head, args, 1, 2, f"{head.text.lower()} bytes[, fill_byte]")
        exprs = self._exprs(args, end)
        count = self._eval_pass1(exprs[0], head.text.lower())
        if not 0 <= count <= MAX_SPACE_BYTES:
            raise AsmError(f"{head.text.lower()} size {count} out of range 0..{MAX_SPACE_BYTES}", exprs[0].loc)
        fill = 0
        if len(exprs) == 2:
            fill = self._eval_pass1(exprs[1], f"{head.text.lower()} fill")
            if not 0 <= fill <= 0xFF:
                raise AsmError(f"fill byte {fill} out of range 0..255", exprs[1].loc)
        if count:
            sec = self.cur
            self._emit(BytesItem(head.loc.with_col(1), sec.name, sec.offset, count, bytes((fill,)) * count, "space"))

    def _d_ascii(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        if not args:
            raise AsmError(f"{head.text} requires at least one string", head.loc)
        terminate = head.text.lower() in (".asciz", ".string")
        data = bytearray()
        for arg in args:
            if len(arg) != 1 or arg[0].kind is not TokKind.STRING:
                raise AsmError(f"{head.text} operands must be string literals", arg[0].loc)
            data += cast(bytes, arg[0].value)
            if terminate:
                data.append(0)
        if data:
            sec = self.cur
            self._emit(BytesItem(head.loc.with_col(1), sec.name, sec.offset, len(data), bytes(data), "string"))

    def _d_equ(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        if len(args) != 2 or len(args[0]) != 1:
            raise AsmError(f"usage: {head.text.lower()} NAME, expression", head.loc)
        self._define_equ(args[0][0], args[1], end)

    def _d_global(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        if not args:
            raise AsmError(f"{head.text} requires at least one symbol name", head.loc)
        for arg in args:
            if len(arg) != 1 or arg[0].kind is not TokKind.IDENT or is_register_name(arg[0].text):
                raise AsmError(f"{head.text} operands must be symbol names", arg[0].loc)
            self.globals.setdefault(arg[0].text, arg[0].loc)

    def _d_include(self, head: Token, args: list[list[Token]], end: SourceLoc) -> None:
        if len(args) != 1 or len(args[0]) != 1 or args[0][0].kind is not TokKind.STRING:
            raise AsmError('usage: .include "file"', head.loc)
        rel = cast(bytes, args[0][0].value).decode("utf-8", errors="replace")
        here_dir = os.path.dirname(head.loc.file) if os.path.isfile(head.loc.file) else os.getcwd()
        candidates = [rel] if os.path.isabs(rel) else [os.path.join(here_dir, rel)] + [
            os.path.join(d, rel) for d in self.opt.include_dirs]
        path = next((c for c in candidates if os.path.isfile(c)), None)
        if path is None:
            raise AsmError(f"cannot find include file '{rel}' (searched: {', '.join(candidates)})", args[0][0].loc)
        real = os.path.realpath(path)
        if real in self._include_real:
            raise AsmError(f"recursive .include of '{rel}'", args[0][0].loc)
        if len(self._include_real) >= MAX_INCLUDE_DEPTH:
            raise AsmError(f".include nesting deeper than {MAX_INCLUDE_DEPTH}", args[0][0].loc)
        text = read_source(path)
        self._include_real.append(real)
        try:
            self._pass1_text(text, os.path.normpath(path))
        finally:
            self._include_real.pop()

    def _d_end(self, head: Token, args: list[list[Token]], end: SourceLoc) -> object:
        self._arg_count(head, args, 0, 0, ".end")
        return _END_OF_FILE

    # ------------------------------------------------------- layout fix-up

    def _finish_layout(self) -> None:
        text, data = self.sections["text"], self.sections["data"]
        if data.base is None:
            data.base = _align_up(cast(int, text.base) + text.high_water, DATA_AUTO_ALIGN)
            if data.base + data.high_water - 1 > ADDR_MAX and data.high_water:
                self._record(AsmError(".data section placed after .text overflows the 32-bit address space"))
        for name, loc in sorted(self.globals.items()):
            if name not in self.symbols:
                self._record(AsmError(f"global symbol '{name}' is never defined", loc))

    # ---------------------------------------------------------------- pass 2

    def _final(self, name: str, loc: SourceLoc) -> int:
        return self._resolve(name, loc, final=True)

    def _pass2(self) -> tuple[dict[str, SparseImage], list[ListingRow]]:
        images = {name: SparseImage(f"{sec.directive} section") for name, sec in self.sections.items()}
        listing: list[ListingRow] = []
        for item in self.items:
            try:
                self._emit_item(item, images, listing)
            except AsmError as exc:
                self._record(exc)
        return images, listing

    def _emit_item(self, item: Item, images: dict[str, SparseImage], listing: list[ListingRow]) -> None:
        address = cast(int, self.sections[item.section].base) + item.offset
        if isinstance(item, InsnItem):
            data = bytearray()
            rows: list[ListingRow] = []
            for k, low in enumerate(item.lowered):
                pc = address + WORD_BYTES * k
                ctx = EncodeCtx(self._final, pc, address, item.loc, self._warn)
                try:
                    word = low.spec.encoder(low.spec, low.mods, low.operands, ctx)
                except EncodingError as exc:
                    raise AsmError(f"internal encoding error in {low.spec.mnemonic}: {exc}", item.loc) from None
                decoded = decode(word, pc)
                if self.opt.verify:
                    self._verify(word, pc, decoded, item.loc)
                rows.append(ListingRow(item.loc, pc, word.to_bytes(WORD_BYTES, "little"), decoded.text,
                                       low.spec.fu, k == 0))
                data += word.to_bytes(WORD_BYTES, "little")
            images[item.section].write(address, bytes(data), item.loc)
            listing.extend(rows)
        elif isinstance(item, DataItem):
            data = bytearray()
            bits = 8 * item.width
            for index, expr in enumerate(item.exprs):
                here = address + index * item.width
                try:
                    value = evaluate(expr, self._final, here)
                except Unresolved as exc:
                    raise AsmError(f"undefined symbol '{exc.name}'", exc.loc) from None
                if not -(1 << (bits - 1)) <= value <= (1 << bits) - 1:
                    raise AsmError(f"value {value} does not fit in {bits} bits", expr.loc)
                data += to_twos(value, bits).to_bytes(item.width, "little")
            images[item.section].write(address, bytes(data), item.loc)
            listing.append(ListingRow(item.loc, address, bytes(data), None, None, True))
        elif isinstance(item, BytesItem):
            images[item.section].write(address, item.data, item.loc)
            listing.append(ListingRow(item.loc, address, item.data, None, None, True))

    @staticmethod
    def _verify(word: int, pc: int, decoded: Decoded, loc: SourceLoc) -> None:
        if not decoded.valid:
            raise AsmError(f"internal error: encoder produced 0x{word:08X}, which the decoder rejects "
                           f"({decoded.reason})", loc)
        try:
            again = assemble_canonical(decoded.text, pc)
        except AsmError as exc:
            raise AsmError(f"internal error: canonical text '{decoded.text}' does not re-assemble: {exc.message}",
                           loc) from None
        if again != word:
            raise AsmError(f"internal error: round-trip mismatch for '{decoded.text}': "
                           f"0x{word:08X} != 0x{again:08X}", loc)


_DirectiveHandler = Callable[[Assembler, Token, list, SourceLoc], object]
_DIRECTIVES: dict[str, _DirectiveHandler] = {
    ".text": Assembler._d_text,
    ".data": Assembler._d_data,
    ".section": Assembler._d_section,
    ".org": Assembler._d_org,
    ".align": Assembler._d_align,
    ".word": Assembler._d_word,
    ".half": Assembler._d_half,
    ".byte": Assembler._d_byte,
    ".space": Assembler._d_space,
    ".zero": Assembler._d_space,
    ".ascii": Assembler._d_ascii,
    ".asciz": Assembler._d_ascii,
    ".string": Assembler._d_ascii,
    ".equ": Assembler._d_equ,
    ".set": Assembler._d_equ,
    ".global": Assembler._d_global,
    ".globl": Assembler._d_global,
    ".include": Assembler._d_include,
    ".end": Assembler._d_end,
}


def read_source(path: str) -> str:
    try:
        if path == "-":
            return sys.stdin.read()
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise AsmError(f"cannot read '{path}': {exc.strerror or exc}") from None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AsmError(f"'{path}' is not valid UTF-8 (byte offset {exc.start})") from None


def assemble(source: str, filename: str = "<input>", options: AsmOptions | None = None) -> Program:
    """Assemble `source` and return the Program; raises AssemblyFailed."""
    return Assembler(options).assemble_source(source, filename)


# =============================================================================
# Output formats (all render the same word list)
# =============================================================================

MIF_RUN_MIN = 4


def render_hex(words: Sequence[int], base: int, title: str) -> str:
    lines = [f"// SilicaFlux memory image: {title}",
             f"// {len(words)} x 32-bit words; line 0 = byte address 0x{base:08X}; {TOOL} {__version__}"]
    lines.extend(f"{w:08X}" for w in words)
    return "\n".join(lines) + "\n"


def render_bin(words: Sequence[int], base: int, title: str) -> bytes:
    return b"".join(w.to_bytes(WORD_BYTES, "little") for w in words)


def render_mif(words: Sequence[int], base: int, title: str) -> str:
    depth = len(words)
    digits = max(1, len(f"{depth - 1:X}"))
    lines = [f"-- SilicaFlux memory image: {title}",
             f"-- word address 0 = byte address 0x{base:08X}; {TOOL} {__version__}",
             "",
             "WIDTH=32;",
             f"DEPTH={depth};",
             "",
             "ADDRESS_RADIX=HEX;",
             "DATA_RADIX=HEX;",
             "",
             "CONTENT BEGIN"]
    i = 0
    while i < depth:
        j = i
        while j + 1 < depth and words[j + 1] == words[i]:
            j += 1
        if j - i + 1 >= MIF_RUN_MIN:
            lines.append(f"\t[{i:0{digits}X}..{j:0{digits}X}] : {words[i]:08X};")
        else:
            lines.extend(f"\t{k:0{digits}X} : {words[k]:08X};" for k in range(i, j + 1))
        i = j + 1
    lines.append("END;")
    return "\n".join(lines) + "\n"


def render_coe(words: Sequence[int], base: int, title: str) -> str:
    lines = [f"; SilicaFlux memory image: {title}",
             f"; WIDTH=32 DEPTH={len(words)}; word 0 = byte address 0x{base:08X}; {TOOL} {__version__}",
             "memory_initialization_radix=16;",
             "memory_initialization_vector="]
    last = len(words) - 1
    lines.extend(f"{w:08X}{';' if i == last else ','}" for i, w in enumerate(words))
    return "\n".join(lines) + "\n"


FORMAT_RENDERERS: dict[str, Callable[[Sequence[int], int, str], str | bytes]] = {
    "hex": render_hex,
    "bin": render_bin,
    "mif": render_mif,
    "coe": render_coe,
}


def parse_hex_image(text: str) -> list[int]:
    words: dict[int, int] = {}
    index = 0
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.split("//", 1)[0]
        for token in line.split():
            if token.startswith("@"):
                index = int(token[1:], 16)
                continue
            if not re.fullmatch(r"[0-9A-Fa-f_]+", token):
                raise AsmError(f"line {lineno}: invalid $readmemh token '{token}'")
            value = int(token.replace("_", ""), 16)
            if value > WORD_MASK:
                raise AsmError(f"line {lineno}: word '{token}' wider than 32 bits")
            words[index] = value
            index += 1
    return _dense(words)


def parse_mif_image(text: str) -> list[int]:
    body = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    header = dict((k.upper(), v.strip().upper()) for k, v in re.findall(r"(\w+)\s*=\s*([^;]+);", body.split("CONTENT")[0]))
    if header.get("WIDTH") != "32" or header.get("ADDRESS_RADIX") != "HEX" or header.get("DATA_RADIX") != "HEX":
        raise AsmError("MIF must be WIDTH=32 with HEX address and data radix")
    depth = int(header["DEPTH"])
    content = re.search(r"CONTENT\s+BEGIN(.*?)END\s*;", body, flags=re.S | re.I)
    if content is None:
        raise AsmError("MIF has no CONTENT BEGIN ... END; block")
    words: dict[int, int] = {}
    for entry in content.group(1).split(";"):
        entry = entry.strip()
        if not entry:
            continue
        addr_text, data_text = (part.strip() for part in entry.split(":"))
        value = int(data_text, 16)
        if addr_text.startswith("["):
            lo_text, hi_text = addr_text.strip("[]").split("..")
            for addr in range(int(lo_text, 16), int(hi_text, 16) + 1):
                words[addr] = value
        else:
            words[int(addr_text, 16)] = value
    dense = _dense(words)
    if len(dense) != depth:
        raise AsmError(f"MIF DEPTH={depth} but content covers {len(dense)} words")
    return dense


def parse_coe_image(text: str) -> list[int]:
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(";"))
    radix = re.search(r"memory_initialization_radix\s*=\s*(\d+)\s*;", body)
    if radix is None or radix.group(1) != "16":
        raise AsmError("COE must declare memory_initialization_radix=16")
    vector = re.search(r"memory_initialization_vector\s*=\s*(.*?);", body, flags=re.S)
    if vector is None:
        raise AsmError("COE has no memory_initialization_vector")
    items = [v for v in re.split(r"[,\s]+", vector.group(1)) if v]
    return [int(v, 16) for v in items]


def parse_bin_image(data: bytes) -> list[int]:
    if len(data) % WORD_BYTES:
        raise AsmError(f"binary image length {len(data)} is not a multiple of 4")
    return [int.from_bytes(data[i:i + WORD_BYTES], "little") for i in range(0, len(data), WORD_BYTES)]


def _dense(words: dict[int, int]) -> list[int]:
    if not words:
        return []
    return [words.get(i, 0) for i in range(max(words) + 1)]


def load_image(path: str) -> list[int]:
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise AsmError(f"cannot read '{path}': {exc.strerror or exc}") from None
    if ext == ".bin":
        return parse_bin_image(raw)
    text = raw.decode("utf-8", errors="strict")
    if ext == ".mif":
        return parse_mif_image(text)
    if ext == ".coe":
        return parse_coe_image(text)
    return parse_hex_image(text)


def write_output(path: str, content: str | bytes) -> None:
    """Write a file atomically (temp file + rename) with normal permissions."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{TOOL}.", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@dataclass(frozen=True)
class ImageJob:
    path_base: str
    title: str
    words: tuple[int, ...]
    base: int


def plan_images(program: Program, out_base: str, base: int | None, depth: int | None, fill: int) -> list[ImageJob]:
    if not 0 <= fill <= WORD_MASK:
        raise AsmError(f"--fill 0x{fill:X} is not a 32-bit value")
    jobs: list[ImageJob] = []
    if program.split_sections:
        for name in ("text", "data"):
            image = program.images[name]
            if image.empty and depth is None:
                continue
            image_base = cast(int, program.sections[name].base) if base is None else base
            words = image.to_words(image_base, depth, fill)
            jobs.append(ImageJob(f"{out_base}.{name}", f"{program.source_name} .{name}", tuple(words), image_base))
    else:
        image_base = cast(int, program.sections["text"].base) if base is None else base
        words = program.merged_image().to_words(image_base, depth, fill)
        jobs.append(ImageJob(out_base, program.source_name, tuple(words), image_base))
    if not jobs or not any(job.words for job in jobs):
        raise AsmError("nothing to output: the program is empty (use --depth to emit a filled image)")
    return jobs


# =============================================================================
# Listing, symbol table, ISA reference and SystemVerilog package
# =============================================================================

def render_listing(program: Program) -> str:
    out = [f"; SilicaFlux assembler listing -- {TOOL} {__version__}",
           f"; source: {program.source_name}",
           f"; .text base 0x{program.sections['text'].base:08X}, .data base 0x{program.sections['data'].base:08X}",
           ";",
           f"; {'LOCATION':<22} {'ADDRESS':<8}  {'DATA':<11}  {'FU':<5} {'MACHINE CODE':<40} SOURCE"]
    for row in program.listing:
        location = f"{os.path.basename(row.loc.file)}:{row.loc.line}" if row.first else ""
        source = row.loc.text.strip() if row.first else ""
        if row.disasm is not None:
            word = int.from_bytes(row.data, "little")
            out.append(f"  {location:<22} {row.address:08X}  {word:08X}     {row.fu.name if row.fu is not None else '':<5} "
                       f"{row.disasm:<40} {source}".rstrip())
            continue
        chunks = [row.data[i:i + 4] for i in range(0, len(row.data), 4)] or [b""]
        shown = chunks if len(chunks) <= 8 else chunks[:8]
        for n, chunk in enumerate(shown):
            hex_bytes = " ".join(f"{b:02X}" for b in chunk)
            src = source if n == 0 else ""
            loc_text = location if n == 0 else ""
            out.append(f"  {loc_text:<22} {row.address + 4 * n:08X}  {hex_bytes:<11}  {'':<5} {'':<40} {src}".rstrip())
        if len(chunks) > 8:
            out.append(f"  {'':<22} {'':<8}  ... {len(row.data) - 32} more byte(s)")
    return "\n".join(out) + "\n"


def render_symbols(program: Program) -> str:
    rows = []
    for name, sym in program.symbols.items():
        value = program.symbol_values[name]
        if sym.kind is SymKind.LABEL:
            kind = "T" if sym.section == "text" else "D"
        else:
            kind = "A"
        scope = "g" if name in program.globals else "l"
        shown = f"0x{value & WORD_MASK:08X}" if -(1 << 31) <= value <= WORD_MASK else str(value)
        rows.append((value, name, f"{shown}  {kind}  {scope}  {name}"))
    rows.sort(key=lambda r: (r[0], r[1]))
    header = [f"; SilicaFlux symbol table -- {program.source_name}",
              "; VALUE       K  S  NAME   (K: T=.text label, D=.data label, A=absolute; S: g=global, l=local)"]
    return "\n".join(header + [r[2] for r in rows]) + "\n"


def render_isa_table() -> str:
    out = [f"SilicaFlux ISA v1 -- {TOOL} {__version__}", "",
           "Instruction fields:"]
    for fld in (F_OPCODE, F_A, F_B, F_C, F_D, F_FUNCT, F_IMM16, F_IMM21, F_IMM26):
        out.append(f"  {str(fld):<14} {fld.width:>2} bits")
    out += ["", "Functional units (dispatch port = opcode[5:3]):"]
    out += [f"  {fu.value}  {fu.name:<6} {FU_DESCRIPTION[fu]}" for fu in FU]
    out += ["", f"  {'OPC':<5} {'FN':<5} {'FU':<6} {'FMT':<4} {'SYNTAX':<58} SEMANTICS"]
    ordered = sorted(INSTRUCTIONS, key=lambda s: (int(s.opcode), s.funct if s.funct is not None else -1))
    for spec in ordered:
        fn = f"0x{spec.funct:02X}" if spec.funct is not None else "-"
        out.append(f"  0x{int(spec.opcode):02X}  {fn:<5} {spec.fu.name:<6} {spec.fmt.value:<4} "
                   f"{spec.syntax:<58} {spec.summary}")
    out += ["", "Reserved opcodes: " + ", ".join(
        f"0x{v:02X}" for v in range(64) if v not in {int(o) for o in Opcode})]
    out += ["", "Pseudo-instructions:"]
    out += [f"  {p.syntax:<30} {p.summary}" for p in PSEUDO_INSTRUCTIONS]
    out += ["", "DFSYNC mask names: " + ", ".join(f"{k}=0x{v:02X}" for k, v in SYNC_MASK_SYMBOLS.items()),
            "DFSYNC scopes: " + ", ".join(f"{k}={v}" for k, v in SYNC_SCOPE_SYMBOLS.items())]
    return "\n".join(out) + "\n"


def render_sv_package(name: str = "silicaflux_isa_pkg") -> str:
    def enum_block(type_name: str, width: int, prefix: str, members: Iterable[tuple[str, int]]) -> list[str]:
        items = list(members)
        lines = [f"  typedef enum logic [{width - 1}:0] {{"]
        for i, (member, value) in enumerate(items):
            comma = "," if i < len(items) - 1 else ""
            lines.append(f"    {prefix}{member} = {width}'h{value:0{(width + 3) // 4}X}{comma}")
        lines.append(f"  }} {type_name};")
        return lines

    out = [f"// {name} -- SilicaFlux ISA v1 encoding, generated by {TOOL} {__version__}.",
           "// Single source of truth: sfx_asm.py.  Regenerate with: python3 sfx_asm.py --emit-pkg <file>",
           f"package {name};", "",
           "  // Architectural parameters"]
    params = [("SF_ILEN", ILEN), ("SF_NUM_SREGS", NUM_SREGS), ("SF_NUM_VREGS", NUM_VREGS),
              ("SF_NUM_TREGS", NUM_TREGS), ("SF_VLEN", VLEN), ("SF_TILE_DIM", TILE_DIM),
              ("SF_TILE_BEATS", TILE_BEATS), ("SF_MAX_BURST_BEATS", MAX_BURST_BEATS),
              ("SF_REG_SP", REG_SP), ("SF_REG_RA", REG_RA)]
    out += [f"  localparam int unsigned {p:<20} = {v};" for p, v in params]
    out += ["", "  // Instruction fields [MSB:LSB]"]
    for fld in (F_OPCODE, F_A, F_B, F_C, F_D, F_FUNCT, F_IMM16, F_IMM21, F_IMM26, F_SH_TYPE, F_SH_AMT,
                F_SYNC_MASK, F_SYNC_SCOPE, F_V_EW, F_V_SAT, F_V_UNS, F_V_OPX, F_T_ITYPE, F_T_ACC, F_X_TGT):
        tag = fld.name.upper()
        out.append(f"  localparam int unsigned SF_F_{tag}_MSB = {fld.msb};")
        out.append(f"  localparam int unsigned SF_F_{tag}_LSB = {fld.lsb};")
    out.append("")
    out += enum_block("sf_fu_e", 3, "SF_FU_", ((fu.name, fu.value) for fu in FU))
    out.append("")
    out += enum_block("sf_opcode_e", 6, "SF_OP_", ((op.name, op.value) for op in Opcode))
    out.append("")
    out += enum_block("sf_alu_fn_e", 6, "SF_ALU_", ((fn.name, fn.value) for fn in AluFn))
    out.append("")
    out += enum_block("sf_shift_e", 2, "SF_SHIFT_", ((s.name, s.value) for s in ShiftType))
    out.append("")
    out += enum_block("sf_ew_e", 2, "SF_EW_", ((e.name, e.value) for e in ElemWidth))
    out.append("")
    out += enum_block("sf_reduce_e", 2, "SF_RED_", ((r.name, r.value) for r in ReduceOp))
    out.append("")
    out += enum_block("sf_itype_e", 2, "SF_ITYPE_", ((t.name, t.value) for t in TensorIType))
    out.append("")
    out += enum_block("sf_scope_e", 2, "SF_SCOPE_", ((s.name, s.value) for s in SyncScope))
    out += ["", "  // DFSYNC FU-mask bit per dispatch port (bit 0 / SCHED reserved)"]
    out += [f"  localparam logic [7:0] SF_SYNC_{k:<8} = 8'h{v:02X};" for k, v in SYNC_MASK_SYMBOLS.items()]
    out += ["",
            "  localparam logic [31:0] SF_NOP_WORD     = 32'h%08X;" % NOP_WORD,
            "  localparam logic [31:0] SF_ILLEGAL_WORD = 32'h00000000;",
            "",
            "  // Dispatch port of an opcode (scheduler.sf / compute_tile.sf routing)",
            "  function automatic logic [2:0] sf_opcode_fu(input logic [5:0] opcode);",
            "    return opcode[5:3];",
            "  endfunction",
            "",
            "  // 1 for every defined opcode, 0 for ILLEGAL and reserved encodings",
            "  function automatic logic sf_opcode_valid(input logic [5:0] opcode);",
            "    case (opcode)"]
    valid = [op for op in Opcode if op is not Opcode.ILLEGAL]
    for i in range(0, len(valid), 4):
        chunk = ", ".join(f"SF_OP_{op.name}" for op in valid[i:i + 4])
        out.append(f"      {chunk}{':' if i + 4 >= len(valid) else ','}")
    out[-1] = out[-1].rstrip(":") + ": return 1'b1;"
    out += ["      default: return 1'b0;",
            "    endcase",
            "  endfunction",
            "",
            f"endpackage : {name}"]
    return "\n".join(out) + "\n"


def disassemble_words(words: Sequence[int], base: int) -> str:
    out = []
    for i, word in enumerate(words):
        pc = base + WORD_BYTES * i
        dec = decode(word, pc)
        fu = dec.fu.name if dec.fu is not None else "-"
        note = f"  ; {dec.reason}" if not dec.valid else ""
        out.append(f"{pc:08X}:  {word:08X}  {fu:<5} {dec.text}{note}")
    return "\n".join(out) + "\n"


# =============================================================================
# Self test
# =============================================================================

_GOLDEN: tuple[tuple[str, int, int], ...] = (
    ("ADD r1, r2, r3", 0, 0x20221800),
    ("ADDI r5, r0, -1", 0, 0x24A0FFFF),
    ("SARI r3, r4, 7", 0, 0x38640047),
    ("LUI r7, 0xDEAD", 0, 0x3CE0DEAD),
    ("VADD.I8.SAT.U v1, v2, v3", 0, 0x4022180C),
    ("VREDUCE.MAX.I16.U r4, v9", 0, 0x50890015),
    ("VBCAST.I16 v1, v2[5]", 0, 0x54220151),
    ("MATMUL_4X4_INT.U8 t1, v2, v3, t1", 0, 0x60221851),
    ("LOAD_V v3, [r4 - 32]", 0, 0xA064FFE0),
    ("BURST_LOAD t2, [r5], r6", 0, 0xA84530C1),
    ("BEQ r1, r2, 0x0", 0x10, 0xCC22FFFC),
    ("JMP 0x100", 0, 0xC0000040),
    ("JAL ra, 0x0", 0x8, 0xC7FFFFFE),
    ("DFSYNC 3, VPU|TPU, CLUSTER", 0, 0x0C600C40),
    ("NOP", 0, 0x04000000),
    ("HALT 0x2A", 0, 0x0800002A),
    ("STORE_S r9, 12(sp)", 0, 0x853E000C),
    ("VDOT.I8.U r2, v4, v5, r2", 0, 0x4C442884),
)

_SELFTEST_PROGRAM = r"""
; SilicaFlux self-test kernel: exercises every instruction, pseudo and directive
        .equ    TILE_BYTES, 64
        .set    ROWS, 4
        .global _start, result
        STACK_WORDS = 16
        .text
_start: LI      sp, stack_top
        LA      r1, mat_a
        LA      r2, mat_b
        LA      r3, result
        LI      r4, 32
        LI      r5, 0x12345678
        LI      r6, 0xFFFF0000
        LI      r7, 0xBEEF
        LI      r8, -40000
        MOV     r9, r4
        NEG     r10, r9
        SUBI    r11, r10, 3
        LOAD_V  v1, [r1]
        LOAD_V  v2, 0(r2)
        MATMUL_4X4_INT       t0, v1, v2
        MATMUL_4X4_INT.U8    t1, v1, v2, t1
        DFSYNC  0, TPU, TILE
        BURST_STORE t0, [r3]
        BURST_STORE t1, [r3], 4, r4
        BURST_LOAD  v8, [r1], 4
        BURST_LOAD  v12, (r1), 2, r4
        VADD.I8.SAT     v3, v1, v2
        VSUB.I16.SAT.U  v4, v1, v2
        VMUL            v5, v1, v2
        VDOT.I8         r12, v1, v2
        VDOT.I8.U       r12, v1, v2, r12
        VREDUCE.MIN.I8.U r13, v3
        VREDUCE          r14, v4
        VBCAST.I8       v6, r5
        VBCAST.I32      v7, v6[3]
        STORE_V v3, [r3 + 64]
        LOAD_S  r15, [r3 - 4]
        STORE_S r15, -8(sp)
        ADD     r16, r1, r2
        SUB     r16, r16, r2
        MUL     r16, r16, r4
        AND     r17, r16, r5
        OR      r17, r17, r6
        XOR     r17, r17, r7
        SHL     r18, r17, r4
        SHR     r18, r18, r4
        SAR     r18, r18, r4
        SLT     r19, r18, r17
        SLTU    r19, r18, r17
        ADDI    r20, r20, %lo(0x1234)
        ANDI    r20, r20, 0xFF00
        ORI     r20, r20, 'A'
        XORI    r20, r20, 0b1010
        SLTI    r21, r20, -1
        SHLI    r21, r21, 3
        SHRI    r21, r21, 1
        SARI    r21, r21, 31
        LUI     r22, %hi(mat_a)
        LI      r23, ROWS
loop:   SUBI    r23, r23, 1
        BNEZ    r23, loop
        BEQ     r1, r1, fwd
        BLT     r1, r2, fwd
        BGE     r2, r1, fwd
        BGT     r2, r1, fwd
        BLE     r1, r2, fwd
        BNE     r1, r2, fwd
        BEQZ    r0, fwd
        .align  16
fwd:    CALL    func
        JAL     ra, func
        JALR    r0, r1, 0
        J       done
        JMP     done
func:   RET
done:   DFSYNC  1, MEM|COMPUTE, GLOBAL
        DFSYNC  2
        NOP
        HALT    0
        .data
mat_a:  .byte   1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
mat_b:  .byte   -1, -2, -3, -4, 0x10, 0x20, 0x30, 0x40, 0, 0, 0, 0, 1, 1, 1, 1
        .align  16
result: .space  TILE_BYTES * 2
table:  .word   _start, fwd, done - _start, -1
        .half   0x1234, -2
        .asciz  "SilicaFlux\n"
        .ascii  "#;//"
        .align  4
        .space  STACK_WORDS * 4
stack_top:
        .word   .
"""

_NEGATIVE_CASES: tuple[tuple[str, str], ...] = (
    ("ADD r1, r2", "expects 3 operands"),
    ("ADD r1, r2, r32", "invalid scalar register 'r32'"),
    ("VADD v1, v2, r3", "must be a vector register"),
    ("FROB r1", "unknown instruction"),
    ("VADDD v1, v2, v3", "did you mean 'VADD'"),
    ("JMP nowhere", "undefined symbol 'nowhere'"),
    ("a: NOP\na: NOP", "duplicate symbol 'a'"),
    ("ADDI r1, r2, 40000", "out of range"),
    ("ANDI r1, r2, -1", "out of range 0..65535"),
    ("LOAD_S r1, [r2 + 2]", "multiple of 4"),
    ("LOAD_V v1, [r2 + 8]", "multiple of 16"),
    ("VBCAST.I32 v1, v2[4]", "lane 4 out of range"),
    ("BURST_LOAD v30, [r1], 4", "exceeds the vector register file"),
    ("BURST_LOAD v1, [r1]", "requires a beat count"),
    ("BURST_LOAD t1, [r1], 2", "exactly 4 beats"),
    ("BURST_LOAD v1, [r1 + 16], 2", "no address offset"),
    ("MATMUL_4X4_INT t8, v1, v2", "invalid tensor register 't8'"),
    ("VADD.U v1, v2, v3", "requires .SAT"),
    ("VADD.I8.I16 v1, v2, v3", "conflicting modifiers"),
    ("ADD.I8 r1, r2, r3", "takes no modifiers"),
    (".byte 300", "does not fit in 8 bits"),
    (".equ A, B\n.equ B, A\n.word A", "circular symbol definition"),
    (".byte 1\nNOP", "unaligned"),
    ("BEQ r1, r2, 2", "not 4-byte aligned"),
    ("DFSYNC 32", "barrier id 32 out of range"),
    ("DFSYNC 0, SCHED", "reserved"),
    (".word 1, , 2", "empty operand"),
    ("ADD r1, r2, r3 r4", "unexpected 'r4'"),
    ("LI r1, 0x1_0000_0000", "does not fit in 32 bits"),
    ("JMP 0x10000000", "out of range"),
    ('.ascii "abc', "unterminated string"),
    (".include \"no_such_file.sfa\"", "cannot find include file"),
    (".data\n.org 0x100\n.byte 1\n.org 0x10", "below the .data base"),
    (".frob 1", "unknown directive"),
    ("r1: NOP", "register name"),
    ("ADD r1, r2, [r3]", "must be a scalar register"),
    ("LOAD_S r1, [v2]", "memory base must be a scalar register"),
    ("x = 1 / 0\n.word x", "division by zero"),
    (".space undefined_later\nundefined_later = 4", "computable in pass 1"),
    ("NOP\n.org 0\nNOP", "already initialised"),
    ("ADD r1, r2, r3 ; ok\n  @", "unexpected character"),
    ("SHLI r1, r2, 32", "shift amount 32 out of range"),
    ("HALT 70000", "exit code 70000 out of range"),
    (".global missing", "never defined"),
    ("VREDUCE.SUM.U r1, v1", "applies only to VREDUCE.MAX"),
    ("12abc: NOP", "malformed number"),
)


def run_selftest(stream=sys.stdout) -> int:
    failures: list[str] = []
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(message)

    check_isa_tables()
    checks += 1

    for source, pc, expected in _GOLDEN:
        try:
            program = assemble(source, "<golden>", AsmOptions(text_base=pc))
            word = int.from_bytes(bytes(program.images["text"]._data[pc + k] for k in range(4)), "little")
            check(word == expected, f"golden '{source}' @0x{pc:X}: got 0x{word:08X}, expected 0x{expected:08X}")
        except (AsmError, AssemblyFailed) as exc:
            check(False, f"golden '{source}' failed: {exc}")

    try:
        program = assemble(_SELFTEST_PROGRAM, "<selftest>")
        check(not program.warnings, f"self-test program produced warnings: {[w.message for w in program.warnings]}")
        jobs = plan_images(program, "selftest", None, None, 0)
        words = list(jobs[0].words)
        check(load_roundtrip(words, jobs[0].base), "output formats disagree after parse-back")
        insn_rows = [r for r in program.listing if r.disasm is not None]
        mnemonics = {r.disasm.split()[0].split(".")[0] for r in insn_rows}
        missing = set(INSN_BY_MNEMONIC) - mnemonics
        check(not missing, f"self-test program does not cover {sorted(missing)}")
        values = program.symbol_values
        check(values["stack_top"] % 4 == 0 and values["result"] % 16 == 0, "data alignment not honoured")
        top_word = int.from_bytes(bytes(program.images["data"]._data[values["stack_top"] + k] for k in range(4)),
                                  "little")
        check(top_word == values["stack_top"], "'.' did not evaluate to the element address")
        check(values["mat_a"] == _align_up(program.sections["text"].high_water, 16), "auto data base incorrect")
    except (AsmError, AssemblyFailed) as exc:
        detail = "; ".join(e.message for e in exc.errors) if isinstance(exc, AssemblyFailed) else str(exc)
        check(False, f"self-test program failed: {detail}")

    for source, needle in _NEGATIVE_CASES:
        try:
            assemble(source, "<negative>")
            check(False, f"negative case was accepted: {source!r}")
        except AssemblyFailed as exc:
            text = " | ".join(e.message for e in exc.errors)
            check(needle in text, f"negative case {source!r}: expected '{needle}', got '{text}'")
        except AsmError as exc:
            check(needle in exc.message, f"negative case {source!r}: expected '{needle}', got '{exc.message}'")

    rng = random.Random(0x5F_A5)
    decoded_valid = 0
    for _ in range(20000):
        word = rng.getrandbits(32)
        if rng.random() < 0.85:
            word = (rng.choice([int(o) for o in Opcode]) << 26) | (word & ((1 << 26) - 1))
            if rng.random() < 0.5:
                word &= ~0x3FC0 if rng.random() < 0.5 else ~0x3F
        pc = rng.randrange(0, 1 << 20) * 4
        dec = decode(word, pc)
        if not dec.valid:
            continue
        decoded_valid += 1
        try:
            again = assemble_canonical(dec.text, pc)
        except AsmError as exc:
            check(False, f"fuzz: '{dec.text}' (0x{word:08X}) does not re-assemble: {exc.message}")
            continue
        check(again == word, f"fuzz: '{dec.text}' re-encodes to 0x{again:08X}, expected 0x{word:08X}")
    check(decoded_valid > 2000, f"fuzz exercised only {decoded_valid} valid encodings")

    for message in failures[:50]:
        print(f"FAIL: {message}", file=stream)
    status = "PASSED" if not failures else f"FAILED ({len(failures)} of {checks})"
    print(f"{TOOL} self-test {status}: {checks} checks, {decoded_valid} fuzzed encodings round-tripped",
          file=stream)
    return 0 if not failures else 1


def load_roundtrip(words: Sequence[int], base: int) -> bool:
    expected = list(words)
    parsed = [
        parse_hex_image(cast(str, render_hex(words, base, "t"))),
        parse_bin_image(cast(bytes, render_bin(words, base, "t"))),
        parse_mif_image(cast(str, render_mif(words, base, "t"))),
        parse_coe_image(cast(str, render_coe(words, base, "t"))),
    ]
    return all(p == expected for p in parsed)


# =============================================================================
# Command line
# =============================================================================

def _int_arg(text: str) -> int:
    try:
        return int(text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer '{text}'") from None


def _parse_defines(items: Sequence[str]) -> dict[str, int]:
    defines: dict[str, int] = {}
    for item in items:
        name, _, value = item.partition("=")
        try:
            defines[name.strip()] = int(value, 0) if value else 1
        except ValueError:
            raise AsmError(f"invalid -D value in '{item}' (expected NAME=INTEGER)") from None
    return defines


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sfx_asm.py",
        description="SilicaFlux multi-format assembler (.hex / .bin / .mif / .coe).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  sfx_asm.py kernel.sfa                    # kernel.hex .bin .mif .coe\n"
               "  sfx_asm.py kernel.sfa -o build/imem -f hex,mif --depth 4096 -l -s\n"
               "  sfx_asm.py kernel.sfa --split-sections   # kernel.text.* and kernel.data.*\n"
               "  sfx_asm.py --disassemble build/imem.hex\n"
               "  sfx_asm.py --emit-pkg silicaflux_isa_pkg.sf\n"
               "  sfx_asm.py --isa-table | --selftest")
    parser.add_argument("input", nargs="?", help="assembly source ('-' reads stdin)")
    parser.add_argument("-o", "--output", metavar="BASE", help="output path without extension "
                        "(default: input path without extension)")
    parser.add_argument("-f", "--formats", default="hex,bin,mif,coe",
                        help="comma-separated subset of hex,bin,mif,coe (default: all)")
    parser.add_argument("--base", type=_int_arg, metavar="ADDR",
                        help="byte address of word 0 in the images (default: section base)")
    parser.add_argument("--depth", type=_int_arg, metavar="WORDS",
                        help="pad each image to WORDS words; fail if the program is larger")
    parser.add_argument("--fill", type=_int_arg, default=0, metavar="WORD",
                        help="value of uninitialised words (default 0x00000000 = ILLEGAL trap)")
    parser.add_argument("--text-base", type=_int_arg, default=0, metavar="ADDR", help=".text base (default 0)")
    parser.add_argument("--data-base", type=_int_arg, metavar="ADDR",
                        help=".data base (default: after .text, 16-byte aligned; 0 with --split-sections)")
    parser.add_argument("--split-sections", action="store_true",
                        help="emit separate .text and .data images (Harvard memories)")
    parser.add_argument("-D", "--define", action="append", default=[], metavar="NAME[=VALUE]",
                        help="predefine an absolute symbol")
    parser.add_argument("-I", "--include-dir", action="append", default=[], metavar="DIR",
                        help="additional .include search directory")
    parser.add_argument("-l", "--listing", action="store_true", help="write BASE.lst")
    parser.add_argument("-s", "--symbols", action="store_true", help="write BASE.sym")
    parser.add_argument("--no-verify", action="store_true", help="skip per-word decode/re-encode verification")
    parser.add_argument("--werror", action="store_true", help="treat warnings as errors")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress the summary line")
    parser.add_argument("--emit-pkg", metavar="FILE", help="write the ISA as a SystemVerilog package")
    parser.add_argument("--isa-table", action="store_true", help="print the opcode map and exit")
    parser.add_argument("--disassemble", metavar="IMAGE", help="disassemble a .hex/.bin/.mif/.coe image")
    parser.add_argument("--selftest", action="store_true", help="run the built-in verification suite")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _report(diags: Iterable[AsmError], severity: str) -> None:
    for diag in diags:
        print(diag.render(severity), file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        check_isa_tables()
    except RuntimeError as exc:
        print(f"{TOOL}: internal error: ISA tables inconsistent: {exc}", file=sys.stderr)
        return 3
    if args.selftest:
        return run_selftest()

    standalone = False
    try:
        if args.isa_table:
            sys.stdout.write(render_isa_table())
            standalone = True
        if args.emit_pkg:
            write_output(args.emit_pkg, render_sv_package())
            if not args.quiet:
                print(f"{TOOL}: wrote {args.emit_pkg}", file=sys.stderr)
            standalone = True
        if args.disassemble:
            words = load_image(args.disassemble)
            sys.stdout.write(disassemble_words(words, args.base or 0))
            standalone = True
    except AsmError as exc:
        _report([exc], "error")
        return 1
    except OSError as exc:
        print(f"{TOOL}: error: {exc}", file=sys.stderr)
        return 2
    if args.input is None:
        if standalone:
            return 0
        parser.error("no input file (or use --isa-table, --emit-pkg, --disassemble, --selftest)")

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    unknown = [f for f in formats if f not in FORMAT_RENDERERS]
    if unknown or not formats:
        parser.error(f"unknown output format(s): {', '.join(unknown) or '(none)'}; choose from hex,bin,mif,coe")
    if args.split_sections and args.base is not None:
        parser.error("--base cannot be combined with --split-sections (each image starts at its section base)")
    if args.depth is not None and args.depth <= 0:
        parser.error("--depth must be positive")

    source_name = "<stdin>" if args.input == "-" else args.input
    out_base = args.output or (os.path.splitext(args.input)[0] if args.input != "-" else "out")
    try:
        options = AsmOptions(text_base=args.text_base, data_base=args.data_base,
                             include_dirs=tuple(args.include_dir), defines=_parse_defines(args.define),
                             verify=not args.no_verify, split_sections=args.split_sections)
        text = read_source(args.input)
        program = Assembler(options).assemble_source(text, source_name)
    except AssemblyFailed as failed:
        _report(failed.warnings, "warning")
        _report(failed.errors, "error")
        print(f"{TOOL}: {len(failed.errors)} error(s), {len(failed.warnings)} warning(s)", file=sys.stderr)
        return 1
    except AsmError as exc:
        _report([exc], "error")
        return 1

    _report(program.warnings, "warning")
    if args.werror and program.warnings:
        print(f"{TOOL}: {len(program.warnings)} warning(s) treated as errors", file=sys.stderr)
        return 1

    try:
        jobs = plan_images(program, out_base, args.base, args.depth, args.fill)
        written: list[str] = []
        for job in jobs:
            for fmt in formats:
                path = f"{job.path_base}.{fmt}"
                write_output(path, FORMAT_RENDERERS[fmt](job.words, job.base, job.title))
                written.append(path)
        if args.listing:
            write_output(f"{out_base}.lst", render_listing(program))
            written.append(f"{out_base}.lst")
        if args.symbols:
            write_output(f"{out_base}.sym", render_symbols(program))
            written.append(f"{out_base}.sym")
    except AsmError as exc:
        _report([exc], "error")
        return 1
    except OSError as exc:
        print(f"{TOOL}: error: cannot write output: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        text_bytes = program.images["text"].size
        data_bytes = program.images["data"].size
        words = sum(len(job.words) for job in jobs)
        print(f"{TOOL}: {source_name}: {words} word(s) [.text {text_bytes} B, .data {data_bytes} B], "
              f"{len(program.symbols)} symbol(s), {len(program.warnings)} warning(s) -> {', '.join(written)}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
