"""Strict SI unit-handling layer.

ICECREAM-X uses SI units internally everywhere:

    kg, m, m^3, s, K, Pa, W, J, kWh

This module exists to make it *hard* to accidentally mix:

    grams / kilograms
    litres / cubic metres
    Celsius / Kelvin
    kW / W

Rather than pulling in a full dimensional-analysis library (``pint``), we use
small, explicit, frozen dataclasses for the handful of quantities that are
routinely confused in food-process engineering. Each type only knows how to
convert to/from its SI-canonical representation. Every internal engine
computation is expected to consume/produce **plain floats already in SI
base units** (kg, K, s, Pa, W, J) -- the wrapper types below are the
*boundary* layer used at API/user-input edges, in tests, and anywhere a
human-supplied value needs an explicit, checked unit.

This keeps the hot simulation loop free of object overhead while still
giving us a strict, typed conversion boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

KELVIN_OFFSET = 273.15


def celsius_to_kelvin(celsius: float) -> float:
    """Convert a temperature in degrees Celsius to Kelvin."""
    return celsius + KELVIN_OFFSET


def kelvin_to_celsius(kelvin: float) -> float:
    """Convert a temperature in Kelvin to degrees Celsius."""
    return kelvin - KELVIN_OFFSET


def grams_to_kilograms(grams: float) -> float:
    return grams / 1000.0


def kilograms_to_grams(kilograms: float) -> float:
    return kilograms * 1000.0


def litres_to_cubic_metres(litres: float) -> float:
    return litres / 1000.0


def cubic_metres_to_litres(cubic_metres: float) -> float:
    return cubic_metres * 1000.0


def watts_to_kilowatts(watts: float) -> float:
    return watts / 1000.0


def kilowatts_to_watts(kilowatts: float) -> float:
    return kilowatts * 1000.0


def joules_to_kilowatt_hours(joules: float) -> float:
    return joules / 3_600_000.0


def kilowatt_hours_to_joules(kilowatt_hours: float) -> float:
    return kilowatt_hours * 3_600_000.0


def minutes_to_seconds(minutes: float) -> float:
    return minutes * 60.0


def hours_to_seconds(hours: float) -> float:
    return hours * 3600.0


@dataclass(frozen=True, slots=True)
class Temperature:
    """A temperature value with an explicit, checked unit.

    Internally stored in Kelvin (SI). Construct with :meth:`from_celsius`
    or :meth:`from_kelvin`; never pass a bare float across a module
    boundary that expects a physical temperature -- wrap it here first so
    a Celsius/Kelvin mix-up raises instead of silently producing nonsense
    thermodynamics.
    """

    kelvin: float

    @classmethod
    def from_celsius(cls, celsius: float) -> "Temperature":
        return cls(celsius_to_kelvin(celsius))

    @classmethod
    def from_kelvin(cls, kelvin: float) -> "Temperature":
        if kelvin < 0:
            raise ValueError(f"Temperature below absolute zero: {kelvin} K")
        return cls(kelvin)

    @property
    def celsius(self) -> float:
        return kelvin_to_celsius(self.kelvin)

    def __add__(self, delta_kelvin: float) -> "Temperature":
        return Temperature.from_kelvin(self.kelvin + delta_kelvin)

    def __sub__(self, other: "Temperature | float") -> "Temperature | float":
        if isinstance(other, Temperature):
            return self.kelvin - other.kelvin
        return Temperature.from_kelvin(self.kelvin - other)

    def __lt__(self, other: "Temperature") -> bool:
        return self.kelvin < other.kelvin

    def __le__(self, other: "Temperature") -> bool:
        return self.kelvin <= other.kelvin

    def __gt__(self, other: "Temperature") -> bool:
        return self.kelvin > other.kelvin

    def __ge__(self, other: "Temperature") -> bool:
        return self.kelvin >= other.kelvin

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Temperature({self.celsius:.3f} degC)"


@dataclass(frozen=True, slots=True)
class Mass:
    """A mass value, stored internally in kilograms (SI)."""

    kilograms: float

    @classmethod
    def from_grams(cls, grams: float) -> "Mass":
        return cls(grams_to_kilograms(grams))

    @classmethod
    def from_kilograms(cls, kilograms: float) -> "Mass":
        if kilograms < 0:
            raise ValueError(f"Negative mass: {kilograms} kg")
        return cls(kilograms)

    @property
    def grams(self) -> float:
        return kilograms_to_grams(self.kilograms)

    def __add__(self, other: "Mass") -> "Mass":
        return Mass.from_kilograms(self.kilograms + other.kilograms)

    def __sub__(self, other: "Mass") -> "Mass":
        return Mass.from_kilograms(self.kilograms - other.kilograms)


@dataclass(frozen=True, slots=True)
class Volume:
    """A volume value, stored internally in cubic metres (SI)."""

    cubic_metres: float

    @classmethod
    def from_litres(cls, litres: float) -> "Volume":
        return cls(litres_to_cubic_metres(litres))

    @classmethod
    def from_cubic_metres(cls, cubic_metres: float) -> "Volume":
        if cubic_metres < 0:
            raise ValueError(f"Negative volume: {cubic_metres} m3")
        return cls(cubic_metres)

    @property
    def litres(self) -> float:
        return cubic_metres_to_litres(self.cubic_metres)


@dataclass(frozen=True, slots=True)
class Power:
    """A power value, stored internally in watts (SI)."""

    watts: float

    @classmethod
    def from_kilowatts(cls, kilowatts: float) -> "Power":
        return cls(kilowatts_to_watts(kilowatts))

    @property
    def kilowatts(self) -> float:
        return watts_to_kilowatts(self.watts)


@dataclass(frozen=True, slots=True)
class Energy:
    """An energy value, stored internally in joules (SI)."""

    joules: float

    @classmethod
    def from_kilowatt_hours(cls, kwh: float) -> "Energy":
        return cls(kilowatt_hours_to_joules(kwh))

    @property
    def kilowatt_hours(self) -> float:
        return joules_to_kilowatt_hours(self.joules)

    def __add__(self, other: "Energy") -> "Energy":
        return Energy(self.joules + other.joules)
