"""Immutable records used by analytical validation and external comparisons."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class ValidationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_COMPARABLE = "not_comparable"


@dataclass(frozen=True, slots=True)
class QuantityTolerance:
    absolute: float
    relative: float

    def __post_init__(self) -> None:
        for name in ("absolute", "relative"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} tolerance must be numeric.")
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"{name} tolerance must be finite and non-negative.")
            object.__setattr__(self, name, float(value))


@dataclass(frozen=True, slots=True)
class QuantityComparison:
    case_id: str
    quantity: str
    unit: str
    expected: complex | float
    actual: complex | float
    absolute_error: float
    allowed_error: float
    relative_error: float
    status: ValidationStatus


@dataclass(frozen=True, slots=True)
class BenchmarkCaseResult:
    case_id: str
    title: str
    comparisons: tuple[QuantityComparison, ...]

    @property
    def passed(self) -> bool:
        return bool(self.comparisons) and all(
            item.status is ValidationStatus.PASS for item in self.comparisons
        )


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    dataset_id: str
    cases: tuple[BenchmarkCaseResult, ...]
    reference_basis: str

    @property
    def total_comparisons(self) -> int:
        return sum(len(case.comparisons) for case in self.cases)

    @property
    def passed_comparisons(self) -> int:
        return sum(
            item.status is ValidationStatus.PASS for case in self.cases for item in case.comparisons
        )

    @property
    def failed_comparisons(self) -> int:
        return self.total_comparisons - self.passed_comparisons

    @property
    def passed_cases(self) -> int:
        return sum(case.passed for case in self.cases)

    @property
    def passed(self) -> bool:
        return bool(self.cases) and self.failed_comparisons == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "reference_basis": self.reference_basis,
            "passed": self.passed,
            "passed_cases": self.passed_cases,
            "total_cases": len(self.cases),
            "passed_comparisons": self.passed_comparisons,
            "failed_comparisons": self.failed_comparisons,
            "total_comparisons": self.total_comparisons,
            "cases": [
                {
                    "case_id": case.case_id,
                    "title": case.title,
                    "passed": case.passed,
                    "comparisons": [
                        {
                            "quantity": item.quantity,
                            "unit": item.unit,
                            "expected": _json_number(item.expected),
                            "actual": _json_number(item.actual),
                            "absolute_error": item.absolute_error,
                            "allowed_error": item.allowed_error,
                            "relative_error": item.relative_error,
                            "status": item.status.value,
                        }
                        for item in case.comparisons
                    ],
                }
                for case in self.cases
            ],
        }


def _json_number(value: complex) -> object:
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    return float(value)


@dataclass(frozen=True, slots=True)
class AuditCheck:
    check_id: str
    description: str
    passed: bool
    residual: float
    tolerance: float
    unit: str


@dataclass(frozen=True, slots=True)
class ElectricalAudit:
    checks: tuple[AuditCheck, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(item.passed for item in self.checks)

    @property
    def failures(self) -> tuple[AuditCheck, ...]:
        return tuple(item for item in self.checks if not item.passed)


@dataclass(frozen=True, slots=True)
class SensitivityPoint:
    parameter_scale: float
    response: complex
    response_magnitude: float
    relative_change: float


@dataclass(frozen=True, slots=True)
class SensitivityAssessment:
    parameter_name: str
    points: tuple[SensitivityPoint, ...]
    derivative_coarse: complex
    derivative_fine: complex
    derivative_relative_difference: float
    monotonic_magnitude: bool
    converged: bool

    @property
    def passed(self) -> bool:
        return self.monotonic_magnitude and self.converged
