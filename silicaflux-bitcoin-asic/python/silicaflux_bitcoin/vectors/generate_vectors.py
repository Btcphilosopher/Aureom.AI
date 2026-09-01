"""
python -m silicaflux_bitcoin.vectors [--out-dir tb/vectors] [--seed 1234]

Generates every test-vector file consumed by the SystemVerilog
testbenches under tb/, using ONLY the Python golden model
(silicaflux_bitcoin.reference) as the source of expected values. This is
the "test vector generator" stage of the verification pipeline in
section 36 of the project brief:

    Python reference -> test vector generator -> SV simulation -> RTL
    output -> Python comparison -> PASS/FAIL

Vectors are written as plain hex-per-line files loadable with SystemVerilog
`$readmemh`, one file per field (not interleaved), so each testbench just
does `$readmemh("path", mem_array)`.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Iterable, Sequence

from silicaflux_bitcoin.reference import sha256_model as m
from silicaflux_bitcoin.reference import block_header as bh

MASK32 = 0xFFFFFFFF


def _w32(path: Path, values: Iterable[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for v in values:
            f.write(f"{v & MASK32:08x}\n")


def _w_bits(path: Path, values: Iterable[int], nbits: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    digits = (nbits + 3) // 4
    mask = (1 << nbits) - 1
    with open(path, "w") as f:
        for v in values:
            f.write(f"{v & mask:0{digits}x}\n")


def _directed_32() -> list[int]:
    return [0x00000000, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555,
            0x80000000, 0x00000001, 0x7FFFFFFF, 0xDEADBEEF]


# ---------------------------------------------------------------------
# Ch / Maj / Sigma (combinational primitives)
# ---------------------------------------------------------------------
def gen_ch_maj_vectors(out_dir: Path, rng: random.Random, n_random: int = 5000) -> int:
    directed = _directed_32()
    xs = list(directed)
    ys = list(directed)
    zs = list(directed)
    # directed cross-product would be huge; pair them positionally + random fill
    n_directed = len(directed)
    for _ in range(n_random):
        xs.append(rng.getrandbits(32))
        ys.append(rng.getrandbits(32))
        zs.append(rng.getrandbits(32))
    ch_vals = [m.ch(x, y, z) for x, y, z in zip(xs, ys, zs)]
    maj_vals = [m.maj(x, y, z) for x, y, z in zip(xs, ys, zs)]

    _w32(out_dir / "ch_maj_x.hex", xs)
    _w32(out_dir / "ch_maj_y.hex", ys)
    _w32(out_dir / "ch_maj_z.hex", zs)
    _w32(out_dir / "ch_expected.hex", ch_vals)
    _w32(out_dir / "maj_expected.hex", maj_vals)
    return len(xs)


def gen_sigma_vectors(out_dir: Path, rng: random.Random, n_random: int = 5000) -> int:
    xs = list(_directed_32())
    for _ in range(n_random):
        xs.append(rng.getrandbits(32))
    _w32(out_dir / "sigma_x.hex", xs)
    _w32(out_dir / "sigma_bsig0_expected.hex", [m.big_sigma0(x) for x in xs])
    _w32(out_dir / "sigma_bsig1_expected.hex", [m.big_sigma1(x) for x in xs])
    _w32(out_dir / "sigma_ssig0_expected.hex", [m.small_sigma0(x) for x in xs])
    _w32(out_dir / "sigma_ssig1_expected.hex", [m.small_sigma1(x) for x in xs])
    return len(xs)


# ---------------------------------------------------------------------
# Message schedule: N blocks, each 16 input words + 64 expected W-words
# ---------------------------------------------------------------------
def gen_schedule_vectors(out_dir: Path, rng: random.Random, n_blocks: int = 40) -> int:
    all_blocks: list[int] = []
    all_expected: list[int] = []
    for _ in range(n_blocks):
        block16 = [rng.getrandbits(32) for _ in range(16)]
        block_bytes = b"".join(w.to_bytes(4, "big") for w in block16)
        w64 = m.message_schedule(block_bytes)
        assert w64[:16] == block16
        all_blocks.extend(block16)
        all_expected.extend(w64)
    _w32(out_dir / "schedule_blocks.hex", all_blocks)      # n_blocks*16 words
    _w32(out_dir / "schedule_expected.hex", all_expected)  # n_blocks*64 words
    return n_blocks


# ---------------------------------------------------------------------
# Round function: directed real traces (from real messages) + random
# ---------------------------------------------------------------------
def gen_round_vectors(out_dir: Path, rng: random.Random, n_random: int = 5000) -> int:
    a_in, b_in, c_in, d_in, e_in, f_in, g_in, h_in, w_in, k_in = ([] for _ in range(10))
    a_o, b_o, c_o, d_o, e_o, f_o, g_o, h_o = ([] for _ in range(8))

    def add_case(a, b, c, d, e, f, g, h, w, k):
        s1 = m.big_sigma1(e); ch_v = m.ch(e, f, g)
        s0 = m.big_sigma0(a); maj_v = m.maj(a, b, c)
        t1 = (h + s1 + ch_v + k + w) & MASK32
        t2 = (s0 + maj_v) & MASK32
        a_in.append(a); b_in.append(b); c_in.append(c); d_in.append(d)
        e_in.append(e); f_in.append(f); g_in.append(g); h_in.append(h)
        w_in.append(w); k_in.append(k)
        a_o.append((t1 + t2) & MASK32); b_o.append(a); c_o.append(b); d_o.append(c)
        e_o.append((d + t1) & MASK32); f_o.append(e); g_o.append(f); h_o.append(g)

    # Directed: real round traces from compressing "abc" and empty string.
    for msg in (b"abc", b"", b"bitcoin" * 3):
        trace: list[m.RoundTrace] = []
        m.compress_block(m.H0, m.pad_message(msg)[:64], trace=trace)
        for rt in trace:
            add_case(rt.a, rt.b, rt.c, rt.d, rt.e, rt.f, rt.g, rt.h, rt.w_t, rt.k_t)

    for _ in range(n_random):
        add_case(*(rng.getrandbits(32) for _ in range(8)),
                  rng.getrandbits(32), rng.choice(m.K))

    for name, vals in (("round_a_in", a_in), ("round_b_in", b_in), ("round_c_in", c_in),
                        ("round_d_in", d_in), ("round_e_in", e_in), ("round_f_in", f_in),
                        ("round_g_in", g_in), ("round_h_in", h_in), ("round_w_in", w_in),
                        ("round_k_in", k_in), ("round_a_out", a_o), ("round_b_out", b_o),
                        ("round_c_out", c_o), ("round_d_out", d_o), ("round_e_out", e_o),
                        ("round_f_out", f_o), ("round_g_out", g_o), ("round_h_out", h_o)):
        _w32(out_dir / f"{name}.hex", vals)
    return len(a_in)


def _words_to_int256(words: Sequence[int]) -> int:
    v = 0
    for w in words:
        v = (v << 32) | (w & MASK32)
    return v


def _block_to_int512(block_bytes: bytes) -> int:
    assert len(block_bytes) == 64
    return int.from_bytes(block_bytes, "big")


# ---------------------------------------------------------------------
# sha256_compressor.sv: every single-block compression step of a set of
# messages (directed KATs + random, variable block counts), so a
# multi-block message exercises state_in continuation (not just H0).
# ---------------------------------------------------------------------
def gen_compressor_vectors(out_dir: Path, rng: random.Random, n_random: int = 1500, max_blocks: int = 4) -> int:
    state_ins: list[int] = []
    blocks: list[int] = []
    state_outs: list[int] = []

    def add_message(msg: bytes) -> None:
        padded = m.pad_message(msg)
        state = m.H0
        for off in range(0, len(padded), 64):
            block = padded[off:off + 64]
            state_ins.append(_words_to_int256(state))
            blocks.append(_block_to_int512(block))
            state = m.compress_block(state, block)
            state_outs.append(_words_to_int256(state))

    # Directed KATs: empty, "abc", NIST 2-block vector, and a hand-picked string.
    add_message(b"")
    add_message(b"abc")
    add_message(b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq")
    add_message(b"The quick brown fox jumps over the lazy dog")
    # The Bitcoin genesis block header itself (see docs/sha256_spec_notes.md /
    # python/silicaflux_bitcoin/reference/block_header.py) -- exercises the
    # exact 80-byte, 2-block shape used by every real header hash.
    genesis = bh.BlockHeader(
        version=1, prev_block=bytes(32),
        merkle_root=bytes.fromhex("4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"),
        timestamp=1231006505, bits=0x1d00ffff, nonce=2083236893,
    )
    add_message(genesis.serialize())

    for _ in range(n_random):
        msg_len = rng.randint(0, max_blocks * 64)
        data = bytes(rng.getrandbits(8) for _ in range(msg_len))
        add_message(data)

    _w_bits(out_dir / "compressor_state_in.hex", state_ins, 256)
    _w_bits(out_dir / "compressor_block.hex", blocks, 512)
    _w_bits(out_dir / "compressor_state_out.hex", state_outs, 256)
    return len(state_ins)


# ---------------------------------------------------------------------
# sha256_double_hash.sv: full 80-byte Bitcoin headers -> {midstate,
# pow_hash}, for both the raw-header (use_midstate=0) and midstate-reuse
# (use_midstate=1) RTL paths -- see tb/integration/tb_sha256_double_hash.sv.
# ---------------------------------------------------------------------
_GENESIS_MERKLE_ROOT_HEX = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"


def gen_double_hash_vectors(out_dir: Path, rng: random.Random, n_random: int = 800) -> int:
    block1s: list[int] = []
    tail4s: list[int] = []
    midstates: list[int] = []
    pow_hashes: list[int] = []

    def add(header: bh.BlockHeader) -> None:
        ser = header.serialize()
        b1, tail4 = ser[:64], ser[64:80]
        ms = m.midstate(b1)
        block1s.append(_block_to_int512(b1))
        tail4s.append(int.from_bytes(tail4, "big"))
        midstates.append(_words_to_int256(ms))
        pow_hashes.append(int.from_bytes(header.pow_hash(), "big"))

    # Directed: the real Bitcoin genesis block (fields sourced from Bitcoin
    # Core's chainparams.cpp; the resulting pow_hash is independently
    # verified in python golden-model self-tests to equal the well-known
    # 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f).
    add(bh.BlockHeader(
        version=1, prev_block=bytes(32),
        merkle_root=bytes.fromhex(_GENESIS_MERKLE_ROOT_HEX),
        timestamp=1231006505, bits=0x1d00ffff, nonce=2083236893,
    ))

    for _ in range(n_random):
        add(bh.BlockHeader(
            version=rng.getrandbits(32),
            prev_block=bytes(rng.getrandbits(8) for _ in range(32)),
            merkle_root=bytes(rng.getrandbits(8) for _ in range(32)),
            timestamp=rng.getrandbits(32),
            bits=rng.getrandbits(32),
            nonce=rng.getrandbits(32),
        ))

    _w_bits(out_dir / "dh_header_block1.hex", block1s, 512)
    _w_bits(out_dir / "dh_header_tail4.hex", tail4s, 128)
    _w_bits(out_dir / "dh_midstate.hex", midstates, 256)
    _w_bits(out_dir / "dh_pow_hash.hex", pow_hashes, 256)
    return len(block1s)


# ---------------------------------------------------------------------
# target_compare.sv / nbits_expand: nBits -> target expansion, and
# hash-vs-target comparison, cross-checked against
# python/silicaflux_bitcoin/reference/block_header.py:bits_to_target()/
# target_meets().
# ---------------------------------------------------------------------
def gen_nbits_expand_vectors(out_dir: Path, rng: random.Random, n_random: int = 150) -> int:
    bits_list = [0x1d00ffff, 0x1b0404cb, 0x207fffff, 0x03000000, 0x04000000, 0x00000000, 0x01003456]
    for _ in range(n_random):
        # Keep the exponent in a realistic range (1..0x22) most of the time
        # so mantissa<<shift/mantissa>>shift both get exercised; still
        # allow the full byte range occasionally for robustness.
        exponent = rng.choice([rng.randint(1, 34)] * 4 + [rng.randint(0, 255)])
        mantissa = rng.randint(0, 0x7FFFFF)
        bits_list.append(((exponent & 0xFF) << 24) | mantissa)

    targets = [bh.bits_to_target(b) for b in bits_list]
    _w_bits(out_dir / "target_bits.hex", bits_list, 32)
    _w_bits(out_dir / "target_expected.hex", targets, 256)
    return len(bits_list)


def gen_target_compare_vectors(out_dir: Path, rng: random.Random, n_random: int = 150) -> int:
    # hash-vs-target comparison cases: edge cases plus random 32-byte
    # digests paired with realistic (nBits-derived) targets, each checked
    # against target_meets()'s little-endian-as-integer semantics.
    known_targets = [bh.bits_to_target(b) for b in (0x1d00ffff, 0x1b0404cb, 0x207fffff, 0x1e0fffff)]
    hash_ints: list[int] = []
    target_ints: list[int] = []
    meets: list[int] = []
    # Edge-case DIGESTS (byte strings), not integers picked then
    # re-encoded: every case below must go through the exact same
    # digest -> {RTL hash-port int, Python target_meets()} derivation as
    # the random cases further down (both from int.from_bytes(digest,
    # "big") / target_meets(digest, t)), or the two sides silently test
    # different byte-order conventions against each other. An earlier
    # version of this generator picked an edge-case *integer* and fed it
    # through int.to_bytes(32, "little") for the Python side while
    # feeding the raw integer directly to the RTL side (which expects
    # MSB-first/"big" packing) -- those are two different digests, and
    # the mismatch briefly looked like an RTL bug (see git history /
    # session notes) until traced back to this inconsistency.
    edge_digests = [
        bytes(32),                                  # all-zero digest
        bytes([0xFF]) * 32,                          # all-ones digest
        (1).to_bytes(32, "big"),                     # digest = 1 (last byte 0x01)
        (1 << 255).to_bytes(32, "big"),               # digest with only its first bit set
    ]
    for digest in edge_digests:
        t = rng.randint(0, (1 << 256) - 1)
        h_int = int.from_bytes(digest, "big")
        hash_ints.append(h_int); target_ints.append(t)
        meets.append(1 if bh.target_meets(digest, t) else 0)
    for _ in range(n_random):
        digest = bytes(rng.getrandbits(8) for _ in range(32))
        t = rng.choice(known_targets)
        h_int = int.from_bytes(digest, "big")  # stored MSB-first, matching RTL's `hash` port convention
        hash_ints.append(h_int); target_ints.append(t)
        meets.append(1 if bh.target_meets(digest, t) else 0)

    _w_bits(out_dir / "target_hash_in.hex", hash_ints, 256)
    _w_bits(out_dir / "target_target_in.hex", target_ints, 256)
    _w_bits(out_dir / "target_meets_expected.hex", meets, 1)
    return len(hash_ints)


# ---------------------------------------------------------------------
# hash_core.sv: full nonce-search scenarios. For each scenario, a target
# is set to EXACTLY the pow_hash of a chosen ("found_index"-th) trial in
# the core's nonce sequence, so the expected outcome is deterministic
# (not probabilistic) -- the core must report a miss on every earlier
# trial and a hit, with the right nonce/hash, on that one. This is also
# the pattern the synthetic mining demo (section 42) and Python mining
# simulator use for "artificially easy target" testing.
# ---------------------------------------------------------------------
def gen_hash_core_vectors(out_dir: Path, rng: random.Random, n_scenarios: int = 6) -> int:
    fields = ["block1", "tail3", "nonce_init", "nonce_step", "target",
              "found_nonce", "found_hash", "trials_to_find", "midstate", "use_midstate"]
    out = {k: [] for k in fields}

    for s in range(n_scenarios):
        header = bh.BlockHeader(
            version=rng.getrandbits(32),
            prev_block=bytes(rng.getrandbits(8) for _ in range(32)),
            merkle_root=bytes(rng.getrandbits(8) for _ in range(32)),
            timestamp=rng.getrandbits(32),
            bits=rng.getrandbits(32),
            nonce=0,
        )
        nonce_init = rng.getrandbits(32) & 0xFFFFFFF0
        nonce_step = rng.choice([1, 2, 3])

        # Pick a genuinely small target (probability ~1/2^k per independent
        # trial that a hash meets it) and search forward for the real
        # first match, exactly like an actual miner -- rather than
        # fabricating a "found" trial and assuming (wrongly: a target
        # equal to a random hash value is met by ~50% of other random
        # hashes too) that no earlier trial collides.
        k = rng.randint(3, 6)
        target_int = (1 << (256 - k)) - 1
        max_trials = 800
        nonce = nonce_init
        found_index = None
        target_nonce = target_hash = None
        for i in range(max_trials):
            h = header.with_nonce(nonce)
            ph = h.pow_hash()
            if bh.target_meets(ph, target_int):
                found_index = i
                target_nonce, target_hash = nonce, ph
                break
            nonce = (nonce + nonce_step) & 0xFFFFFFFF
        assert found_index is not None, (
            f"scenario {s}: no nonce met target within {max_trials} trials "
            f"(k={k}) -- statistically shouldn't happen, rerun with a different seed"
        )

        ser = header.serialize()
        b1 = ser[:64]
        tail3_bytes = ser[64:76]  # merkle_tail(4)+ntime(4)+nbits(4) = 12 bytes, nonce excluded

        out["block1"].append(_block_to_int512(b1))
        out["tail3"].append(int.from_bytes(tail3_bytes, "big"))
        out["nonce_init"].append(nonce_init)
        out["nonce_step"].append(nonce_step)
        out["target"].append(target_int)
        out["found_nonce"].append(target_nonce)
        out["found_hash"].append(int.from_bytes(target_hash, "big"))  # RTL packs MSB-first
        out["trials_to_find"].append(found_index + 1)
        out["midstate"].append(_words_to_int256(m.midstate(b1)))
        out["use_midstate"].append(1 if s % 2 == 1 else 0)  # alternate both hash_core code paths

    _w_bits(out_dir / "hc_block1.hex", out["block1"], 512)
    _w_bits(out_dir / "hc_tail3.hex", out["tail3"], 96)
    _w_bits(out_dir / "hc_nonce_init.hex", out["nonce_init"], 32)
    _w_bits(out_dir / "hc_nonce_step.hex", out["nonce_step"], 32)
    _w_bits(out_dir / "hc_target.hex", out["target"], 256)
    _w_bits(out_dir / "hc_found_nonce.hex", out["found_nonce"], 32)
    _w_bits(out_dir / "hc_found_hash.hex", out["found_hash"], 256)
    _w_bits(out_dir / "hc_trials_to_find.hex", out["trials_to_find"], 32)
    _w_bits(out_dir / "hc_midstate.hex", out["midstate"], 256)
    _w_bits(out_dir / "hc_use_midstate.hex", out["use_midstate"], 1)
    return n_scenarios


# ---------------------------------------------------------------------
# hash_core_array.sv: a real multi-core parallel search. NUM_CORES cores
# each run the nonce_allocator's interleaved sequence in lockstep (fixed,
# data-independent per-trial latency -- every core completes its k-th
# trial on the same cycle), so "which core wins" is exactly "which core's
# sequence contains the smallest-index match" -- computed here directly
# from the golden model, not assumed.
# ---------------------------------------------------------------------
def gen_hash_core_array_vectors(out_dir: Path, rng: random.Random,
                                 num_cores: int = 4, max_trials_per_core: int = 60) -> dict:
    header = bh.BlockHeader(
        version=rng.getrandbits(32),
        prev_block=bytes(rng.getrandbits(8) for _ in range(32)),
        merkle_root=bytes(rng.getrandbits(8) for _ in range(32)),
        timestamp=rng.getrandbits(32),
        bits=rng.getrandbits(32),
        nonce=0,
    )
    nonce_start = rng.getrandbits(32) & 0xFFFFFF00
    nonce_stride = 1
    step = nonce_stride * num_cores
    k = 5
    target_int = (1 << (256 - k)) - 1

    best_core, best_trial, best_nonce, best_hash = None, None, None, None
    per_core_trials_run = []
    for core_i in range(num_cores):
        nonce = (nonce_start + core_i * nonce_stride) & 0xFFFFFFFF
        found_trial = None
        for t in range(max_trials_per_core):
            h = header.with_nonce(nonce)
            ph = h.pow_hash()
            if bh.target_meets(ph, target_int):
                found_trial = t
                if best_trial is None or t < best_trial:
                    best_core, best_trial, best_nonce, best_hash = core_i, t, nonce, ph
                break
            nonce = (nonce + step) & 0xFFFFFFFF
        per_core_trials_run.append(found_trial if found_trial is not None else max_trials_per_core)

    assert best_trial is not None, "gen_hash_core_array_vectors: no core found a match, rerun with a different seed"
    # hash_core_array's total_hashes_completed is a SUM across all cores
    # (see its own header comment: "telemetry only"). All cores run in
    # lockstep (fixed, data-independent per-trial latency), so every core
    # -- including the eventual loser(s), preempted by the shared `stop`
    # before reaching whatever later trial *their own* search would have
    # matched at -- completes exactly best_trial+1 trials by the cycle the
    # winner's found pulse fires. Total = num_cores * (best_trial + 1).
    expected_hashes_completed = num_cores * (best_trial + 1)

    ser = header.serialize()
    b1 = ser[:64]
    tail3_bytes = ser[64:76]

    data = dict(
        NUM_CORES=num_cores,
        BLOCK1=_block_to_int512(b1),
        TAIL3=int.from_bytes(tail3_bytes, "big"),
        NONCE_START=nonce_start,
        NONCE_STRIDE=nonce_stride,
        TARGET=target_int,
        FOUND_CORE_ID=best_core,
        FOUND_NONCE=best_nonce,
        FOUND_HASH=int.from_bytes(best_hash, "big"),
        EXPECTED_HASHES_COMPLETED=expected_hashes_completed,
    )
    lines = ["// AUTO-GENERATED by silicaflux_bitcoin.vectors.generate_vectors -- DO NOT EDIT.",
             "// Single multi-core search scenario for tb/system/tb_hash_core_array.sv."]
    widths = dict(NUM_CORES=32, BLOCK1=512, TAIL3=96, NONCE_START=32, NONCE_STRIDE=32,
                  TARGET=256, FOUND_CORE_ID=32, FOUND_NONCE=32, FOUND_HASH=256,
                  EXPECTED_HASHES_COMPLETED=32)
    for key, val in data.items():
        w = widths[key]
        lines.append(f"`define HCA_{key} {w}'h{val:0{(w + 3)//4}x}")
    (out_dir / "hca_scenario.svh").write_text("\n".join(lines) + "\n")
    return data


# ---------------------------------------------------------------------
# miner_top.sv: one full end-to-end scenario via the header-loading
# interface, using a REAL nBits encoding (not a synthetic target) so
# miner_controller's own nbits_expand path is exercised exactly as a real
# job would drive it.
# ---------------------------------------------------------------------
def gen_miner_top_vectors(out_dir: Path, rng: random.Random,
                           num_cores: int = 4, max_trials_per_core: int = 60) -> dict:
    want_target = (1 << (256 - 6)) - 1
    bits = bh.target_to_bits(want_target)
    target_int = bh.bits_to_target(bits)  # the exact value nbits_expand will independently compute
    assert target_int > 0

    header = bh.BlockHeader(
        version=rng.getrandbits(32),
        prev_block=bytes(rng.getrandbits(8) for _ in range(32)),
        merkle_root=bytes(rng.getrandbits(8) for _ in range(32)),
        timestamp=rng.getrandbits(32),
        bits=bits,
        nonce=0,
    )
    nonce_start = rng.getrandbits(32) & 0xFFFFFF00
    nonce_stride = 1
    step = nonce_stride * num_cores

    best_core, best_trial, best_nonce, best_hash = None, None, None, None
    for core_i in range(num_cores):
        nonce = (nonce_start + core_i * nonce_stride) & 0xFFFFFFFF
        for t in range(max_trials_per_core):
            h = header.with_nonce(nonce)
            ph = h.pow_hash()
            if bh.target_meets(ph, target_int):
                if best_trial is None or t < best_trial:
                    best_core, best_trial, best_nonce, best_hash = core_i, t, nonce, ph
                break
            nonce = (nonce + step) & 0xFFFFFFFF
    assert best_trial is not None, "gen_miner_top_vectors: no core found a match, rerun with a different seed"

    ser = header.serialize()
    header_data = int.from_bytes(ser[:76], "big")  # {block1(512), tail3(96)} = header[0:76)

    data = dict(
        NUM_CORES=num_cores,
        HEADER_DATA=header_data,
        NONCE_START=nonce_start,
        NONCE_STRIDE=nonce_stride,
        BITS=bits,
        TARGET=target_int,
        FOUND_CORE_ID=best_core,
        FOUND_NONCE=best_nonce,
        FOUND_HASH=int.from_bytes(best_hash, "big"),
    )
    widths = dict(NUM_CORES=32, HEADER_DATA=608, NONCE_START=32, NONCE_STRIDE=32, BITS=32,
                  TARGET=256, FOUND_CORE_ID=32, FOUND_NONCE=32, FOUND_HASH=256)
    lines = ["// AUTO-GENERATED by silicaflux_bitcoin.vectors.generate_vectors -- DO NOT EDIT.",
             "// End-to-end scenario for tb/system/tb_miner_top.sv."]
    for key, val in data.items():
        w = widths[key]
        lines.append(f"`define MTOP_{key} {w}'h{val:0{(w + 3)//4}x}")
    (out_dir / "miner_top_scenario.svh").write_text("\n".join(lines) + "\n")
    return data


def _write_counts_header(out_dir: Path, counts: dict) -> None:
    """Emit tb/vectors/vector_counts.svh so testbenches size their arrays
    from a generated constant instead of a hardcoded literal that could
    silently drift out of sync with the generator (section 36 automation:
    the SV side must never guess how many vectors Python produced)."""
    lines = [
        "// AUTO-GENERATED by silicaflux_bitcoin.vectors.generate_vectors -- DO NOT EDIT.",
        "// `include`d by tb/unit testbenches to size vector arrays exactly to",
        "// what generate_vectors.py actually wrote this run.",
    ]
    name_map = {
        "ch_maj": "CH_MAJ_N",
        "sigma": "SIGMA_N",
        "schedule_blocks": "SCHEDULE_NBLOCKS",
        "round": "ROUND_N",
        "compressor": "COMPRESSOR_N",
        "double_hash": "DOUBLE_HASH_N",
        "nbits_expand": "NBITS_EXPAND_N",
        "target_compare": "TARGET_COMPARE_N",
        "hash_core": "HASH_CORE_N",
    }
    for key, macro in name_map.items():
        lines.append(f"`define {macro} {counts[key]}")
    (out_dir / "vector_counts.svh").write_text("\n".join(lines) + "\n")


def generate_all(out_dir: Path, seed: int = 1234) -> dict:
    rng = random.Random(seed)
    counts = {}
    counts["ch_maj"] = gen_ch_maj_vectors(out_dir, rng)
    counts["sigma"] = gen_sigma_vectors(out_dir, rng)
    counts["schedule_blocks"] = gen_schedule_vectors(out_dir, rng)
    counts["round"] = gen_round_vectors(out_dir, rng)
    counts["compressor"] = gen_compressor_vectors(out_dir, rng)
    counts["double_hash"] = gen_double_hash_vectors(out_dir, rng)
    counts["nbits_expand"] = gen_nbits_expand_vectors(out_dir, rng)
    counts["target_compare"] = gen_target_compare_vectors(out_dir, rng)
    counts["hash_core"] = gen_hash_core_vectors(out_dir, rng)
    gen_hash_core_array_vectors(out_dir, rng)
    gen_miner_top_vectors(out_dir, rng)
    _write_counts_header(out_dir, counts)
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate SystemVerilog test vectors from the Python golden model.")
    ap.add_argument("--out-dir", type=Path, default=Path("tb/vectors"))
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args(argv)
    counts = generate_all(args.out_dir, args.seed)
    for name, n in counts.items():
        print(f"[silicaflux.vectors] {name}: {n} cases -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
