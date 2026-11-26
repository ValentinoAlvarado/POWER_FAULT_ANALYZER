"""Immutable domain contracts for IEC 60909 calculations and traceability.

This module defines data contracts only. It deliberately contains no normative
calculation coefficients or equations; those belong to clause-mapped policies.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from numbers import Real
from types import MappingProxyType
from uuid import UUID, uuid4

from power_fault_analyzer.domain.enums.sequence_type import SequenceType

STANDARD_EDITION = "IEC 60909-0:2026"


class IEC60909SourceFamily(str, Enum):
    """Electrical source families with potentially different IEC procedures."""

    NETWORK_FEEDER = "network_feeder"
    SYNCHRONOUS_MACHINE = "synchronous_machine"
    ASYNCHRONOUS_MACHINE = "asynchronous_machine"
    CONVERTER = "converter"
    POWER_STATION_UNIT = "power_station_unit"
    OTHER = "other"


class IEC60909SourceMode(str, Enum):
    """Representation mode used for one source in a short-circuit study."""

    VOLTAGE_SOURCE = "voltage_source"
    CURRENT_SOURCE = "current_source"


class IEC60909CalculationQuantity(str, Enum):
    """Short-circuit quantities exposed by the calculation domain."""

    INITIAL_SYMMETRICAL_CURRENT = "I''k"
    PEAK_CURRENT = "ip"
    BREAKING_CURRENT = "Ib"
    DC_COMPONENT = "iDC"
    ASYMMETRICAL_BREAKING_CURRENT = "Ibasym"
    STEADY_STATE_CURRENT = "Ik"
    THERMAL_EQUIVALENT_CURRENT = "Ith"
    JOULE_INTEGRAL = "J"


class IEC60909QuantityStatus(str, Enum):
    """Explicit availability state; an unavailable quantity is never represented as zero."""

    CALCULATED = "calculated"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class IEC60909SourceDescriptor:
    """Declared in-service source input for a normalized IEC study scenario."""

    source_id: UUID
    name: str
    family: IEC60909SourceFamily
    mode: IEC60909SourceMode
    active_sequences: frozenset[SequenceType]
    model_reference: str
    in_service: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, UUID):
            raise TypeError("source_id must be a UUID value.")
        _non_empty_text(self.name, "name")
        _non_empty_text(self.model_reference, "model_reference")
        if not isinstance(self.family, IEC60909SourceFamily):
            raise TypeError("family must be an IEC60909SourceFamily value.")
        if not isinstance(self.mode, IEC60909SourceMode):
            raise TypeError("mode must be an IEC60909SourceMode value.")
        if not isinstance(self.active_sequences, frozenset) or any(
            not isinstance(item, SequenceType) for item in self.active_sequences
        ):
            raise TypeError("active_sequences must be a frozenset of SequenceType values.")
        if not self.active_sequences:
            raise ValueError("A source descriptor must declare at least one active sequence.")
        if not isinstance(self.in_service, bool):
            raise TypeError("in_service must be bool.")


@dataclass(frozen=True, slots=True)
class IEC60909FactorInput:
    """One numerical input retained as evidence for a correction factor."""

    name: str
    value: float
    unit: str

    def __post_init__(self) -> None:
        _non_empty_text(self.name, "name")
        _non_empty_text(self.unit, "unit")
        object.__setattr__(self, "value", _finite_real(self.value, "value"))


@dataclass(frozen=True, slots=True)
class IEC60909CorrectionFactor:
    """Applied correction factor with equipment/source and clause provenance."""

    name: str
    value: float
    unit: str
    clause_reference: str
    inputs: tuple[IEC60909FactorInput, ...]
    equipment_id: UUID | None = None
    source_id: UUID | None = None
    scenario_id: UUID | None = None
    factor_id: UUID = field(default_factory=uuid4)
    standard_edition: str = STANDARD_EDITION

    def __post_init__(self) -> None:
        _non_empty_text(self.name, "name")
        _non_empty_text(self.unit, "unit")
        _non_empty_text(self.clause_reference, "clause_reference")
        _non_empty_text(self.standard_edition, "standard_edition")
        value = _finite_real(self.value, "value")
        if value <= 0.0:
            raise ValueError("Correction factor value must be greater than zero.")
        if not isinstance(self.factor_id, UUID):
            raise TypeError("factor_id must be a UUID value.")
        for field_name in ("equipment_id", "source_id", "scenario_id"):
            identifier = getattr(self, field_name)
            if identifier is not None and not isinstance(identifier, UUID):
                raise TypeError(f"{field_name} must be a UUID value or None.")
        if self.equipment_id is None and self.source_id is None and self.scenario_id is None:
            raise ValueError(
                "A correction factor must be scoped to a scenario, source or equipment."
            )
        if not isinstance(self.inputs, tuple) or any(
            not isinstance(item, IEC60909FactorInput) for item in self.inputs
        ):
            raise TypeError("inputs must be a tuple of IEC60909FactorInput values.")
        if len({item.name for item in self.inputs}) != len(self.inputs):
            raise ValueError("Correction factor input names must be unique.")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class IEC60909QuantityResult:
    """One calculated or explicitly unavailable IEC short-circuit quantity."""

    quantity: IEC60909CalculationQuantity
    status: IEC60909QuantityStatus
    value: float | None
    unit: str
    method_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.quantity, IEC60909CalculationQuantity):
            raise TypeError("quantity must be an IEC60909CalculationQuantity value.")
        if not isinstance(self.status, IEC60909QuantityStatus):
            raise TypeError("status must be an IEC60909QuantityStatus value.")
        _non_empty_text(self.unit, "unit")
        expected_unit = (
            "kA^2 s" if self.quantity is IEC60909CalculationQuantity.JOULE_INTEGRAL else "kA"
        )
        if self.unit != expected_unit:
            raise ValueError(f"{self.quantity.value} must use unit {expected_unit!r}.")
        if self.status is IEC60909QuantityStatus.CALCULATED:
            if self.value is None:
                raise ValueError("A calculated quantity must provide a numerical value.")
            numeric = _finite_real(self.value, "value")
            if numeric < 0.0:
                raise ValueError("A short-circuit quantity cannot be negative.")
            _non_empty_text(self.method_id, "method_id")
            if self.reason is not None:
                raise ValueError("A calculated quantity cannot have an unavailable reason.")
            object.__setattr__(self, "value", numeric)
        else:
            if self.value is not None:
                raise ValueError("An unavailable or inapplicable quantity must not carry a value.")
            _non_empty_text(self.reason, "reason")
            if self.method_id is not None:
                raise ValueError("An unavailable quantity cannot declare a calculation method.")


@dataclass(frozen=True, slots=True)
class IEC60909SourceContribution:
    """Per-source fault contribution expressed in sequence and/or phase kA phasors."""

    source_id: UUID
    source_name: str
    source_family: IEC60909SourceFamily
    source_mode: IEC60909SourceMode
    sequence_currents_ka: Mapping[SequenceType, complex] = field(default_factory=dict)
    phase_currents_ka: Mapping[str, complex] = field(default_factory=dict)
    model_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, UUID):
            raise TypeError("source_id must be a UUID value.")
        _non_empty_text(self.source_name, "source_name")
        if not isinstance(self.source_family, IEC60909SourceFamily):
            raise TypeError("source_family must be an IEC60909SourceFamily value.")
        if not isinstance(self.source_mode, IEC60909SourceMode):
            raise TypeError("source_mode must be an IEC60909SourceMode value.")
        if self.model_reference is not None:
            _non_empty_text(self.model_reference, "model_reference")
        if not isinstance(self.sequence_currents_ka, Mapping):
            raise TypeError("sequence_currents_ka must be a mapping.")
        if not isinstance(self.phase_currents_ka, Mapping):
            raise TypeError("phase_currents_ka must be a mapping.")

        sequence_values: dict[SequenceType, complex] = {}
        for sequence, current in self.sequence_currents_ka.items():
            if not isinstance(sequence, SequenceType):
                raise TypeError("Sequence current keys must be SequenceType values.")
            sequence_values[sequence] = _finite_complex(current, "sequence current")

        phase_values: dict[str, complex] = {}
        for phase, current in self.phase_currents_ka.items():
            if phase not in {"A", "B", "C"}:
                raise ValueError("Phase current keys must use the canonical A, B or C labels.")
            phase_values[phase] = _finite_complex(current, "phase current")

        if not sequence_values and not phase_values:
            raise ValueError("A source contribution must contain sequence or phase currents.")
        object.__setattr__(self, "sequence_currents_ka", MappingProxyType(sequence_values))
        object.__setattr__(self, "phase_currents_ka", MappingProxyType(phase_values))


@dataclass(frozen=True, slots=True)
class IEC60909CalculationTrace:
    """Reproducibility record for a completed or partially completed study."""

    scenario_id: UUID
    source_contributions: tuple[IEC60909SourceContribution, ...] = ()
    applied_factors: tuple[IEC60909CorrectionFactor, ...] = ()
    quantity_results: tuple[IEC60909QuantityResult, ...] = ()
    method_ids: Mapping[IEC60909CalculationQuantity, str] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    input_fingerprint: str | None = None
    trace_id: UUID = field(default_factory=uuid4)
    standard_edition: str = STANDARD_EDITION

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, UUID) or not isinstance(self.trace_id, UUID):
            raise TypeError("scenario_id and trace_id must be UUID values.")
        _non_empty_text(self.standard_edition, "standard_edition")
        for name, values, expected_type in (
            ("source_contributions", self.source_contributions, IEC60909SourceContribution),
            ("applied_factors", self.applied_factors, IEC60909CorrectionFactor),
            ("quantity_results", self.quantity_results, IEC60909QuantityResult),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(item, expected_type) for item in values
            ):
                raise TypeError(f"{name} must be a tuple of {expected_type.__name__} values.")
        if len({item.source_id for item in self.source_contributions}) != len(
            self.source_contributions
        ):
            raise ValueError("A calculation trace cannot repeat a source contribution.")
        if len({item.factor_id for item in self.applied_factors}) != len(self.applied_factors):
            raise ValueError("A calculation trace cannot repeat a correction-factor ID.")
        if len({item.quantity for item in self.quantity_results}) != len(self.quantity_results):
            raise ValueError("A calculation trace can contain only one result per quantity.")
        for factor in self.applied_factors:
            if factor.standard_edition != self.standard_edition:
                raise ValueError("Correction factor standard edition does not match the trace.")
            if factor.scenario_id is not None and factor.scenario_id != self.scenario_id:
                raise ValueError("Correction factor scenario_id does not match the trace.")
        if not isinstance(self.method_ids, Mapping):
            raise TypeError("method_ids must be a mapping.")
        methods: dict[IEC60909CalculationQuantity, str] = {}
        for quantity, method_id in self.method_ids.items():
            if not isinstance(quantity, IEC60909CalculationQuantity):
                raise TypeError("method_ids keys must be IEC60909CalculationQuantity values.")
            methods[quantity] = _non_empty_text(method_id, "method_id")
        calculated_results = {
            item.quantity: item
            for item in self.quantity_results
            if item.status is IEC60909QuantityStatus.CALCULATED
        }
        if set(methods) != set(calculated_results):
            raise ValueError(
                "Trace method_ids must match exactly the quantities with calculated results."
            )
        for quantity, result in calculated_results.items():
            if methods[quantity] != result.method_id:
                raise ValueError("Trace method_id does not match the calculated quantity result.")
        if not isinstance(self.assumptions, tuple):
            raise TypeError("assumptions must be a tuple of strings.")
        assumptions = tuple(_non_empty_text(item, "assumption") for item in self.assumptions)
        if self.input_fingerprint is not None:
            _non_empty_text(self.input_fingerprint, "input_fingerprint")
        object.__setattr__(self, "method_ids", MappingProxyType(methods))
        object.__setattr__(self, "assumptions", assumptions)


def _non_empty_text(value: str | None, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value.strip()


def _finite_real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not bool.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite.")
    return numeric


def _finite_complex(value: complex, name: str) -> complex:
    if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
        raise TypeError(f"{name} must be a real or complex number, not bool.")
    numeric = complex(value)
    if not math.isfinite(numeric.real) or not math.isfinite(numeric.imag):
        raise ValueError(f"{name} must have finite real and imaginary components.")
    return numeric
