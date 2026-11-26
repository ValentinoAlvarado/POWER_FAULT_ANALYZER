"""Immutable bus-fault specification in per-unit quantities."""

from __future__ import annotations

import math
from dataclasses import dataclass
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
class FaultSpecification:
    """Fault applied at one physical bus.

    ``fault_impedance_pu`` uses the positive-sequence three-phase system base at
    the faulted bus. Its physical interpretation depends on ``fault_type``:

    * three-phase: identical per-phase impedance from each phase to ground;
    * single-line-to-ground: impedance from phase A to ground;
    * line-to-line: impedance directly between phases B and C;
    * double-line-to-ground: common impedance from the B-C fault junction to ground.

    All reported phase quantities use the canonical A-B-C phase order.
    """

    fault_type: FaultType
    bus_id: UUID
    fault_impedance_pu: complex = 0.0j

    def __post_init__(self) -> None:
        if not isinstance(self.fault_type, FaultType):
            raise TypeError("fault_type must be a FaultType value.")
        if not isinstance(self.bus_id, UUID):
            raise TypeError("bus_id must be a UUID value.")
        object.__setattr__(self, "fault_impedance_pu", _finite_impedance(self.fault_impedance_pu))

    @classmethod
    def from_ohms(
        cls,
        fault_type: FaultType,
        bus_id: UUID,
        fault_impedance_ohm: complex,
        impedance_base: ElectricalImpedanceBase,
    ) -> FaultSpecification:
        """Create a specification by converting physical ohms to per unit."""
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
            bus_id=bus_id,
            fault_impedance_pu=impedance / impedance_base.base_impedance_ohm,
        )
