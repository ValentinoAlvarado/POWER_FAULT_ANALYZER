"""Immutable scalar impedance and admittance value objects in SI units."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real


def _finite_real(value: Real, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real numeric value, not bool.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite.")
    return numeric


@dataclass(frozen=True, slots=True)
class Impedance:
    """Complex impedance stored as resistance and reactance in ohms.

    Negative reactance is valid (capacitive behavior). Negative resistance is
    rejected because this value object represents passive branch equipment.
    """

    resistance_ohm: float
    reactance_ohm: float

    def __post_init__(self) -> None:
        resistance = _finite_real(self.resistance_ohm, "resistance_ohm")
        reactance = _finite_real(self.reactance_ohm, "reactance_ohm")
        if resistance < 0.0:
            raise ValueError("Passive branch resistance cannot be negative.")
        object.__setattr__(self, "resistance_ohm", resistance)
        object.__setattr__(self, "reactance_ohm", reactance)

    @property
    def value_ohm(self) -> complex:
        return complex(self.resistance_ohm, self.reactance_ohm)

    def scaled(self, factor: Real) -> Impedance:
        scale = _finite_real(factor, "factor")
        if scale < 0.0:
            raise ValueError("Impedance scale factor cannot be negative.")
        return Impedance(
            resistance_ohm=self.resistance_ohm * scale,
            reactance_ohm=self.reactance_ohm * scale,
        )

    @classmethod
    def zero(cls) -> Impedance:
        return cls(0.0, 0.0)


@dataclass(frozen=True, slots=True)
class Admittance:
    """Complex admittance stored as conductance and susceptance in siemens."""

    conductance_siemens: float
    susceptance_siemens: float

    def __post_init__(self) -> None:
        conductance = _finite_real(self.conductance_siemens, "conductance_siemens")
        susceptance = _finite_real(self.susceptance_siemens, "susceptance_siemens")
        if conductance < 0.0:
            raise ValueError("Passive branch conductance cannot be negative.")
        object.__setattr__(self, "conductance_siemens", conductance)
        object.__setattr__(self, "susceptance_siemens", susceptance)

    @property
    def value_siemens(self) -> complex:
        return complex(self.conductance_siemens, self.susceptance_siemens)

    def scaled(self, factor: Real) -> Admittance:
        scale = _finite_real(factor, "factor")
        if scale < 0.0:
            raise ValueError("Admittance scale factor cannot be negative.")
        return Admittance(
            conductance_siemens=self.conductance_siemens * scale,
            susceptance_siemens=self.susceptance_siemens * scale,
        )

    @classmethod
    def zero(cls) -> Admittance:
        return cls(0.0, 0.0)
