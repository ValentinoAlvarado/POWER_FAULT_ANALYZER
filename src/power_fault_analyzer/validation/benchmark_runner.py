"""Run production short-circuit calculations against closed-form reference data."""

from __future__ import annotations

import math
from collections.abc import Mapping

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.validation.models import (
    BenchmarkCaseResult,
    BenchmarkSummary,
    QuantityComparison,
    ValidationStatus,
)
from power_fault_analyzer.validation.reference_cases import (
    AnalyticalReferenceCase,
    load_reference_dataset,
    solve_reference_case,
)


def _comparison(
    case_id: str,
    quantity: str,
    unit: str,
    expected: complex,
    actual: complex,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> QuantityComparison:
    error = abs(complex(actual) - complex(expected))
    scale = abs(complex(expected))
    allowed = absolute_tolerance + relative_tolerance * scale
    relative_error = error / max(scale, absolute_tolerance, 1e-30)
    return QuantityComparison(
        case_id=case_id,
        quantity=quantity,
        unit=unit,
        expected=expected,
        actual=actual,
        absolute_error=float(error),
        allowed_error=float(allowed),
        relative_error=float(relative_error),
        status=ValidationStatus.PASS if error <= allowed else ValidationStatus.FAIL,
    )


def compare_case(case: AnalyticalReferenceCase) -> BenchmarkCaseResult:
    result = solve_reference_case(case)
    tol = case.tolerances
    comparisons: list[QuantityComparison] = []
    for sequence in (SequenceType.ZERO, SequenceType.POSITIVE, SequenceType.NEGATIVE):
        expected = complex(*case.expected["sequence_currents_pu"][sequence.value])
        actual = result.sequence_currents_pu[sequence]
        comparisons.append(
            _comparison(
                case.case_id,
                f"sequence_current_{sequence.value}",
                "p.u.",
                expected,
                actual,
                tol["complex_abs_pu"],
                tol["relative"],
            )
        )
    for index, phase in enumerate("ABC"):
        comparisons.append(
            _comparison(
                case.case_id,
                f"phase_current_{phase}",
                "p.u.",
                complex(*case.expected["phase_currents_pu"][index]),
                result.phase_currents_pu[index],
                tol["complex_abs_pu"],
                tol["relative"],
            )
        )
        comparisons.append(
            _comparison(
                case.case_id,
                f"phase_current_{phase}",
                "kA",
                complex(*case.expected["phase_currents_ka"][index]),
                result.phase_currents_ka[index],
                tol["complex_abs_ka"],
                tol["relative"],
            )
        )
    comparisons.append(
        _comparison(
            case.case_id,
            "ground_current",
            "p.u.",
            complex(*case.expected["ground_current_pu"]),
            result.ground_current_pu,
            tol["complex_abs_pu"],
            tol["relative"],
        )
    )
    comparisons.append(
        _comparison(
            case.case_id,
            "base_current",
            "kA",
            float(case.expected["base_current_ka"]),
            result.base_current_ka,
            tol["scalar_abs"],
            tol["relative"],
        )
    )
    return BenchmarkCaseResult(case.case_id, case.title, tuple(comparisons))


def run_analytical_benchmarks() -> BenchmarkSummary:
    dataset_id, basis, cases = load_reference_dataset()
    return BenchmarkSummary(
        dataset_id=dataset_id,
        cases=tuple(compare_case(case) for case in cases),
        reference_basis=basis,
    )


def compare_external_values(
    *,
    expected: Mapping[str, complex | float],
    actual: Mapping[str, complex | float],
    unit_by_quantity: Mapping[str, str],
    absolute_tolerance: float = 1e-8,
    relative_tolerance: float = 1e-5,
    case_id: str = "EXTERNAL-REFERENCE",
) -> tuple[QuantityComparison, ...]:
    """Compare imported third-party result quantities without pretending a run occurred.

    The caller must supply tool/version/provenance in its surrounding benchmark manifest.
    Only keys present in both maps are compared; mismatched keys are rejected.
    """
    if set(expected) != set(actual) or set(expected) != set(unit_by_quantity):
        raise ValueError("Expected, actual, and unit maps must have identical quantity keys.")
    for name, tolerance in (
        ("absolute_tolerance", absolute_tolerance),
        ("relative_tolerance", relative_tolerance),
    ):
        if (
            isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or not math.isfinite(float(tolerance))
            or tolerance < 0.0
        ):
            raise ValueError(f"{name} must be finite and non-negative.")
    return tuple(
        _comparison(
            case_id,
            key,
            unit_by_quantity[key],
            expected[key],
            actual[key],
            absolute_tolerance,
            relative_tolerance,
        )
        for key in sorted(expected)
    )
