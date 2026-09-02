import pytest

from silicaflux_pv_spectral.digital_twin import PVCellDigitalTwin
from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum


@pytest.fixture(scope="module")
def spectrum():
    return terrestrial_spectrum()


def test_twin_computes_lazily_on_first_access(spectrum):
    twin = PVCellDigitalTwin(material=SILICON, spectrum=spectrum)
    assert twin._result is None
    assert twin._dirty
    _ = twin.result
    assert not twin._dirty
    assert twin._result is not None


def test_twin_caches_result_until_a_parameter_changes(spectrum):
    twin = PVCellDigitalTwin(material=SILICON, spectrum=spectrum)
    first = twin.result
    second = twin.result
    assert first is second  # no recompute happened


def test_set_material_parameter_marks_dirty_and_changes_output(spectrum):
    twin = PVCellDigitalTwin(material=SILICON, spectrum=spectrum)
    baseline_efficiency = twin.efficiency
    twin.set_parameter("bandgap_eV", 1.4)
    assert twin._dirty
    assert twin.bandgap_eV == 1.4
    assert twin.efficiency != baseline_efficiency


def test_set_encapsulant_uv_blocking_changes_uv_response(spectrum):
    twin = PVCellDigitalTwin(material=SILICON, spectrum=spectrum)
    baseline_uv = twin.spectral_response.uv_power_fraction
    twin.set_parameter("encapsulant_uv_blocking", False)
    assert twin.spectral_response.uv_power_fraction > baseline_uv


def test_set_ar_index_changes_reflection_and_stays_consistent(spectrum):
    twin = PVCellDigitalTwin(material=SILICON, spectrum=spectrum)
    baseline_eff = twin.efficiency
    twin.set_parameter("ar_index", 2.0)
    assert twin.optical_stack.layers[0].thickness_nm == 100.0  # unchanged
    assert twin.efficiency != baseline_eff


def test_set_unknown_parameter_raises_keyerror(spectrum):
    twin = PVCellDigitalTwin(material=SILICON, spectrum=spectrum)
    with pytest.raises(KeyError):
        twin.set_parameter("not_a_real_parameter", 123)


def test_layer_structure_includes_semiconductor_last(spectrum):
    twin = PVCellDigitalTwin(material=SILICON, spectrum=spectrum)
    structure = twin.layer_structure
    assert structure[-1]["name"] == "SILICON"
    assert len(structure) == len(twin.optical_stack.layers) + 1


def test_summary_is_json_serialisable(spectrum):
    import json

    twin = PVCellDigitalTwin(material=SILICON, spectrum=spectrum)
    summary = twin.summary()
    json.dumps(summary)  # must not raise
    assert summary["material"] == "SILICON"
    assert 0.0 < summary["efficiency"] < 1.0
