"""Bit-exact Python golden models of the MemoryFlow RTL.

Every function here mirrors a specific RTL block; the SystemVerilog
testbenches load vectors produced by :func:`write_vector_set` and compare
the hardware against them, so RTL and Python are checked against each other.

Mirrors
-------
* :func:`secded_encode` / :func:`secded_decode`  -> rtl/ecc/sf_ecc_secded_{enc,dec}.sv
* :func:`parity_pack`                           -> sf_sram_bank ECC_MODE=1
* :func:`bank_map`                              -> sf_spm_banked INTERLEAVE modes
* :func:`dma_copy`                              -> sf_dma 1-D / 2-D semantics
* :func:`tensor_tile` / :func:`pack_tensor_*`   -> sf_tensor_array
* :func:`vec_op`                                -> sf_vec_unit
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# --------------------------------------------------------------------- SECDED


def secded_r(k: int) -> int:
    """Hamming check bits for k data bits: smallest r with 2**r >= k + r + 1."""
    if k < 1:
        raise ValueError("k must be >= 1")
    r = 1
    while (1 << r) < k + r + 1:
        r += 1
    return r


def secded_n(k: int) -> int:
    """Total stored codeword width (data + Hamming check + overall parity)."""
    return k + secded_r(k) + 1


def secded_dpos(j: int) -> int:
    """Hamming position of data bit j (j-th integer >= 3 that is not a power of 2)."""
    n = 0
    p = 3
    while True:
        if p & (p - 1):
            if n == j:
                return p
            n += 1
        p += 1


def _parity(x: int) -> int:
    return bin(x).count("1") & 1


def secded_encode(data: int, k: int) -> int:
    """Encode k-bit ``data`` -> codeword ``{overall, check[r-1:0], data[k-1:0]}``."""
    if data < 0 or data >> k:
        raise ValueError("data out of range for k bits")
    r = secded_r(k)
    chk = 0
    for i in range(r):
        bit = 0
        for j in range(k):
            if (secded_dpos(j) >> i) & 1 and (data >> j) & 1:
                bit ^= 1
        chk |= bit << i
    overall = _parity(data) ^ _parity(chk)
    return (overall << (k + r)) | (chk << k) | data


@dataclass(frozen=True)
class SecdedResult:
    data: int
    corrected: bool
    uncorrectable: bool
    syndrome: int


def secded_decode(code: int, k: int) -> SecdedResult:
    """Decode a codeword exactly as sf_ecc_secded_dec does."""
    r = secded_r(k)
    n = k + r + 1
    if code < 0 or code >> n:
        raise ValueError("codeword out of range")
    d = code & ((1 << k) - 1)
    c_rx = (code >> k) & ((1 << r) - 1)
    p_all = _parity(code)
    c_re = 0
    for i in range(r):
        bit = 0
        for j in range(k):
            if (secded_dpos(j) >> i) & 1 and (d >> j) & 1:
                bit ^= 1
        c_re |= bit << i
    syn = c_re ^ c_rx
    max_pos = k + r
    in_rng = syn <= max_pos
    single = bool(p_all) and (syn == 0 or in_rng)
    out = d
    if single and syn:
        for j in range(k):
            if secded_dpos(j) == syn:
                out ^= 1 << j
                break
    uncorr = (not p_all and syn != 0) or (bool(p_all) and syn != 0 and not in_rng)
    return SecdedResult(out, single, uncorr, syn)


def parity_pack(data: int, nbytes: int) -> int:
    """ECC_MODE=1 stored word: per byte {parity, byte} in 9-bit lanes."""
    w = 0
    for b in range(nbytes):
        byte = (data >> (8 * b)) & 0xFF
        w |= (byte | (_parity(byte) << 8)) << (9 * b)
    return w


# --------------------------------------------------------------------- banking

INTERLEAVE_MODULO = 0
INTERLEAVE_XOR = 1
INTERLEAVE_BLOCK = 2


def bank_map(word: int, nbanks: int, bank_depth: int, mode: int) -> tuple[int, int]:
    """Word address -> (bank, index) exactly as sf_spm_banked decodes it."""
    if nbanks & (nbanks - 1) or bank_depth & (bank_depth - 1):
        raise ValueError("nbanks and bank_depth must be powers of two")
    bkw = max(nbanks.bit_length() - 1, 0)
    idxw = max(bank_depth.bit_length() - 1, 0)
    bmask = nbanks - 1
    imask = bank_depth - 1
    if nbanks == 1:
        return 0, word & imask
    if mode == INTERLEAVE_BLOCK:
        return (word >> idxw) & bmask, word & imask
    if mode == INTERLEAVE_XOR:
        return (word & bmask) ^ ((word >> bkw) & bmask), (word >> bkw) & imask
    return word & bmask, (word >> bkw) & imask


# --------------------------------------------------------------------- DMA

DMA_E_ZERO, DMA_E_ALIGN, DMA_E_OVF, DMA_E_RD, DMA_E_WR, DMA_E_ABORT = 1, 2, 3, 4, 5, 6


def dma_validate(src: int, dst: int, length: int, rows: int, sstride: int,
                 dstride: int, mode_2d: bool, src_stream: bool = False,
                 dst_stream: bool = False, beat_bytes: int = 8, aw: int = 32) -> int:
    """Start-time validation code (0 = OK) identical to sf_dma."""
    nrows = rows if (mode_2d and rows) else 1
    if length == 0:
        return DMA_E_ZERO
    m = beat_bytes - 1
    if (not src_stream and (src & m or (mode_2d and sstride & m))) or \
       (not dst_stream and (dst & m or (mode_2d and dstride & m))):
        return DMA_E_ALIGN
    s_end = src + (nrows - 1) * (sstride if mode_2d else 0) + length - 1
    d_end = dst + (nrows - 1) * (dstride if mode_2d else 0) + length - 1
    if (not src_stream and s_end >> aw) or (not dst_stream and d_end >> aw):
        return DMA_E_OVF
    return 0


def dma_copy(mem: bytearray, src: int, dst: int, length: int, rows: int = 1,
             sstride: int = 0, dstride: int = 0) -> None:
    """Reference 1-D/2-D byte copy (row-major, non-overlapping)."""
    for r in range(max(rows, 1)):
        s = src + r * sstride
        d = dst + r * dstride
        mem[d:d + length] = mem[s:s + length]


# --------------------------------------------------------------------- vector unit


def _wrap(x: int, bits: int) -> int:
    x &= (1 << bits) - 1
    return x - (1 << bits) if x >> (bits - 1) else x


def lanes_unpack(word: int, ew: int, lanes: int) -> list[int]:
    return [_wrap((word >> (ew * i)) & ((1 << ew) - 1), ew) for i in range(lanes)]


def lanes_pack(vals: Sequence[int], ew: int) -> int:
    w = 0
    for i, v in enumerate(vals):
        w |= (v & ((1 << ew) - 1)) << (ew * i)
    return w


def vec_op(op: int, a: Sequence[int], b: Sequence[int], alpha: int = 1, ew: int = 16) -> list[int] | int:
    """Golden model of sf_vec_unit over flat element lists.

    op 0 ADD, 1 MUL, 3 AXPY -> list of wrapped results; op 2 DOT -> int (64-bit wrap).
    """
    if len(a) != len(b):
        raise ValueError("operand length mismatch")
    if op == 2:
        return _wrap(sum(x * y for x, y in zip(a, b)), 64)
    out = []
    for x, y in zip(a, b):
        if op == 0:
            out.append(_wrap(x + y, ew))
        elif op == 1:
            out.append(_wrap(x * y, ew))
        elif op == 3:
            out.append(_wrap(_wrap(alpha * x, ew) + y, ew))
        else:
            raise ValueError("bad op")
    return out


# --------------------------------------------------------------------- tensor array


def tensor_tile(a: Sequence[Sequence[int]], b: Sequence[Sequence[int]], accw: int = 32) -> list[list[int]]:
    """C = A @ B with int8 inputs and ACCW-bit wrapping accumulators."""
    tr, k = len(a), len(a[0])
    kb, tc = len(b), len(b[0])
    if k != kb:
        raise ValueError("inner dimension mismatch")
    c = [[0] * tc for _ in range(tr)]
    for i in range(tr):
        for j in range(tc):
            c[i][j] = _wrap(sum(a[i][kk] * b[kk][j] for kk in range(k)), accw)
    return c


def pack_tensor_a(a: Sequence[Sequence[int]], iw: int = 8) -> list[int]:
    """A operand beats: beat k = column A[:, k] (row i in lane i)."""
    tr, k = len(a), len(a[0])
    return [lanes_pack([a[i][kk] for i in range(tr)], iw) for kk in range(k)]


def pack_tensor_b(b: Sequence[Sequence[int]], iw: int = 8) -> list[int]:
    """B operand beats: beat k = row B[k, :]."""
    return [lanes_pack(row, iw) for row in b]


def pack_tensor_c(c: Sequence[Sequence[int]], accw: int = 32, dw: int = 64) -> list[int]:
    """Drain order of sf_tensor_array: row-major, DW/ACCW accumulators per beat."""
    flat = [v for row in c for v in row]
    epb = dw // accw
    return [lanes_pack(flat[i:i + epb], accw) for i in range(0, len(flat), epb)]


# --------------------------------------------------------------------- vector files


def write_hex(path: Path, words: Iterable[int], width_bits: int) -> int:
    digits = (width_bits + 3) // 4
    n = 0
    with open(path, "w") as f:
        for w in words:
            f.write(f"{w:0{digits}x}\n")
            n += 1
    return n


def write_vector_set(outdir: Path | str, seed: int = 2026) -> dict[str, int]:
    """Generate every golden-vector file used by the SV testbenches."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    counts: dict[str, int] = {}

    # ECC encoder/decoder vectors (corner cases + random)
    for k in (32, 64):
        data = [0, (1 << k) - 1, 0x5555555555555555 & ((1 << k) - 1),
                0xAAAAAAAAAAAAAAAA & ((1 << k) - 1), 1, 1 << (k - 1)]
        data += [rng.getrandbits(k) for _ in range(250)]
        counts[f"ecc_k{k}_data.hex"] = write_hex(out / f"ecc_k{k}_data.hex", data, k)
        write_hex(out / f"ecc_k{k}_code.hex", (secded_encode(d, k) for d in data), secded_n(k))

    # tensor tiles: three K values, 8x8 array
    for k in (1, 8, 37):
        a = [[rng.randint(-128, 127) for _ in range(k)] for _ in range(8)]
        b = [[rng.randint(-128, 127) for _ in range(8)] for _ in range(k)]
        c = tensor_tile(a, b)
        write_hex(out / f"ten_k{k}_a.hex", pack_tensor_a(a), 64)
        write_hex(out / f"ten_k{k}_b.hex", pack_tensor_b(b), 64)
        counts[f"ten_k{k}_c.hex"] = write_hex(out / f"ten_k{k}_c.hex", pack_tensor_c(c), 64)

    # system GEMM: C(16x8) = A(16x32) @ B(32x8); two 8-row tiles share B (reuse=2)
    m, n, k = 16, 8, 32
    a = [[rng.randint(-128, 127) for _ in range(k)] for _ in range(m)]
    b = [[rng.randint(-128, 127) for _ in range(n)] for _ in range(k)]
    c = tensor_tile(a, b)
    a_beats: list[int] = []
    for t in range(m // 8):
        a_beats += pack_tensor_a(a[8 * t: 8 * t + 8])
    c_beats: list[int] = []
    for t in range(m // 8):
        c_beats += pack_tensor_c(c[8 * t: 8 * t + 8])
    write_hex(out / "sys_gemm_a.hex", a_beats, 64)
    write_hex(out / "sys_gemm_b.hex", pack_tensor_b(b), 64)
    counts["sys_gemm_c.hex"] = write_hex(out / "sys_gemm_c.hex", c_beats, 64)

    # system vector ops: 256 int16 elements (64 beats)
    ne = 256
    va = [rng.randint(-32768, 32767) for _ in range(ne)]
    vb = [rng.randint(-32768, 32767) for _ in range(ne)]
    beats = lambda v: [lanes_pack(v[i:i + 4], 16) for i in range(0, len(v), 4)]  # noqa: E731
    write_hex(out / "sys_vec_a.hex", beats(va), 64)
    write_hex(out / "sys_vec_b.hex", beats(vb), 64)
    write_hex(out / "sys_vec_add.hex", beats(vec_op(0, va, vb)), 64)
    write_hex(out / "sys_vec_axpy3.hex", beats(vec_op(3, va, vb, alpha=3)), 64)
    dot = vec_op(2, va, vb)
    counts["sys_vec_dot.hex"] = write_hex(out / "sys_vec_dot.hex", [dot & ((1 << 64) - 1)], 64)
    return counts
