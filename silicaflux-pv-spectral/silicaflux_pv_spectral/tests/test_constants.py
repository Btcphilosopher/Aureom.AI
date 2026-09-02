import numpy as np

from silicaflux_pv_spectral import constants as C


def test_hc_ev_nm_matches_first_principles():
    assert abs(C.HC_EV_NM - C._HC_EV_NM_DERIVED) < 1e-4


def test_wavelength_grid_bounds_and_spacing():
    grid = C.wavelength_grid_nm()
    assert grid[0] == C.LAMBDA_MIN_NM
    assert grid[-1] == C.LAMBDA_MAX_NM
    assert np.allclose(np.diff(grid), C.DELTA_LAMBDA_NM)
    assert len(grid) == int(round((C.LAMBDA_MAX_NM - C.LAMBDA_MIN_NM) / C.DELTA_LAMBDA_NM)) + 1


def test_bands_are_contiguous_and_ordered():
    bands = C.SPECTRAL_BANDS_NM
    assert bands["UVC"][1] == bands["UVB"][0]
    assert bands["UVB"][1] == bands["UVA"][0]
    assert bands["UVA"][1] == bands["VISIBLE"][0]
    assert bands["VISIBLE"][1] == bands["NIR"][0]
    assert bands["UV"] == (bands["UVB"][0], bands["UVA"][1])
