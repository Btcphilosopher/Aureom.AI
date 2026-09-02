import json
from dataclasses import dataclass

import numpy as np
import pytest

from silicaflux_pv_spectral.io_utils import to_json, to_jsonable
from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.pipeline import run_pipeline
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum


@dataclass
class _Inner:
    value: float


@dataclass
class _Outer:
    name: str
    inner: _Inner
    array: np.ndarray
    items: list


def test_to_jsonable_handles_nested_dataclasses_and_arrays():
    obj = _Outer(name="x", inner=_Inner(value=1.5), array=np.array([1, 2, 3]), items=[np.float64(2.0), {"a": np.int64(3)}])
    result = to_jsonable(obj)
    assert result == {"name": "x", "inner": {"value": 1.5}, "array": [1, 2, 3], "items": [2.0, {"a": 3}]}
    json.dumps(result)  # must not raise


def test_to_jsonable_converts_numpy_scalars():
    assert to_jsonable(np.float64(3.14)) == pytest.approx(3.14)
    assert to_jsonable(np.int32(7)) == 7
    assert to_jsonable(np.bool_(True)) is True


def test_to_jsonable_replaces_nan_and_inf_with_none():
    assert to_jsonable(float("nan")) is None
    assert to_jsonable(float("inf")) is None


def test_to_json_produces_valid_json_string():
    payload = to_json({"a": np.array([1.0, 2.0]), "b": 3})
    parsed = json.loads(payload)
    assert parsed == {"a": [1.0, 2.0], "b": 3}


def test_full_pipeline_result_is_serialisable():
    spectrum = terrestrial_spectrum()
    result = run_pipeline(spectrum, SILICON)
    payload = to_json(result)
    parsed = json.loads(payload)
    assert "spectral_response" in parsed
    assert "efficiency" in parsed
