"""
Independent, from-scratch SHA-256 reference implementation (FIPS 180-4).

This module is the *golden model* used to verify the SystemVerilog RTL
datapath (rtl/sha256/*.sv). Per the project verification policy, the RTL
DUT and this Python model are independently authored implementations of
the same published specification -- they must never share implementation
logic. This file does NOT call hashlib for the actual compression -- the
compression function, message schedule, and padding are all written out
by hand from FIPS 180-4. hashlib is used only in tests/vectors as a
*third-party* cross-check of this model (see python/silicaflux_bitcoin/
vectors/generate_vectors.py), never as the model itself.

Byte-order policy (see docs/sha256_spec_notes.md for the full writeup):
  - SHA-256 itself is defined over a bit string. Following FIPS 180-4's
    own convention, we load each 512-bit block as sixteen 32-bit words
    in BIG-ENDIAN byte order (the first byte of the block is the most
    significant byte of W[0]), and we emit the final digest as eight
    32-bit words, again in BIG-ENDIAN byte order, concatenated H0..H7.
    This is what every standard SHA-256 test vector (NIST, hashlib,
    OpenSSL, ...) assumes, and it is what `sha256()` below returns.
  - Bitcoin's block header fields are serialized LITTLE-ENDIAN on the
    wire (see block_header.py). The 80-byte header byte string is fed
    to SHA-256 exactly as those wire bytes appear -- SHA-256 does not
    know or care about the *numeric* endianness of the fields it is
    hashing, it just hashes a byte string.
  - Bitcoin's proof-of-work target comparison then treats the resulting
    32-byte digest as a 256-bit integer in LITTLE-ENDIAN byte order
    (byte 0 of the digest is the least-significant byte of the integer).
    This is the opposite convention from the big-endian word-loading
    used *inside* SHA-256 above, and is a well-known source of bugs.
    See target_meets() in block_header.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

MASK32 = 0xFFFFFFFF

# Initial hash value H(0): first 32 bits of the fractional parts of the
# square roots of the first 8 primes (2 .. 19). FIPS 180-4 section 5.3.3.
H0: Tuple[int, ...] = (
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
)

# Round constants K(0..63): first 32 bits of the fractional parts of the
# cube roots of the first 64 primes (2 .. 311). FIPS 180-4 section 4.2.2.
K: Tuple[int, ...] = (
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5,
    0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5,
    0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3,
    0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174,
    0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC,
    0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7,
    0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967,
    0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13,
    0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85,
    0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3,
    0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5,
    0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3,
    0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208,
    0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
)


def _rotr(x: int, n: int) -> int:
    """32-bit rotate-right, matches the RTL's {x[n-1:0], x[31:n]} form."""
    x &= MASK32
    n &= 31
    return ((x >> n) | (x << (32 - n))) & MASK32


def _shr(x: int, n: int) -> int:
    return (x & MASK32) >> n


# ---------------------------------------------------------------------
# The six SHA-256 logical functions (FIPS 180-4 section 4.1.2), exactly
# mirrored 1:1 by rtl/sha256/sha256_ch.sv, sha256_maj.sv, sha256_sigma.sv.
# ---------------------------------------------------------------------
def ch(x: int, y: int, z: int) -> int:
    return ((x & y) ^ (~x & z)) & MASK32


def maj(x: int, y: int, z: int) -> int:
    return ((x & y) ^ (x & z) ^ (y & z)) & MASK32


def big_sigma0(x: int) -> int:
    return (_rotr(x, 2) ^ _rotr(x, 13) ^ _rotr(x, 22)) & MASK32


def big_sigma1(x: int) -> int:
    return (_rotr(x, 6) ^ _rotr(x, 11) ^ _rotr(x, 25)) & MASK32


def small_sigma0(x: int) -> int:
    return (_rotr(x, 7) ^ _rotr(x, 18) ^ _shr(x, 3)) & MASK32


def small_sigma1(x: int) -> int:
    return (_rotr(x, 17) ^ _rotr(x, 19) ^ _shr(x, 10)) & MASK32


def pad_message(msg: bytes) -> bytes:
    """FIPS 180-4 section 5.1.1 padding: append 0x80, zero-pad, append the
    64-bit big-endian bit length, so the result is a multiple of 64 bytes.
    """
    bit_len = len(msg) * 8
    padded = msg + b"\x80"
    pad_zeros = (56 - len(padded) % 64) % 64
    padded += b"\x00" * pad_zeros
    padded += bit_len.to_bytes(8, "big")
    assert len(padded) % 64 == 0
    return padded


def block_to_words(block: bytes) -> List[int]:
    """Split a 64-byte block into sixteen big-endian 32-bit words."""
    assert len(block) == 64
    return [int.from_bytes(block[i:i + 4], "big") for i in range(0, 64, 4)]


def message_schedule(block: bytes) -> List[int]:
    """Compute W[0..63] for one 512-bit block (FIPS 180-4 section 6.2.2 step 1)."""
    w = block_to_words(block)
    for t in range(16, 64):
        w.append(
            (small_sigma1(w[t - 2]) + w[t - 7] + small_sigma0(w[t - 15]) + w[t - 16])
            & MASK32
        )
    return w


@dataclass(frozen=True)
class RoundTrace:
    """One round's {a..h} state, for RTL round-by-round cross-checking."""
    t: int
    a: int
    b: int
    c: int
    d: int
    e: int
    f: int
    g: int
    h: int
    t1: int
    t2: int
    w_t: int
    k_t: int


def compress_block(state: Sequence[int], block: bytes, trace: List[RoundTrace] | None = None) -> Tuple[int, ...]:
    """One SHA-256 compression over a single 64-byte block, starting from
    `state` (8 words). Returns the updated 8-word state. If `trace` is
    given, appends a RoundTrace per round for RTL-vs-Python round-level
    debugging (see tb/unit/tb_sha256_round.sv vector generation).
    """
    w = message_schedule(block)
    a, b, c, d, e, f, g, h = state

    for t in range(64):
        t1 = (h + big_sigma1(e) + ch(e, f, g) + K[t] + w[t]) & MASK32
        t2 = (big_sigma0(a) + maj(a, b, c)) & MASK32
        if trace is not None:
            trace.append(RoundTrace(t, a, b, c, d, e, f, g, h, t1, t2, w[t], K[t]))
        h = g
        g = f
        f = e
        e = (d + t1) & MASK32
        d = c
        c = b
        b = a
        a = (t1 + t2) & MASK32

    return (
        (state[0] + a) & MASK32,
        (state[1] + b) & MASK32,
        (state[2] + c) & MASK32,
        (state[3] + d) & MASK32,
        (state[4] + e) & MASK32,
        (state[5] + f) & MASK32,
        (state[6] + g) & MASK32,
        (state[7] + h) & MASK32,
    )


def sha256_words(msg: bytes) -> Tuple[int, ...]:
    """Full SHA-256 over an arbitrary-length message, returned as 8 words."""
    padded = pad_message(msg)
    state = H0
    for off in range(0, len(padded), 64):
        state = compress_block(state, padded[off:off + 64])
    return state


def words_to_bytes(words: Sequence[int]) -> bytes:
    return b"".join(w.to_bytes(4, "big") for w in words)


def sha256(msg: bytes) -> bytes:
    """Full SHA-256, standard big-endian digest bytes (matches hashlib.sha256(msg).digest())."""
    return words_to_bytes(sha256_words(msg))


def double_sha256(msg: bytes) -> bytes:
    """Bitcoin's hashing primitive: SHA256(SHA256(msg))."""
    return sha256(sha256(msg))


def midstate(first_block: bytes) -> Tuple[int, ...]:
    """Compress exactly one 64-byte block from the fixed IV (H0).

    For an 80-byte Bitcoin header this is compress(H0, header[0:64]):
    the version + prev_block_hash + first 28 bytes of merkle_root. That
    prefix is constant for an entire mining round (only nonce, and
    occasionally ntime/merkle_root-tail via extranonce rolling, change),
    so the midstate can be computed once per job and re-used across every
    nonce trial -- see rtl/top/hash_core.sv `midstate_load`/`midstate_valid`.
    """
    if len(first_block) != 64:
        raise ValueError("midstate() takes exactly one 64-byte block")
    return compress_block(H0, first_block)
