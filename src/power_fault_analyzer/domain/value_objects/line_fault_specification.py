"""Immutable interior-line short-circuit location and fault input."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from uuid import UUID

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)


def _finite_impedance(value: complex) -> complex:
    if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
        raise TypeError("fault_impedance_pu must be a real or complex number, not bool.")
    result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError("Fault impedance must have finite real and imaginary parts.")
    if result.real < 0.0:
        raise ValueError("Fault resistance cannot be negative.")
    return result


@dataclass(frozen=True, slots=True)
class LineFaultSpecification:
    """Fault at an interior point of a transmission line or underground cable.

    ``fraction_from`` is measured from the branch's ``from_node_id`` terminal and
    must be strictly between zero and one. End-point faults are bus faults and
    should use :class:`FaultSpecification` from ND-006 instead.

    Fault impedance uses the three-phase system base and the line-to-line voltage
    base shared by both line terminals.
    """

    fault_type: FaultType
    branch_id: UUID
    fraction_from: float
    fault_impedance_pu: complex = 0.0j

    def __post_init__(self) -> None:
        if not isinstance(self.fault_type, FaultType):
            raise TypeError("fault_type must be a FaultType value.")
        if not isinstance(self.branch_id, UUID):
            raise TypeError("branch_id must be a UUID value.")
        if isinstance(self.fraction_from, bool) or not isinstance(self.fraction_from, Real):
            raise TypeError("fraction_from must be a real number, not bool.")
        fraction = float(self.fraction_from)
        if not math.isfinite(fraction) or not 0.0 < fraction < 1.0:
            raise ValueError("fraction_from must be finite and strictly between zero and one.")
        object.__setattr__(self, "fraction_from", fraction)
        object.__setattr__(self, "fault_impedance_pu", _finite_impedance(self.fault_impedance_pu))

    @classmethod
    def from_ohms(
        cls,
        fault_type: FaultType,
        branch_id: UUID,
        fraction_from: float,
        fault_impedance_ohm: complex,
        impedance_base: ElectricalImpedanceBase,
    ) -> LineFaultSpecification:
        """Create a line-fault input by converting physical ohms to per unit."""
        if not isinstance(impedance_base, ElectricalImpedanceBase):
            raise TypeError("impedance_base must be an ElectricalImpedanceBase value.")
        if isinstance(fault_impedance_ohm, bool) or not isinstance(
            fault_impedance_ohm, (int, float, complex)
        ):
            raise TypeError("fault_impedance_ohm must be a real or complex number, not bool.")
        impedance = complex(fault_impedance_ohm)
        if not math.isfinite(impedance.real) or not math.isfinite(impedance.imag):
            raise ValueError("Fault impedance must have finite real and imaginary parts.")
        if impedance.real < 0.0:
            raise ValueError("Fault resistance cannot be negative.")
        return cls(
            fault_type=fault_type,
            branch_id=branch_id,
            fraction_from=fraction_from,
            fault_impedance_pu=impedance / impedance_base.base_impedance_ohm,
        )
