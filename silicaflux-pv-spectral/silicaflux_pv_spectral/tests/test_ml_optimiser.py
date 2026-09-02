import itertools

import numpy as np
import pytest

from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.ml_optimiser import (
    FEATURE_NAMES,
    RidgeSurrogate,
    build_training_set,
    ml_optimise,
)
from silicaflux_pv_spectral.parameter_sweep import SweepConfiguration
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum


@pytest.fixture(scope="module")
def spectrum():
    return terrestrial_spectrum()


@pytest.fixture(scope="module")
def small_configurations():
    return [
        SweepConfiguration(*combo)
        for combo in itertools.product(
            [0.95 * SILICON.bandgap_eV, SILICON.bandgap_eV, 1.1 * SILICON.bandgap_eV],
            [SILICON.thickness_nm, SILICON.thickness_nm * 2],
            [1.3, 1.6],
            [1.0],
            [298.15],
            [0.0],
        )
    ]


def test_ridge_surrogate_fits_a_simple_linear_function_exactly_with_no_regularisation():
    rng = np.random.default_rng(0)
    X = rng.uniform(-1, 1, size=(50, 3))
    true_coef = np.array([2.0, -1.0, 0.5])
    y = X @ true_coef + 3.0
    model = RidgeSurrogate(alpha=1e-8).fit(X, y)
    predictions = model.predict(X)
    assert np.allclose(predictions, y, atol=1e-4)


def test_ridge_surrogate_is_deterministic():
    rng = np.random.default_rng(1)
    X = rng.uniform(-1, 1, size=(30, 4))
    y = rng.uniform(0, 1, size=30)
    m1 = RidgeSurrogate(alpha=1.0).fit(X, y)
    m2 = RidgeSurrogate(alpha=1.0).fit(X, y)
    assert np.allclose(m1.coef_, m2.coef_)


def test_build_training_set_has_expected_shape(spectrum, small_configurations):
    training_set = build_training_set(SILICON, spectrum, small_configurations)
    assert training_set.X.shape == (len(small_configurations), len(FEATURE_NAMES))
    assert training_set.y.shape == (len(small_configurations),)
    assert np.all(np.isfinite(training_set.X))
    assert np.all(np.isfinite(training_set.y))


def test_ml_optimise_recommendation_matches_a_real_physics_evaluated_configuration(spectrum, small_configurations):
    result = ml_optimise(SILICON, spectrum, small_configurations)
    assert result.recommended_configuration in small_configurations
    # the reported net energy must equal one of the true physics-evaluated targets, never an unvalidated raw prediction
    assert result.recommended_net_energy_w_m2 in list(result.training_set.y)


def test_ml_optimise_never_beats_the_true_best_observed_configuration(spectrum, small_configurations):
    result = ml_optimise(SILICON, spectrum, small_configurations)
    assert result.recommended_net_energy_w_m2 <= result.best_observed_net_energy_w_m2 + 1e-9


def test_ml_optimise_falls_back_to_best_observed_when_not_accepted(spectrum, small_configurations):
    result = ml_optimise(SILICON, spectrum, small_configurations)
    if not result.ml_recommendation_accepted:
        assert result.recommended_configuration == result.best_observed_configuration
        assert result.recommended_net_energy_w_m2 == result.best_observed_net_energy_w_m2


def test_feature_importance_has_every_feature_name(spectrum, small_configurations):
    result = ml_optimise(SILICON, spectrum, small_configurations)
    assert set(result.feature_importance.keys()) == set(FEATURE_NAMES)


def test_r_squared_is_reasonable(spectrum, small_configurations):
    result = ml_optimise(SILICON, spectrum, small_configurations)
    assert 0.0 <= result.r_squared_training_fit <= 1.0 + 1e-6


def test_ml_optimise_is_deterministic(spectrum, small_configurations):
    r1 = ml_optimise(SILICON, spectrum, small_configurations)
    r2 = ml_optimise(SILICON, spectrum, small_configurations)
    assert r1.recommended_configuration == r2.recommended_configuration
    assert r1.recommended_net_energy_w_m2 == r2.recommended_net_energy_w_m2
