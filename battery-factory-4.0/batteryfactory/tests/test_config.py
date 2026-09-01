from batteryfactory.config.chemistry_profiles import CHEMISTRY_PROFILES, get_profile
from batteryfactory.config.factory_config import default_gigafactory_config
from batteryfactory.datamodel.models import Chemistry


def test_all_chemistries_have_profiles():
    for chem in Chemistry:
        profile = get_profile(chem)
        assert profile.chemistry == chem
        assert profile.nominal_voltage_v > 0
        assert profile.capacity_ah_reference > 0


def test_chemistry_clone_overrides():
    base = get_profile(Chemistry.LFP)
    clone = base.clone(nominal_voltage_v=3.3)
    assert clone.nominal_voltage_v == 3.3
    assert base.nominal_voltage_v == 3.2  # original untouched


def test_default_factory_config_capacity():
    cfg = default_gigafactory_config()
    assert cfg.theoretical_annual_capacity_cells > 0
    assert cfg.cells_per_pack() == cfg.module_architecture.cells_per_module * cfg.pack_architecture.modules_per_pack
