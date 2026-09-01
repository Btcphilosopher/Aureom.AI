"""
Bitcoin block-header serialization, target expansion, and proof-of-work
comparison -- the Bitcoin-specific layer built on top of sha256_model.py.

Byte-order is the single most bug-prone part of any Bitcoin hashing
implementation (see section 41 of the project brief: "Document all
byte-order conversions explicitly"), so every conversion here is called
out in a comment at the point it happens. Summary:

  * Every header FIELD (version, timestamp, nBits, nonce) is a little-
    endian integer on the wire. prev_block_hash and merkle_root are
    32-byte digests already in "internal" (little-endian-as-integer)
    byte order -- i.e. exactly as produced by double_sha256() below,
    NOT the byte-reversed form block explorers print.
  * The 80-byte header is hashed as a plain byte string (SHA-256 does
    not know about field endianness -- see sha256_model.py docstring).
  * The resulting 32-byte digest is compared to `target` by re-reading
    the digest bytes as a LITTLE-ENDIAN integer (hash_int <= target).
  * `to_display_hex()` byte-reverses a digest to produce the familiar
    leading-zeros hex string used by block explorers / bitcoind RPC.
    That reversed string is for human display ONLY -- never fed back
    into hashing or comparison logic.
"""
from __future__ import annotations

from dataclasses import dataclass

from .sha256_model import double_sha256, midstate, sha256, words_to_bytes

HEADER_LEN = 80          # bytes
FIRST_BLOCK_LEN = 64     # bytes: version(4)+prev_hash(32)+merkle_root[0:28](28)
SECOND_BLOCK_TAIL_LEN = 16  # bytes: merkle_root[28:32](4)+time(4)+bits(4)+nonce(4)


@dataclass(frozen=True)
class BlockHeader:
    version: int
    prev_block: bytes   # 32 bytes, internal byte order (NOT display order)
    merkle_root: bytes  # 32 bytes, internal byte order (NOT display order)
    timestamp: int
    bits: int
    nonce: int

    def __post_init__(self):
        if len(self.prev_block) != 32:
            raise ValueError("prev_block must be exactly 32 bytes")
        if len(self.merkle_root) != 32:
            raise ValueError("merkle_root must be exactly 32 bytes")
        for name, val in (("version", self.version), ("timestamp", self.timestamp),
                           ("bits", self.bits), ("nonce", self.nonce)):
            if not (0 <= val <= 0xFFFFFFFF):
                raise ValueError(f"{name} must fit in 32 bits, got {val}")

    def serialize(self) -> bytes:
        """80-byte wire serialization. Every scalar field is little-endian."""
        return (
            self.version.to_bytes(4, "little")
            + self.prev_block
            + self.merkle_root
            + self.timestamp.to_bytes(4, "little")
            + self.bits.to_bytes(4, "little")
            + self.nonce.to_bytes(4, "little")
        )

    @staticmethod
    def parse(data: bytes) -> "BlockHeader":
        if len(data) != HEADER_LEN:
            raise ValueError(f"header must be exactly {HEADER_LEN} bytes, got {len(data)}")
        return BlockHeader(
            version=int.from_bytes(data[0:4], "little"),
            prev_block=data[4:36],
            merkle_root=data[36:68],
            timestamp=int.from_bytes(data[68:72], "little"),
            bits=int.from_bytes(data[72:76], "little"),
            nonce=int.from_bytes(data[76:80], "little"),
        )

    def with_nonce(self, nonce: int) -> "BlockHeader":
        return BlockHeader(self.version, self.prev_block, self.merkle_root,
                            self.timestamp, self.bits, nonce)

    def first_block(self) -> bytes:
        """The constant-per-job 64-byte block used to compute the midstate."""
        return self.serialize()[:FIRST_BLOCK_LEN]

    def second_block_tail(self) -> bytes:
        """The 16 bytes of real header data in the second 64-byte block
        (before SHA-256 padding is appended by the RTL/model)."""
        return self.serialize()[FIRST_BLOCK_LEN:HEADER_LEN]

    def midstate_words(self):
        """8-word SHA-256 state after compressing only first_block() from IV."""
        return midstate(self.first_block())

    def single_hash(self) -> bytes:
        """SHA256(header) -- the *first* pass only, internal byte order."""
        return sha256(self.serialize())

    def pow_hash(self) -> bytes:
        """SHA256(SHA256(header)) -- Bitcoin's actual proof-of-work hash,
        internal (little-endian-as-integer) byte order."""
        return double_sha256(self.serialize())


def bits_to_target(bits: int) -> int:
    """Expand Bitcoin's 32-bit compact ("nBits") representation to a full
    256-bit target integer.

    Encoding: bits = (exponent:8)(mantissa:24), big-endian within the
    32-bit word conceptually -- i.e. exponent = bits[31:24], mantissa =
    bits[23:0]. target = mantissa * 256**(exponent - 3).
    Bit 23 of the mantissa (0x00800000) is a sign flag; Bitcoin consensus
    rules always treat a set sign bit as producing target 0 (unconditional
    PoW failure) rather than a negative number, and we mirror that here.
    """
    if not (0 <= bits <= 0xFFFFFFFF):
        raise ValueError("bits must fit in 32 bits")
    exponent = (bits >> 24) & 0xFF
    mantissa = bits & 0x007FFFFF
    is_negative = bool(bits & 0x00800000)
    if is_negative or mantissa == 0:
        return 0
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    return target


def target_to_bits(target: int) -> int:
    """Inverse of bits_to_target(): compact-encode a target integer.
    Provided for test-vector generation / sanity round-tripping."""
    if target <= 0:
        return 0
    nbytes = (target.bit_length() + 7) // 8
    if nbytes <= 3:
        mantissa = target << (8 * (3 - nbytes))
    else:
        mantissa = target >> (8 * (nbytes - 3))
    if mantissa & 0x00800000:
        mantissa >>= 8
        nbytes += 1
    return (nbytes << 24) | (mantissa & 0x007FFFFF)


def target_meets(hash_bytes: bytes, target: int) -> bool:
    """Bitcoin's PoW check: the 32-byte digest, read as a LITTLE-ENDIAN
    256-bit integer, must be <= target. This is the opposite byte order
    from the big-endian word convention SHA-256 itself uses internally --
    see the module docstring."""
    if len(hash_bytes) != 32:
        raise ValueError("hash must be exactly 32 bytes")
    hash_int = int.from_bytes(hash_bytes, "little")
    return hash_int <= target


def to_display_hex(hash_bytes: bytes) -> str:
    """Byte-reversed hex string, matching block-explorer / bitcoind display
    convention. Display-only: never re-hash or compare this string."""
    return hash_bytes[::-1].hex()
