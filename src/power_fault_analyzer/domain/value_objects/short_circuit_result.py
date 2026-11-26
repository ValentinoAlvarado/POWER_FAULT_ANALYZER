"""Immutable result of a bus short-circuit calculation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.diagnostic import DomainDiagnostic


def _complex_mapping(
    values: Mapping[SequenceType, complex], name: str
) -> Mapping[SequenceType, complex]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a mapping.")
    copied: dict[SequenceType, complex] = {}
    for sequence, value in values.items():
        if not isinstance(sequence, SequenceType):
            raise TypeError(f"{name} keys must be SequenceType values.")
        if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
            raise TypeError(f"{name} values must be real or complex numbers.")
        number = complex(value)
        if not math.isfinite(number.real) or not math.isfinite(number.imag):
            raise ValueError(f"{name} values must be finite.")
        copied[sequence] = number
    return MappingProxyType(copied)


@dataclass(frozen=True, slots=True)
class ShortCircuitResult:
    """Fault solution with sequence and phase-domain quantities.

    Phase voltage entries are line-to-neutral complex kV; phase current entries
    are complex kA. The tuples always follow A-B-C order.
    """

    fault_type: FaultType
    bus_id: UUID
    fault_impedance_pu: complex
    base_power_mva: float
    base_voltage_kv: float
    base_current_ka: float
    prefault_sequence_voltages_pu: Mapping[SequenceType, complex]
    driving_point_impedances_pu: Mapping[SequenceType, complex]
    sequence_currents_pu: Mapping[SequenceType, complex]
    sequence_fault_voltages_pu: Mapping[SequenceType, complex]
    phase_currents_pu: tuple[complex, complex, complex]
    phase_voltages_pu: tuple[complex, complex, complex]
    phase_currents_ka: tuple[complex, complex, complex]
    phase_voltages_kv: tuple[complex, complex, complex]
    ground_current_pu: complex = 0.0j
    ground_current_ka: complex = 0.0j
    diagnostics: tuple[DomainDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.fault_type, FaultType):
            raise TypeError("fault_type must be a FaultType value.")
        if not isinstance(self.bus_id, UUID):
            raise TypeError("bus_id must be a UUID value.")
        fault_impedance = complex(self.fault_impedance_pu)
        if not math.isfinite(fault_impedance.real) or not math.isfinite(fault_impedance.imag):
            raise ValueError("fault_impedance_pu must be finite.")
        if fault_impedance.real < 0.0:
            raise ValueError("Fault resistance cannot be negative.")
        object.__setattr__(self, "fault_impedance_pu", fault_impedance)
        for name in ("base_power_mva", "base_voltage_kv", "base_current_ka"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a real number.")
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")
        for name in (
            "prefault_sequence_voltages_pu",
            "driving_point_impedances_pu",
            "sequence_currents_pu",
            "sequence_fault_voltages_pu",
        ):
            object.__setattr__(self, name, _complex_mapping(getattr(self, name), name))
        for name in (
            "phase_currents_pu",
            "phase_voltages_pu",
            "phase_currents_ka",
            "phase_voltages_kv",
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or len(values) != 3:
                raise TypeError(f"{name} must be a 3-value tuple in A-B-C order.")
            converted = tuple(complex(value) for value in values)
            if any(
                not math.isfinite(value.real) or not math.isfinite(value.imag)
                for value in converted
            ):
                raise ValueError(f"{name} values must be finite.")
            object.__setattr__(self, name, converted)
        for name in ("ground_current_pu", "ground_current_ka"):
            value = complex(getattr(self, name))
            if not math.isfinite(value.real) or not math.isfinite(value.imag):
                raise ValueError(f"{name} must be finite.")
            object.__setattr__(self, name, value)
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of DomainDiagnostic values.")

    @property
    def maximum_phase_current_ka(self) -> float:
        """Maximum RMS phase-current magnitude in kA."""
        return max(abs(value) for value in self.phase_currents_ka)
