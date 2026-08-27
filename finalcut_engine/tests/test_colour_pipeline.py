from __future__ import annotations

import numpy as np

from finalcut_engine.colour.colour_board import ColourBoard
from finalcut_engine.colour.colour_pipeline import ColourPipeline
from finalcut_engine.colour.colour_wheels import ColourWheel
from finalcut_engine.colour.curves import Curve
from finalcut_engine.colour.exposure import ExposureParams, apply_exposure
from finalcut_engine.colour.lut import LUT3D
from finalcut_engine.colour.matching import SmartColourMatching
from finalcut_engine.core.timebase import Time


def test_exposure_stops_doubles_brightness_per_stop():
    img = np.full((4, 4, 3), 0.25)
    out = apply_exposure(img, 1.0)
    assert np.allclose(out, 0.5)


def test_colour_wheel_is_a_linear_lift_gain_transform():
    img = np.full((2, 2, 3), 0.5)
    wheel = ColourWheel(lift=(0.1, 0.0, 0.0), gain=(1.0, 1.0, 1.0))
    out = wheel.apply(img)
    assert np.allclose(out[..., 0], 0.6)
    assert np.allclose(out[..., 1], 0.5)


def test_curve_is_monotonic_and_bounded():
    curve = Curve(points=[(0, 0), (0.5, 0.7), (1, 1)])
    xs = np.linspace(0, 1, 100)
    ys = curve.evaluate(xs)
    assert np.all(np.diff(ys) >= -1e-9)
    assert ys.min() >= 0 and ys.max() <= 1


def test_identity_lut_is_a_no_op():
    lut = LUT3D.identity(9)
    img = np.random.default_rng(0).uniform(0, 1, (5, 5, 3))
    out = lut.apply(img)
    assert np.allclose(out, img, atol=1e-2)


def test_lut_cube_round_trip(tmp_path):
    lut = LUT3D.identity(5)
    path = tmp_path / "test.cube"
    path.write_text(lut.to_cube_text())
    reloaded = LUT3D.from_cube_file(path)
    assert reloaded.size == lut.size
    assert np.allclose(reloaded.table, lut.table)


def test_colour_pipeline_stages_compose_and_stay_in_range():
    pipeline = ColourPipeline(
        exposure=ExposureParams(exposure_stops=0.5, saturation=1.2),
        colour=ColourBoard(wheels=ColourWheel(lift=(0.05, 0, 0))),
    )
    img = np.random.default_rng(1).uniform(0, 1, (8, 8, 3))
    out = pipeline.apply(img, Time.zero())
    assert out.shape == img.shape
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_smart_colour_matching_reproduces_reference_statistics_when_unclamped():
    rng = np.random.default_rng(2)
    target = rng.uniform(0.3, 0.6, (16, 16, 3))
    reference = np.clip(target * 1.1 + 0.05, 0, 1)

    result = SmartColourMatching().analyze(reference, target)
    corrected = target * np.array(result.wheel.gain) + np.array(result.wheel.lift)
    assert np.allclose(corrected.mean(axis=(0, 1)), reference.mean(axis=(0, 1)), atol=1e-6)
