"""Generic three-phase per-unit impedance base."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real


def _positive_finite(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and greater than zero.")
    return result


@dataclass(frozen=True, slots=True)
class ElectricalImpedanceBase:
    """Three-phase apparent-power and line-to-line voltage reference base."""

    base_power_mva: float
    base_voltage_kv: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "base_power_mva", _positive_finite(self.base_power_mva, "base_power_mva")
        )
        object.__setattr__(
            self, "base_voltage_kv", _positive_finite(self.base_voltage_kv, "base_voltage_kv")
        )

    @property
    def base_impedance_ohm(self) -> float:
        """Return Zbase = VLL_base² / S3φ_base in ohms."""
        return self.base_voltage_kv**2 / self.base_power_mva

    @property
    def base_current_ka(self) -> float:
        """Return three-phase base current in kA."""
        return self.base_power_mva / (3.0**0.5 * self.base_voltage_kv)
