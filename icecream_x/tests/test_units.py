import pytest

from icecream_x.utils.units import (
    Energy,
    Mass,
    Temperature,
    Volume,
    celsius_to_kelvin,
    kelvin_to_celsius,
)


def test_celsius_kelvin_round_trip():
    for c in [-40.0, -18.0, 0.0, 4.0, 100.0]:
        assert kelvin_to_celsius(celsius_to_kelvin(c)) == pytest.approx(c)


def test_temperature_wrapper_round_trip():
    t = Temperature.from_celsius(-18.0)
    assert t.celsius == pytest.approx(-18.0)
    assert t.kelvin == pytest.approx(255.15)


def test_temperature_rejects_below_absolute_zero():
    with pytest.raises(ValueError):
        Temperature.from_kelvin(-1.0)


def test_mass_arithmetic():
    a = Mass.from_kilograms(2.0)
    b = Mass.from_grams(500.0)
    total = a + b
    assert total.kilograms == pytest.approx(2.5)
    assert total.grams == pytest.approx(2500.0)


def test_mass_rejects_negative():
    with pytest.raises(ValueError):
        Mass.from_kilograms(-1.0)


def test_volume_round_trip():
    v = Volume.from_litres(500.0)
    assert v.cubic_metres == pytest.approx(0.5)


def test_energy_kwh_round_trip():
    e = Energy.from_kilowatt_hours(1.0)
    assert e.joules == pytest.approx(3_600_000.0)
    assert e.kilowatt_hours == pytest.approx(1.0)
