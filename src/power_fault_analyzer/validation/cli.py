"""Command-line entry point for reproducible ND-016 validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.validation.benchmark_runner import run_analytical_benchmarks
from power_fault_analyzer.validation.electrical_checks import audit_short_circuit_result
from power_fault_analyzer.validation.external_reference import (
    compare_external_reference_document,
    load_external_reference,
)
from power_fault_analyzer.validation.models import _json_number
from power_fault_analyzer.validation.reference_cases import (
    load_reference_dataset,
    solve_reference_case,
)
from power_fault_analyzer.validation.sensitivity import assess_scalar_parameter_sensitivity


def run_validation(external_reference_path: Path | None = None) -> dict[str, object]:
    dataset_id, basis, cases = load_reference_dataset()
    summary = run_analytical_benchmarks()
    audits = []
    for case in cases:
        result = solve_reference_case(case)
        audit = audit_short_circuit_result(result)
        audits.append(
            {
                "case_id": case.case_id,
                "passed": audit.passed,
                "checks": [
                    {
                        "check_id": item.check_id,
                        "description": item.description,
                        "passed": item.passed,
                        "residual": item.residual,
                        "tolerance": item.tolerance,
                        "unit": item.unit,
                    }
                    for item in audit.checks
                ],
            }
        )
    external_comparison: dict[str, object] = {
        "status": "not_performed",
        "reason": "No ETAP/DIgSILENT/PSS/E result file was supplied; use --external-reference.",
    }
    if external_reference_path is not None:
        document = load_external_reference(external_reference_path)
        if document["reference_dataset_id"] != dataset_id:
            raise ValueError(
                "External reference dataset_id does not match the bundled analytical dataset."
            )
        matching_case = next((case for case in cases if case.case_id == document["case_id"]), None)
        if matching_case is None:
            raise ValueError(
                f"External reference case_id '{document['case_id']}' is not in the built-in dataset."
            )
        external_result = solve_reference_case(matching_case)
        comparisons = compare_external_reference_document(document, external_result)
        external_comparison = {
            "status": "passed"
            if all(item.status.value == "pass" for item in comparisons)
            else "failed",
            "tool_name": document["tool_name"],
            "tool_version": document["tool_version"],
            "case_id": document["case_id"],
            "comparisons": [
                {
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "expected_external": _json_number(item.expected),
                    "actual_engine": _json_number(item.actual),
                    "absolute_error": item.absolute_error,
                    "allowed_error": item.allowed_error,
                    "relative_error": item.relative_error,
                    "status": item.status.value,
                }
                for item in comparisons
            ],
        }
    base_case = next(case for case in cases if case.case_id == "REF-3PH-001")
    sensitivity = assess_scalar_parameter_sensitivity(
        lambda scale: solve_reference_case(
            base_case, positive_sequence_scale=scale
        ).sequence_currents_pu[SequenceType.POSITIVE],
        parameter_name="positive-sequence Thevenin impedance scale",
    )
    return {
        "schema_version": "1.0.0",
        "dataset_id": dataset_id,
        "reference_basis": basis,
        "benchmark": summary.to_dict(),
        "electrical_audits": audits,
        "sensitivity": {
            "parameter_name": sensitivity.parameter_name,
            "passed": sensitivity.passed,
            "monotonic_magnitude": sensitivity.monotonic_magnitude,
            "converged": sensitivity.converged,
            "derivative_relative_difference": sensitivity.derivative_relative_difference,
            "points": [
                {
                    "parameter_scale": point.parameter_scale,
                    "response": _json_number(point.response),
                    "response_magnitude": point.response_magnitude,
                    "relative_change": point.relative_change,
                }
                for point in sensitivity.points
            ],
        },
        "external_tool_comparison": external_comparison,
        "iterative_convergence": {
            "status": "not_applicable_to_current_solver",
            "reason": "The validated bus-fault path uses direct sparse linear solves, not an iterative nonlinear load-flow loop. Closed-form reference comparisons and perturbation sensitivity checks are reported instead.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="POWER_FAULT_ANALYZER ND-016 validation suite")
    parser.add_argument(
        "--json", dest="json_path", type=Path, help="Write complete validation report to JSON"
    )
    parser.add_argument(
        "--external-reference",
        type=Path,
        help="Compare one matching case with a provenance-labelled third-party JSON result",
    )
    args = parser.parse_args(argv)
    report = run_validation(args.external_reference)
    benchmark = report["benchmark"]
    audits = report["electrical_audits"]
    audit_passed = all(item["passed"] for item in audits)
    sensitivity_passed = bool(report["sensitivity"]["passed"])
    external_status = report["external_tool_comparison"]["status"]
    external_passed = external_status != "failed"
    passed = bool(benchmark["passed"]) and audit_passed and sensitivity_passed and external_passed
    report["passed"] = passed
    print(
        f"ND-016 analytical benchmark: {benchmark['passed_cases']}/{benchmark['total_cases']} cases; "
        f"{benchmark['passed_comparisons']}/{benchmark['total_comparisons']} quantities passed"
    )
    print(f"Electrical audits: {sum(item['passed'] for item in audits)}/{len(audits)} cases passed")
    print(
        f"Sensitivity refinement: {'PASS' if sensitivity_passed else 'FAIL'} "
        f"(relative derivative difference={report['sensitivity']['derivative_relative_difference']:.3e})"
    )
    if external_status == "not_performed":
        print("Independent external-tool comparison: NOT PERFORMED")
    else:
        print(f"Independent external-tool comparison: {str(external_status).upper()}")
    print("Iterative convergence study: NOT APPLICABLE (direct sparse solver)")
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Report written: {args.json_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
