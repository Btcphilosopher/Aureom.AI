from neurax_gpu_core.utils.config import GPUConfig, get_preset, PRESETS


def test_default_config_constructs():
    cfg = GPUConfig()
    assert cfg.architecture.num_sms > 0
    assert cfg.compute.cuda_cores_per_sm > 0


def test_presets_are_distinct():
    flagship = get_preset("flagship")
    efficiency = get_preset("efficiency")
    assert flagship.architecture.num_sms > efficiency.architecture.num_sms
    assert flagship.power.tdp_watts > efficiency.power.tdp_watts


def test_round_trip_json(tmp_path):
    cfg = get_preset("mainstream")
    path = tmp_path / "cfg.json"
    cfg.save(path)
    loaded = GPUConfig.load(path)
    assert loaded.architecture.num_sms == cfg.architecture.num_sms
    assert loaded.name == cfg.name


def test_all_presets_registered():
    for name in PRESETS:
        cfg = get_preset(name)
        assert isinstance(cfg, GPUConfig)
