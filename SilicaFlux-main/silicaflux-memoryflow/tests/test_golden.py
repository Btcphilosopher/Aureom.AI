"""Golden models: SECDED, parity, bank maps, DMA validation, accelerator maths."""
import itertools
import random

import numpy as np
import pytest

from memoryflow.verify import golden as G


@pytest.mark.parametrize("k", [1, 4, 8, 16, 26, 27, 32, 57, 58, 64, 128])
def test_secded_r_matches_closed_form(k):
    clog2 = lambda x: (x - 1).bit_length()
    assert G.secded_r(k) == clog2(k + 1 + clog2(k + 1))
    assert (1 << G.secded_r(k)) >= k + G.secded_r(k) + 1


def test_secded_widths():
    assert G.secded_n(64) == 72 and G.secded_n(32) == 39 and G.secded_n(8) == 13


def test_data_positions_skip_powers_of_two():
    pos = [G.secded_dpos(j) for j in range(64)]
    assert len(set(pos)) == 64 and all(p & (p - 1) for p in pos) and pos[:4] == [3, 5, 6, 7]


@pytest.mark.parametrize("k", [8, 32, 64])
def test_secded_corrects_every_single_bit(k):
    rng = random.Random(k)
    for _ in range(20):
        d = rng.getrandbits(k)
        c = G.secded_encode(d, k)
        assert G.secded_decode(c, k) == G.SecdedResult(d, False, False, 0)
        for i in range(G.secded_n(k)):
            r = G.secded_decode(c ^ (1 << i), k)
            assert r.data == d and r.corrected and not r.uncorrectable


@pytest.mark.parametrize("k", [8, 32])
def test_secded_detects_every_double_bit(k):
    d = 0xA5A5A5A5 & ((1 << k) - 1)
    c = G.secded_encode(d, k)
    for i, j in itertools.combinations(range(G.secded_n(k)), 2):
        r = G.secded_decode(c ^ (1 << i) ^ (1 << j), k)
        assert r.uncorrectable and not r.corrected


def test_secded_rejects_out_of_range():
    with pytest.raises(ValueError):
        G.secded_encode(1 << 8, 8)


def test_parity_pack_even_parity():
    w = G.parity_pack(0x0103, 2)
    assert (w & 0x1FF) == 0x003 and ((w >> 9) & 0x1FF) == 0x101   # 0x03 even, 0x01 odd


@pytest.mark.parametrize("mode", [0, 1, 2])
@pytest.mark.parametrize("nb,bd", [(4, 256), (8, 512), (16, 64)])
def test_bank_map_is_bijective(mode, nb, bd):
    seen = {G.bank_map(w, nb, bd, mode) for w in range(nb * bd)}
    assert len(seen) == nb * bd


def test_bank_map_modes():
    assert [G.bank_map(w, 4, 256, 0)[0] for w in range(6)] == [0, 1, 2, 3, 0, 1]
    assert G.bank_map(4, 4, 256, 1)[0] == 1          # 0 ^ 1
    assert G.bank_map(256, 4, 256, 2) == (1, 0)


def test_dma_validate_codes():
    v = G.dma_validate
    assert v(0, 0, 0, 1, 0, 0, False) == G.DMA_E_ZERO
    assert v(4, 0, 8, 1, 0, 0, False) == G.DMA_E_ALIGN
    assert v(4, 0, 8, 1, 0, 0, False, src_stream=True) == 0
    assert v(0xFFFFFF00, 0, 0x200, 1, 0, 0, False) == G.DMA_E_OVF
    assert v(0, 0, 64, 0xFFFF, 0x100000, 64, True) == G.DMA_E_OVF
    assert v(0, 0, 64, 0x8000, 0x10000, 64, True) == 0


def test_dma_copy_2d():
    mem = bytearray(range(256)) * 4
    G.dma_copy(mem, 0, 512, 4, rows=3, sstride=16, dstride=8)
    assert mem[512:516] == bytes([0, 1, 2, 3]) and mem[520:524] == bytes([16, 17, 18, 19])


def test_tensor_tile_matches_numpy():
    rng = np.random.default_rng(1)
    a = rng.integers(-128, 128, (8, 37))
    b = rng.integers(-128, 128, (37, 8))
    assert np.array_equal(np.array(G.tensor_tile(a.tolist(), b.tolist())), a @ b)


def test_tensor_packing_roundtrip():
    a = [[i * 8 + k - 100 for k in range(3)] for i in range(8)]
    beats = G.pack_tensor_a(a)
    assert len(beats) == 3 and G.lanes_unpack(beats[1], 8, 8) == [a[i][1] for i in range(8)]


def test_vec_ops_wrap():
    assert G.vec_op(0, [32767], [1]) == [-32768]
    assert G.vec_op(1, [300], [300]) == [G._wrap(90000, 16)]
    assert G.vec_op(3, [2], [5], alpha=-3) == [-1]
    assert G.vec_op(2, [3, -4], [5, 6]) == -9


def test_vector_set_files(tmp_path):
    counts = G.write_vector_set(tmp_path)
    assert counts["ecc_k64_data.hex"] == 256
    lines = (tmp_path / "ecc_k64_code.hex").read_text().split()
    assert len(lines[0]) == 18
