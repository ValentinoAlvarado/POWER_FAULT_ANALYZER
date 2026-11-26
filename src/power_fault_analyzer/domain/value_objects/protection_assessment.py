"""Immutable assessment results for protection coordination and equipment duty."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from power_fault_analyzer.domain.enums.protection import ProtectionAssessmentStatus
from power_fault_analyzer.domain.value_objects.diagnostic import DomainDiagnostic


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def _positive(value: float, name: str) -> float:
    result = _finite(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive.")
    return result


@dataclass(frozen=True, slots=True)
class RelaySensitivityAssessment:
    status: ProtectionAssessmentStatus
    minimum_fault_current_a: float
    relay_pickup_current_primary_a: float
    sensitivity_ratio: float
    required_sensitivity_ratio: float

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")
        for name in (
            "minimum_fault_current_a",
            "relay_pickup_current_primary_a",
            "sensitivity_ratio",
            "required_sensitivity_ratio",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class CoordinationSample:
    current_a: float
    downstream_operating_time_s: float
    downstream_clearing_time_s: float
    upstream_operating_time_s: float
    coordination_margin_s: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_a", _positive(self.current_a, "current_a"))
        for name in (
            "downstream_operating_time_s",
            "downstream_clearing_time_s",
            "upstream_operating_time_s",
        ):
            value = _finite(getattr(self, name), name)
            if value < 0.0:
                raise ValueError(f"{name} cannot be negative.")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "coordination_margin_s",
            _finite(self.coordination_margin_s, "coordination_margin_s"),
        )


@dataclass(frozen=True, slots=True)
class CoordinationAssessment:
    status: ProtectionAssessmentStatus
    minimum_required_margin_s: float
    minimum_achieved_margin_s: float | None
    critical_current_a: float | None
    samples: tuple[CoordinationSample, ...]
    diagnostics: tuple[DomainDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")
        object.__setattr__(
            self,
            "minimum_required_margin_s",
            _finite(self.minimum_required_margin_s, "minimum_required_margin_s"),
        )
        if self.minimum_required_margin_s < 0.0:
            raise ValueError("minimum_required_margin_s cannot be negative.")
        for name in ("minimum_achieved_margin_s", "critical_current_a"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite(value, name))
        if not isinstance(self.samples, tuple) or any(
            not isinstance(item, CoordinationSample) for item in self.samples
        ):
            raise TypeError("samples must be a tuple of CoordinationSample values.")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of DomainDiagnostic values.")


@dataclass(frozen=True, slots=True)
class EquipmentDutyAssessment:
    equipment_id: UUID
    status: ProtectionAssessmentStatus
    checks: Mapping[str, ProtectionAssessmentStatus]
    margins: Mapping[str, float]
    diagnostics: tuple[DomainDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.equipment_id, UUID):
            raise TypeError("equipment_id must be a UUID.")
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")
        if not isinstance(self.checks, Mapping) or any(
            not isinstance(key, str) or not isinstance(value, ProtectionAssessmentStatus)
            for key, value in self.checks.items()
        ):
            raise TypeError("checks must map string names to ProtectionAssessmentStatus values.")
        if not isinstance(self.margins, Mapping):
            raise TypeError("margins must be a mapping.")
        copied_margins = {
            key: _finite(value, f"margin {key}") for key, value in self.margins.items()
        }
        object.__setattr__(self, "checks", MappingProxyType(dict(self.checks)))
        object.__setattr__(self, "margins", MappingProxyType(copied_margins))
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of DomainDiagnostic values.")


@dataclass(frozen=True, slots=True)
class ConductorThermalAssessment:
    status: ProtectionAssessmentStatus
    actual_i2t_a2s: float
    withstand_i2t_a2s: float
    utilization: float
    fault_duration_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")
        for name in (
            "actual_i2t_a2s",
            "withstand_i2t_a2s",
            "utilization",
            "fault_duration_s",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
