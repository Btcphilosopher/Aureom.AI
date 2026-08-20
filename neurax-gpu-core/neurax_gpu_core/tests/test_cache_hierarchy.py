from neurax_gpu_core.memory.cache_hierarchy import CacheHierarchy, CacheLevel


def test_cache_level_hit_on_repeat_access():
    cache = CacheLevel("L1", size_kb=32, line_bytes=128, associativity=4, hit_latency_cycles=10)
    assert cache.access(0x1000, is_write=False) is False  # first touch: miss
    assert cache.access(0x1000, is_write=False) is True   # same line: hit
    assert cache.stats.hits == 1
    assert cache.stats.misses == 1


def test_cache_level_evicts_lru_way():
    # size 1KB / 512B lines / 2-way => exactly 1 set, fully-associative 2-way.
    cache = CacheLevel("L1", size_kb=1, line_bytes=512, associativity=2, hit_latency_cycles=10)
    assert cache.num_sets == 1
    assert cache.access(0, is_write=False) is False        # tag 0: miss, fill
    assert cache.access(512, is_write=False) is False       # tag 1: miss, fill (way full)
    assert cache.access(0, is_write=False) is True          # tag 0: hit, becomes MRU
    assert cache.access(1024, is_write=False) is False      # tag 2: miss, evicts LRU (tag 1)
    assert cache.stats.evictions == 1
    assert cache.access(512, is_write=False) is False       # tag 1 was evicted: miss again


def test_hierarchy_routes_l1_then_l2_then_mem():
    hierarchy = CacheHierarchy(
        num_sms=2, l1_kb=16, l1_line=64, l1_assoc=2, l1_latency=20,
        l2_kb=256, l2_line=64, l2_assoc=8, l2_latency=100,
    )
    level, latency = hierarchy.access(sm_id=0, address=0x4000, is_write=False)
    assert level == "MEM"
    level2, latency2 = hierarchy.access(sm_id=0, address=0x4000, is_write=False)
    assert level2 == "L1"
    assert latency2 == 20


def test_hit_rate_bounds():
    cache = CacheLevel("L1", size_kb=32, line_bytes=128, associativity=4, hit_latency_cycles=10)
    for addr in range(0, 128 * 200, 128):
        cache.access(addr, is_write=False)
    assert 0.0 <= cache.stats.hit_rate <= 1.0
