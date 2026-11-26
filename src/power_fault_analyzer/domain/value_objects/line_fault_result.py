"""Immutable result models for an interior-line short-circuit study."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult


def _complex_mapping(
    values: Mapping[SequenceType, complex], name: str
) -> Mapping[SequenceType, complex]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a mapping.")
    copied: dict[SequenceType, complex] = {}
    for sequence, value in values.items():
        if not isinstance(sequence, SequenceType):
            raise TypeError(f"{name} keys must be SequenceType values.")
        number = complex(value)
        if not math.isfinite(number.real) or not math.isfinite(number.imag):
            raise ValueError(f"{name} values must be finite.")
        copied[sequence] = number
    return MappingProxyType(copied)


def _finite_tuple(
    values: tuple[complex, complex, complex], name: str
) -> tuple[complex, complex, complex]:
    if not isinstance(values, tuple) or len(values) != 3:
        raise TypeError(f"{name} must be a 3-value tuple in A-B-C order.")
    converted = tuple(complex(value) for value in values)
    if any(not math.isfinite(value.real) or not math.isfinite(value.imag) for value in converted):
        raise ValueError(f"{name} values must be finite.")
    return converted


@dataclass(frozen=True, slots=True)
class LineTerminalState:
    """Electrical state at one physical terminal, with current directed into the line."""

    bus_id: UUID
    base_voltage_kv: float
    base_current_ka: float
    sequence_voltages_pu: Mapping[SequenceType, complex]
    sequence_currents_into_line_pu: Mapping[SequenceType, complex]
    phase_voltages_pu: tuple[complex, complex, complex]
    phase_voltages_kv: tuple[complex, complex, complex]
    phase_currents_into_line_pu: tuple[complex, complex, complex]
    phase_currents_into_line_ka: tuple[complex, complex, complex]

    def __post_init__(self) -> None:
        if not isinstance(self.bus_id, UUID):
            raise TypeError("bus_id must be a UUID value.")
        for name in ("base_voltage_kv", "base_current_ka"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a real number.")
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")
        object.__setattr__(
            self,
            "sequence_voltages_pu",
            _complex_mapping(self.sequence_voltages_pu, "sequence_voltages_pu"),
        )
        object.__setattr__(
            self,
            "sequence_currents_into_line_pu",
            _complex_mapping(self.sequence_currents_into_line_pu, "sequence_currents_into_line_pu"),
        )
        for name in (
            "phase_voltages_pu",
            "phase_voltages_kv",
            "phase_currents_into_line_pu",
            "phase_currents_into_line_ka",
        ):
            object.__setattr__(self, name, _finite_tuple(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class LineFaultStudyResult:
    """Interior-line fault result and the calculated states at both line terminals."""

    branch_id: UUID
    line_name: str
    from_bus_id: UUID
    to_bus_id: UUID
    fault_node_id: UUID
    fraction_from: float
    line_length_km: float
    distance_from_km: float
    distance_to_km: float
    fault_result: ShortCircuitResult
    from_terminal: LineTerminalState
    to_terminal: LineTerminalState

    def __post_init__(self) -> None:
        for name in ("branch_id", "from_bus_id", "to_bus_id", "fault_node_id"):
            if not isinstance(getattr(self, name), UUID):
                raise TypeError(f"{name} must be a UUID value.")
        if not isinstance(self.line_name, str) or not self.line_name.strip():
            raise ValueError("line_name cannot be empty.")
        if not isinstance(self.fault_result, ShortCircuitResult):
            raise TypeError("fault_result must be a ShortCircuitResult value.")
        if self.fault_result.bus_id != self.fault_node_id:
            raise ValueError("fault_result must refer to the generated interior fault node.")
        if not isinstance(self.from_terminal, LineTerminalState) or not isinstance(
            self.to_terminal, LineTerminalState
        ):
            raise TypeError("Both terminal states must be LineTerminalState values.")
        if self.from_terminal.bus_id != self.from_bus_id:
            raise ValueError("from_terminal must refer to from_bus_id.")
        if self.to_terminal.bus_id != self.to_bus_id:
            raise ValueError("to_terminal must refer to to_bus_id.")
        for name in ("fraction_from", "line_length_km", "distance_from_km", "distance_to_km"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a real number.")
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")
        if not 0.0 < self.fraction_from < 1.0:
            raise ValueError("fraction_from must be strictly between zero and one.")
        if self.line_length_km <= 0.0:
            raise ValueError("line_length_km must be greater than zero.")
        expected_from = self.fraction_from * self.line_length_km
        expected_to = self.line_length_km - expected_from
        if not math.isclose(self.distance_from_km, expected_from, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError(
                "distance_from_km is inconsistent with fraction_from and line_length_km."
            )
        if not math.isclose(self.distance_to_km, expected_to, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("distance_to_km is inconsistent with line_length_km.")

    @property
    def maximum_line_end_current_ka(self) -> float:
        """Largest RMS phase-current magnitude at either line terminal, in kA."""
        return max(
            max(abs(value) for value in self.from_terminal.phase_currents_into_line_ka),
            max(abs(value) for value in self.to_terminal.phase_currents_into_line_ka),
        )
