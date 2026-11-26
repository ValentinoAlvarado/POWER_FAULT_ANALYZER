"""Immutable, presentation-neutral engineering result contracts.

These models normalize existing solver outputs without recalculating electrical
quantities. They intentionally preserve complex phasors and explicit availability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class QuantityAvailability(StrEnum):
    CALCULATED = "calculated"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    NOT_REPORTED = "not_reported"


class ResultLocationKind(StrEnum):
    BUS = "bus"
    LINE_INTERIOR = "line_interior"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value.strip()


def _finite(value: float, name: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number.")
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0.0):
        qualifier = "finite and non-negative" if nonnegative else "finite"
        raise ValueError(f"{name} must be {qualifier}.")
    return result


@dataclass(frozen=True, slots=True)
class PhasorValue:
    """Serializable complex phasor with derived magnitude and angle."""

    real: float
    imaginary: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "real", _finite(self.real, "real"))
        object.__setattr__(self, "imaginary", _finite(self.imaginary, "imaginary"))

    @classmethod
    def from_complex(cls, value: complex) -> PhasorValue:
        if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
            raise TypeError("Phasor value must be real or complex.")
        number = complex(value)
        return cls(number.real, number.imag)

    @property
    def magnitude(self) -> float:
        return math.hypot(self.real, self.imaginary)

    @property
    def angle_degrees(self) -> float:
        return math.degrees(math.atan2(self.imaginary, self.real)) if self.magnitude else 0.0


@dataclass(frozen=True, slots=True)
class PhaseQuantityResult:
    phase: str
    current_pu: PhasorValue
    current_ka: PhasorValue
    voltage_pu: PhasorValue
    voltage_kv: PhasorValue

    def __post_init__(self) -> None:
        if self.phase not in {"A", "B", "C"}:
            raise ValueError("phase must be A, B or C.")
        for name in ("current_pu", "current_ka", "voltage_pu", "voltage_kv"):
            if not isinstance(getattr(self, name), PhasorValue):
                raise TypeError(f"{name} must be a PhasorValue.")


@dataclass(frozen=True, slots=True)
class SequenceQuantityResult:
    sequence: str
    current_pu: PhasorValue | None
    voltage_pu: PhasorValue | None
    driving_point_impedance_pu: PhasorValue | None
    prefault_voltage_pu: PhasorValue | None

    def __post_init__(self) -> None:
        if self.sequence not in {"zero", "positive", "negative"}:
            raise ValueError("Unsupported sequence identifier.")
        for name in (
            "current_pu",
            "voltage_pu",
            "driving_point_impedance_pu",
            "prefault_voltage_pu",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, PhasorValue):
                raise TypeError(f"{name} must be a PhasorValue or None.")


@dataclass(frozen=True, slots=True)
class IECQuantityResult:
    name: str
    unit: str
    status: QuantityAvailability
    value: float | None = None
    method_reference: str | None = None
    reason: str | None = None
    classification: str = "normative"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "name"))
        object.__setattr__(self, "unit", _text(self.unit, "unit"))
        if not isinstance(self.status, QuantityAvailability):
            raise TypeError("status must be a QuantityAvailability value.")
        if self.value is not None:
            object.__setattr__(self, "value", _finite(self.value, "value", nonnegative=True))
        if self.status is QuantityAvailability.CALCULATED:
            if self.value is None:
                raise ValueError("A calculated quantity requires a value.")
            if self.reason is not None:
                raise ValueError("A calculated quantity cannot have an unavailable reason.")
        elif self.value is not None:
            raise ValueError("Unavailable or unreported quantities cannot carry a value.")
        if self.method_reference is not None:
            object.__setattr__(
                self, "method_reference", _text(self.method_reference, "method_reference")
            )
        if self.reason is not None:
            object.__setattr__(self, "reason", _text(self.reason, "reason"))
        if self.status is QuantityAvailability.UNAVAILABLE and self.reason is None:
            raise ValueError("An unavailable quantity requires a reason.")
        if self.classification not in {"normative", "supplementary", "engineering"}:
            raise ValueError("Unsupported quantity classification.")


@dataclass(frozen=True, slots=True)
class CorrectionFactorResult:
    name: str
    value: float
    provenance: str = "Provenance not supplied by source result contract."

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "name"))
        object.__setattr__(self, "value", _finite(self.value, "value"))
        object.__setattr__(self, "provenance", _text(self.provenance, "provenance"))


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    code: str
    severity: str
    message: str
    entity_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _text(self.code, "code"))
        object.__setattr__(self, "severity", _text(self.severity, "severity"))
        object.__setattr__(self, "message", _text(self.message, "message"))


@dataclass(frozen=True, slots=True)
class FaultResultRecord:
    fault_id: str
    location_kind: ResultLocationKind
    location_id: str
    location_name: str
    fault_type: str
    fault_impedance_pu: PhasorValue
    base_power_mva: float
    base_voltage_kv: float
    base_current_ka: float
    maximum_phase_current_ka: float
    phase_quantities: tuple[PhaseQuantityResult, ...]
    sequence_quantities: tuple[SequenceQuantityResult, ...]
    ground_current_pu: PhasorValue
    ground_current_ka: PhasorValue
    voltage_factor: float | None = None
    equivalent_voltage_pu: PhasorValue | None = None
    fault_duration_s: float | None = None
    frequency_hz: float | None = None
    first_pole_contact_separation_time_s: float | None = None
    current_case: str | None = None
    line_branch_id: str | None = None
    line_name: str | None = None
    from_bus_name: str | None = None
    to_bus_name: str | None = None
    distance_from_km: float | None = None
    distance_to_km: float | None = None
    iec_quantities: tuple[IECQuantityResult, ...] = ()
    correction_factors: tuple[CorrectionFactorResult, ...] = ()
    diagnostics: tuple[DiagnosticResult, ...] = ()

    def __post_init__(self) -> None:
        for name in ("fault_id", "location_id", "location_name", "fault_type"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.location_kind, ResultLocationKind):
            raise TypeError("location_kind must be a ResultLocationKind.")
        if not isinstance(self.fault_impedance_pu, PhasorValue):
            raise TypeError("fault_impedance_pu must be a PhasorValue.")
        for name in ("ground_current_pu", "ground_current_ka"):
            if not isinstance(getattr(self, name), PhasorValue):
                raise TypeError(f"{name} must be a PhasorValue.")
        if self.equivalent_voltage_pu is not None and not isinstance(
            self.equivalent_voltage_pu, PhasorValue
        ):
            raise TypeError("equivalent_voltage_pu must be a PhasorValue or None.")
        for name in (
            "voltage_factor",
            "fault_duration_s",
            "frequency_hz",
            "first_pole_contact_separation_time_s",
        ):
            value = getattr(self, name)
            if value is not None:
                numeric = _finite(value, name, nonnegative=True)
                if numeric <= 0.0:
                    raise ValueError(f"{name} must be positive when supplied.")
                object.__setattr__(self, name, numeric)
        for name in ("base_power_mva", "base_voltage_kv", "base_current_ka"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, nonnegative=True))
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be positive.")
        object.__setattr__(
            self,
            "maximum_phase_current_ka",
            _finite(self.maximum_phase_current_ka, "maximum_phase_current_ka", nonnegative=True),
        )
        if not isinstance(self.phase_quantities, tuple) or tuple(
            item.phase for item in self.phase_quantities
        ) != ("A", "B", "C"):
            raise ValueError("phase_quantities must contain A, B and C in canonical order.")
        if any(not isinstance(item, PhaseQuantityResult) for item in self.phase_quantities):
            raise TypeError("phase_quantities contains an invalid record.")
        if not isinstance(self.sequence_quantities, tuple) or any(
            not isinstance(item, SequenceQuantityResult) for item in self.sequence_quantities
        ):
            raise TypeError("sequence_quantities must be a tuple of SequenceQuantityResult.")
        for name, expected_type in (
            ("iec_quantities", IECQuantityResult),
            ("correction_factors", CorrectionFactorResult),
            ("diagnostics", DiagnosticResult),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, expected_type) for item in values
            ):
                raise TypeError(f"{name} must be a tuple of {expected_type.__name__} values.")
        for name in ("distance_from_km", "distance_to_km"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite(value, name, nonnegative=True))


@dataclass(frozen=True, slots=True)
class SourceContributionResult:
    fault_id: str
    scenario_id: str
    source_id: str
    source_name: str
    source_family: str
    source_mode: str
    domain: str
    component: str
    current_ka: PhasorValue
    model_reference: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "fault_id",
            "scenario_id",
            "source_id",
            "source_name",
            "source_family",
            "source_mode",
            "domain",
            "component",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.domain not in {"phase", "sequence"}:
            raise ValueError("domain must be phase or sequence.")
        if not isinstance(self.current_ka, PhasorValue):
            raise TypeError("current_ka must be a PhasorValue.")
        if self.model_reference is not None:
            object.__setattr__(
                self, "model_reference", _text(self.model_reference, "model_reference")
            )


@dataclass(frozen=True, slots=True)
class SourceContributionBalanceResult:
    fault_id: str
    scenario_id: str
    domain: str
    component: str
    residual_ka: float
    method_id: str

    def __post_init__(self) -> None:
        for name in ("fault_id", "scenario_id", "component", "method_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.domain not in {"phase", "sequence"}:
            raise ValueError("domain must be phase or sequence.")
        object.__setattr__(
            self, "residual_ka", _finite(self.residual_ka, "residual_ka", nonnegative=True)
        )


@dataclass(frozen=True, slots=True)
class BranchCurrentResult:
    fault_id: str
    branch_id: str
    branch_name: str
    equipment_type: str
    terminal: str
    bus_id: str
    bus_name: str
    phase: str
    current_pu: PhasorValue
    current_ka: PhasorValue
    direction_convention: str = "current_into_branch"

    def __post_init__(self) -> None:
        for name in (
            "fault_id",
            "branch_id",
            "branch_name",
            "equipment_type",
            "terminal",
            "bus_id",
            "bus_name",
            "direction_convention",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.phase not in {"A", "B", "C"}:
            raise ValueError("phase must be A, B or C.")
        for name in ("current_pu", "current_ka"):
            if not isinstance(getattr(self, name), PhasorValue):
                raise TypeError(f"{name} must be a PhasorValue.")


@dataclass(frozen=True, slots=True)
class StudyMetadata:
    study_id: str
    project_name: str
    study_name: str
    network_name: str
    generated_at: datetime
    standard_edition: str | None = None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("study_id", "project_name", "study_name", "network_name", "schema_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.standard_edition is not None:
            object.__setattr__(
                self, "standard_edition", _text(self.standard_edition, "standard_edition")
            )
        if not isinstance(self.generated_at, datetime) or self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be a timezone-aware datetime.")

    @property
    def generated_at_utc(self) -> str:
        return self.generated_at.astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class EngineeringStudyReport:
    metadata: StudyMetadata
    faults: tuple[FaultResultRecord, ...]
    source_contributions: tuple[SourceContributionResult, ...] = ()
    source_balance_residuals: tuple[SourceContributionBalanceResult, ...] = ()
    branch_currents: tuple[BranchCurrentResult, ...] = ()
    diagnostics: tuple[DiagnosticResult, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, StudyMetadata):
            raise TypeError("metadata must be a StudyMetadata value.")
        for name, expected in (
            ("faults", FaultResultRecord),
            ("source_contributions", SourceContributionResult),
            ("source_balance_residuals", SourceContributionBalanceResult),
            ("branch_currents", BranchCurrentResult),
            ("diagnostics", DiagnosticResult),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, expected) for item in values
            ):
                raise TypeError(f"{name} must be a tuple of {expected.__name__} values.")
        fault_ids = {fault.fault_id for fault in self.faults}
        if len(fault_ids) != len(self.faults):
            raise ValueError("fault IDs must be unique within one report.")
        source_keys = [
            (item.fault_id, item.scenario_id, item.source_id, item.domain, item.component)
            for item in self.source_contributions
        ]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("Source contribution rows cannot be duplicated.")
        balance_keys = [
            (item.fault_id, item.scenario_id, item.domain, item.component)
            for item in self.source_balance_residuals
        ]
        if len(balance_keys) != len(set(balance_keys)):
            raise ValueError("Source contribution balance rows cannot be duplicated.")
        linked_ids = {
            item.fault_id
            for item in (
                *self.source_contributions,
                *self.source_balance_residuals,
                *self.branch_currents,
            )
        }
        orphaned_ids = linked_ids - fault_ids
        if orphaned_ids:
            raise ValueError(
                "Source contribution and branch-current rows must reference a fault in the report; "
                f"orphaned fault IDs: {', '.join(sorted(orphaned_ids))}."
            )
        for name in ("assumptions", "limitations"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be a tuple of strings.")
            normalized = tuple(_text(value, name) for value in values)
            object.__setattr__(self, name, normalized)
