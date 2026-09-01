# SHA-256 / Bitcoin byte-order notes (section 41)

Byte-order mistakes are the single most common source of bugs in Bitcoin
hashing implementations. This document is the canonical reference; every
RTL module and Python function that touches byte order links back here
in a comment. **Nothing in this project silently truncates a hash,
changes endianness, omits a round, alters a constant, or alters
padding** — every one of those would be a correctness bug, not a style
choice, and section 41 treats them as non-negotiable.

## 1. SHA-256 word loading (internal to the hash function)

FIPS 180-4 loads each 512-bit message block as sixteen 32-bit words,
**big-endian**: the first byte of the block is the most-significant byte
of `W[0]`. This is true regardless of what the bytes being hashed
*mean* — SHA-256 hashes a byte string, full stop. Every RTL module in
`rtl/sha256/` uses this convention for every packed word/block port:
`block_bits[511:480]` is `W[0]`, and so on. Python's
`sha256_model.block_to_words()` does the same via
`int.from_bytes(block[i:i+4], "big")`.

The final digest is emitted the same way: eight 32-bit words,
big-endian, concatenated `H0..H7`. This is what every generic SHA-256
test vector (NIST, hashlib, OpenSSL, ...) assumes, and it's what
`sha256_model.sha256()` returns.

## 2. Bitcoin header field serialization (numeric fields are LE)

The 80-byte Bitcoin block header packs `version`, `timestamp`, `nBits`,
and `nonce` as **little-endian** 32-bit integers on the wire.
`prev_block_hash` and `merkle_root` are 32-byte digests already in
"internal" byte order (see §3) — not the byte-reversed form block
explorers print.

`python/silicaflux_bitcoin/reference/block_header.py:BlockHeader.
serialize()` builds the wire bytes field-by-field with the correct
per-field endianness. Those wire bytes are then hashed as a plain byte
string per §1 — no further conversion.

## 3. "Internal" vs "display" hash byte order

`double_sha256(header_bytes)` returns the digest exactly as produced by
two SHA-256 passes (§1's big-endian word convention, output
concatenated in order) — this **is** the internal byte order Bitcoin
uses everywhere in the protocol and in its own source (`uint256`
storage). It is *not* what a block explorer shows you. The familiar
leading-zeros hex string is that same digest with its 32 bytes fully
reversed, for human display only:
`to_display_hex(h) = h[::-1].hex()`. Never reverse a digest before
hashing it again or before comparing it to a target — only for display.

## 4. The proof-of-work comparison is LITTLE-endian

Bitcoin's actual PoW rule: read the 32-byte digest (internal order, §3)
as a **little-endian** 256-bit integer (byte 0 = least significant) and
require `hash_int <= target`. This is the *opposite* convention from
§1's big-endian word loading *inside* the hash function — two different,
unrelated byte-order rules that both apply to the same design, at
different points. `block_header.target_meets()` implements this
exactly; `rtl/target/target_compare.sv` implements the RTL equivalent
via an explicit 32-byte (not 32-bit-word) reversal, documented in that
file's header comment.

`target` itself (from `bits_to_target()` / `nbits_expand.sv`) is a
**plain magnitude**, not a byte string — there is no byte-order question
for it at all, only for the hash it's compared against.

## 5. The nonce field: a real bug this project's own tests caught

Every other value that crosses into the hashing datapath in this design
(`header_block1`, `header_tail3`, the re-hashed first-pass digest, ...)
arrives **already** in wire byte order because it was built by slicing
a real serialized byte string (in Python: `header.serialize()[...]`; in
a real system: however the host packs the header). `hash_core.sv`'s
nonce is different: it's a plain **arithmetic counter**
(`nonce_r`), built by addition, not by parsing bytes — so its bit
pattern is a normal MSB-first integer, not wire-byte-ordered data.

Feeding that counter directly into the hashing datapath (as an early
version of `hash_core.sv` did) silently searches the *wrong* nonce
sequence: correct answers for header X exist, just not at the nonce
values you think you're trying. `tb/integration/tb_hash_core.sv`,
checking real per-nonce results against the Python golden model, caught
this immediately (RTL found a *different*, earlier nonce than expected
with a completely different resulting hash). The fix is one explicit
byte-swap before the nonce enters the hashing datapath — see
`hash_core.sv`'s `nonce_wire_word` and its long comment. This is kept
here as the canonical example of exactly the class of bug §1–§4 exist to
prevent, and why every byte-order boundary in this project is
independently vector-tested against the Python model rather than
"obviously correct by inspection."

## 6. Constants and rounds (no alterations, ever)

`sha256_pkg.sv`'s `H0_0..H0_7` and `k_const()` are cross-checked
programmatically against `sha256_model.H0`/`K` (byte-for-byte, all 64+8
values) during bring-up — see the session's verification notes; this is
not "we typed the same constants twice and hoped." All 64 rounds run
unconditionally every compression (`sha256_compressor.sv`'s round
counter and `sha256_pipeline.sv`'s generate-unrolled 64 `sha256_round`
instances both cover exactly rounds 0..63, verified round-by-round
against `sha256_model.compress_block`'s `RoundTrace` in
`tb/unit/tb_sha256_round.sv`). Padding (`pad_message()` /
`sha256_double_hash.sv`'s hardwired tail words) is derived once from
FIPS 180-4 §5.1.1 and reused everywhere a message length is fixed (an
80-byte header, a 32-byte digest) — see §13 notes in
`sha256_double_hash.sv`'s header comment for the exact word-by-word
derivation.
