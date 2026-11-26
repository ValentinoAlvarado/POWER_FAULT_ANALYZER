"""Three-phase per-unit base quantities and impedance conversions.

Conventions:
    - S_base_mva is total three-phase apparent power in MVA.
    - V_base_kv is line-to-line voltage in kV.
    - Derived I_base_ka is line current in kA.
    - Derived Z_base_ohm is per-phase impedance base in ohms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real


@dataclass(frozen=True, slots=True)
class BaseQuantities:
    """Base quantities for a balanced three-phase power system."""

    s_base_mva: float
    v_base_kv: float

    def __post_init__(self) -> None:
        for name, value in (
            ("s_base_mva", self.s_base_mva),
            ("v_base_kv", self.v_base_kv),
        ):
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a real numeric value.")
            if not math.isfinite(float(value)) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero.")
            object.__setattr__(self, name, float(value))

    @property
    def i_base_ka(self) -> float:
        """Three-phase line-current base in kA."""
        return self.s_base_mva / (math.sqrt(3.0) * self.v_base_kv)

    @property
    def z_base_ohm(self) -> float:
        """Per-phase impedance base in ohms."""
        return (self.v_base_kv**2) / self.s_base_mva

    @property
    def y_base_siemens(self) -> float:
        """Admittance base in siemens."""
        return 1.0 / self.z_base_ohm


def _finite_complex(value: complex, name: str) -> complex:
    if isinstance(value, bool) or not isinstance(value, (Real, complex)):
        raise TypeError(f"{name} must be a real or complex numeric value.")
    result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"{name} must have finite real and imaginary parts.")
    return result


def ohm_to_pu(
    impedance_ohm: complex,
    base: BaseQuantities,
) -> complex:
    """Convert impedance in ohms to per unit."""
    impedance = _finite_complex(impedance_ohm, "impedance_ohm")
    return impedance / base.z_base_ohm


def pu_to_ohm(
    impedance_pu: complex,
    base: BaseQuantities,
) -> complex:
    """Convert per-unit impedance to ohms."""
    impedance = _finite_complex(impedance_pu, "impedance_pu")
    return impedance * base.z_base_ohm


def convert_pu_base(
    impedance_pu: complex,
    old_base: BaseQuantities,
    new_base: BaseQuantities,
) -> complex:
    """Convert per-unit impedance between bases.

    Zpu,new = Zpu,old * (Snew/Sold) * (Vold/Vnew)^2
    where voltage bases use the same line-to-line convention.
    """
    impedance = _finite_complex(impedance_pu, "impedance_pu")
    factor = (
        new_base.s_base_mva / old_base.s_base_mva * (old_base.v_base_kv / new_base.v_base_kv) ** 2
    )
    return impedance * factor
