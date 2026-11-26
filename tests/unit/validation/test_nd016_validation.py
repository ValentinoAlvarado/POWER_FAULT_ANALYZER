"""Reproducible analytical benchmarks, dimensional audits and sensitivity checks."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.validation.benchmark_runner import (
    compare_external_values,
    run_analytical_benchmarks,
)
from power_fault_analyzer.validation.electrical_checks import audit_short_circuit_result
from power_fault_analyzer.validation.external_reference import (
    compare_external_reference_document,
    load_external_reference,
)
from power_fault_analyzer.validation.reference_cases import (
    load_reference_dataset,
    solve_reference_case,
)
from power_fault_analyzer.validation.sensitivity import assess_scalar_parameter_sensitivity


def test_reference_dataset_contains_four_canonical_fault_types():
    dataset_id, basis, cases = load_reference_dataset()
    assert dataset_id == "PFA-ND016-ANALYTICAL-FAULTS-001"
    assert "not IEC 60909 normative" in basis
    assert {case.fault_type.value for case in cases} == {
        "three_phase",
        "single_line_to_ground",
        "line_to_line",
        "double_line_to_ground",
    }


def test_reference_case_ids_are_stable_and_unique():
    _, _, cases = load_reference_dataset()
    ids = [case.case_id for case in cases]
    assert len(ids) == len(set(ids)) == 4


def test_all_analytic_reference_quantities_match_production_solver():
    summary = run_analytical_benchmarks()
    assert summary.passed
    assert summary.passed_cases == 4
    assert summary.total_comparisons == 44
    assert summary.passed_comparisons == 44
    assert summary.failed_comparisons == 0


@pytest.mark.parametrize(
    "case_id",
    [
        "REF-3PH-001",
        "REF-SLG-001",
        "REF-LL-001",
        "REF-DLG-001",
    ],
)
def test_unit_base_and_fault_boundary_audits_pass(case_id):
    _, _, cases = load_reference_dataset()
    case = next(item for item in cases if item.case_id == case_id)
    audit = audit_short_circuit_result(solve_reference_case(case))
    assert audit.passed
    assert audit.failures == ()
    assert {
        "BASE-CURRENT",
        "PHASE-CURRENT-BASE",
        "PHASE-VOLTAGE-BASE",
        "SEQUENCE-PHASE-CONSISTENCY",
        "GROUND-CURRENT",
    }.issubset({item.check_id for item in audit.checks})


def test_electrical_audit_detects_inconsistent_base_current():
    _, _, cases = load_reference_dataset()
    result = solve_reference_case(cases[0])
    corrupted = replace(result, base_current_ka=result.base_current_ka * 1.02)
    audit = audit_short_circuit_result(corrupted)
    assert not audit.passed
    assert "BASE-CURRENT" in {item.check_id for item in audit.failures}


def test_electrical_audit_detects_phase_current_unit_mismatch():
    _, _, cases = load_reference_dataset()
    result = solve_reference_case(cases[0])
    wrong = (result.phase_currents_ka[0] * 1.01, *result.phase_currents_ka[1:])
    audit = audit_short_circuit_result(replace(result, phase_currents_ka=wrong))
    assert not audit.passed
    assert "PHASE-CURRENT-BASE" in {item.check_id for item in audit.failures}


def test_sensitivity_study_uses_solver_response_and_refines_derivative():
    _, _, cases = load_reference_dataset()
    case = next(item for item in cases if item.case_id == "REF-3PH-001")
    sensitivity = assess_scalar_parameter_sensitivity(
        lambda scale: solve_reference_case(
            case, positive_sequence_scale=scale
        ).sequence_currents_pu[SequenceType.POSITIVE],
        parameter_name="positive-sequence Thevenin impedance scale",
    )
    assert sensitivity.passed
    assert sensitivity.monotonic_magnitude
    assert sensitivity.converged
    assert len(sensitivity.points) == 5


def test_sensitivity_flags_non_monotonic_response():
    assessment = assess_scalar_parameter_sensitivity(
        lambda scale: complex(1.0 + (scale - 1.0) ** 2),
        parameter_name="test parameter",
    )
    assert not assessment.monotonic_magnitude
    assert not assessment.passed


@pytest.mark.parametrize(
    "scales",
    [
        (0.9, 1.0),
        (0.9, 1.1, 1.0),
        (0.0, 0.9, 1.0),
    ],
)
def test_sensitivity_rejects_invalid_scale_sweep(scales):
    with pytest.raises(ValueError):
        assess_scalar_parameter_sensitivity(
            lambda scale: complex(scale), parameter_name="invalid", scales=scales
        )


def test_external_reference_document_loads_with_tool_provenance(tmp_path):
    source = {
        "schema_version": "1.0.0",
        "tool_name": "IndependentStudyTool",
        "tool_version": "2026.1",
        "reference_dataset_id": "PFA-ND016-ANALYTICAL-FAULTS-001",
        "case_id": "REF-3PH-001",
        "quantities": {"phase_current_A_ka": {"value": 12.5, "unit": "kA"}},
    }
    path = tmp_path / "external.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    assert load_external_reference(path) == source


def test_external_reference_rejects_missing_provenance(tmp_path):
    path = tmp_path / "external.json"
    path.write_text(json.dumps({"schema_version": "1.0.0", "quantities": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        load_external_reference(path)


def test_external_result_comparator_handles_complex_values_and_units():
    comparisons = compare_external_values(
        expected={"ia": 10.0 + 2.0j, "ib": 5.0},
        actual={"ia": 10.0 + 2.0j, "ib": 5.0000001},
        unit_by_quantity={"ia": "kA", "ib": "kA"},
    )
    assert len(comparisons) == 2
    assert all(item.status.value == "pass" for item in comparisons)


def test_external_result_comparator_rejects_quantity_key_mismatch():
    with pytest.raises(ValueError, match="identical quantity keys"):
        compare_external_values(
            expected={"ia": 1.0}, actual={"ib": 1.0}, unit_by_quantity={"ia": "kA"}
        )


def test_external_result_comparator_detects_out_of_tolerance_difference():
    comparisons = compare_external_values(
        expected={"ik": 10.0},
        actual={"ik": 10.2},
        unit_by_quantity={"ik": "kA"},
        absolute_tolerance=1e-6,
        relative_tolerance=1e-4,
    )
    assert comparisons[0].status.value == "fail"


def test_solver_positive_sequence_impedance_perturbation_changes_actual_solution():
    _, _, cases = load_reference_dataset()
    case = next(item for item in cases if item.case_id == "REF-3PH-001")
    base = solve_reference_case(case)
    increased = solve_reference_case(case, positive_sequence_scale=1.05)
    assert abs(
        increased.sequence_currents_pu[
            next(
                sequence
                for sequence in increased.sequence_currents_pu
                if sequence.value == "positive"
            )
        ]
    ) < abs(
        base.sequence_currents_pu[
            next(sequence for sequence in base.sequence_currents_pu if sequence.value == "positive")
        ]
    )


def test_loaded_external_reference_compares_against_matching_engine_results(tmp_path):
    _, _, cases = load_reference_dataset()
    case = next(item for item in cases if item.case_id == "REF-3PH-001")
    result = solve_reference_case(case)
    document = {
        "schema_version": "1.0.0",
        "tool_name": "IndependentStudyTool",
        "tool_version": "2026.1",
        "reference_dataset_id": "PFA-ND016-ANALYTICAL-FAULTS-001",
        "case_id": case.case_id,
        "quantities": {
            "sequence_current_positive_pu": {
                "value": {
                    "real": result.sequence_currents_pu[SequenceType.POSITIVE].real,
                    "imag": result.sequence_currents_pu[SequenceType.POSITIVE].imag,
                },
                "unit": "p.u.",
            },
            "base_current_ka": {"value": result.base_current_ka, "unit": "kA"},
        },
    }
    path = tmp_path / "external.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    loaded = load_external_reference(path)
    comparisons = compare_external_reference_document(loaded, result)
    assert len(comparisons) == 2
    assert all(item.status.value == "pass" for item in comparisons)


def test_external_reference_rejects_wrong_unit(tmp_path):
    document = {
        "schema_version": "1.0.0",
        "tool_name": "Tool",
        "tool_version": "1.0",
        "reference_dataset_id": "PFA-ND016-ANALYTICAL-FAULTS-001",
        "case_id": "REF-3PH-001",
        "quantities": {"base_current_ka": {"value": 4.0, "unit": "A"}},
    }
    path = tmp_path / "external.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="requires unit"):
        load_external_reference(path)


def test_cli_accepts_matching_external_reference_and_reports_pass(tmp_path, capsys):
    from power_fault_analyzer.validation.cli import main

    _, _, cases = load_reference_dataset()
    case = next(item for item in cases if item.case_id == "REF-3PH-001")
    result = solve_reference_case(case)
    value = result.sequence_currents_pu[SequenceType.POSITIVE]
    document = {
        "schema_version": "1.0.0",
        "tool_name": "IndependentStudyFixture",
        "tool_version": "fixture-1",
        "reference_dataset_id": "PFA-ND016-ANALYTICAL-FAULTS-001",
        "case_id": case.case_id,
        "quantities": {
            "sequence_current_positive_pu": {
                "value": {"real": value.real, "imag": value.imag},
                "unit": "p.u.",
            }
        },
    }
    external_path = tmp_path / "tool-result.json"
    external_path.write_text(json.dumps(document), encoding="utf-8")
    output_path = tmp_path / "validation.json"
    exit_code = main(["--external-reference", str(external_path), "--json", str(output_path)])
    assert exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["external_tool_comparison"]["status"] == "passed"
    assert "PASSED" in capsys.readouterr().out


def test_reference_case_rejects_non_positive_impedance_scale():
    _, _, cases = load_reference_dataset()
    with pytest.raises(ValueError, match="must be finite and positive"):
        solve_reference_case(cases[0], positive_sequence_scale=0.0)


def test_external_reference_rejects_boolean_scalar_as_invalid_type(tmp_path):
    document = {
        "schema_version": "1.0.0",
        "tool_name": "Tool",
        "tool_version": "1.0",
        "reference_dataset_id": "PFA-ND016-ANALYTICAL-FAULTS-001",
        "case_id": "REF-3PH-001",
        "quantities": {"phase_current_A_ka": {"value": True, "unit": "kA"}},
    }
    path = tmp_path / "boolean-scalar.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(TypeError, match="cannot be boolean"):
        load_external_reference(path)


def test_external_reference_rejects_non_object_json_root_as_invalid_type(tmp_path):
    path = tmp_path / "non-object-root.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    with pytest.raises(TypeError, match="root must be a JSON object"):
        load_external_reference(path)


def test_external_reference_rejects_boolean_phasor_component_as_invalid_type(tmp_path):
    document = {
        "schema_version": "1.0.0",
        "tool_name": "Tool",
        "tool_version": "1.0",
        "reference_dataset_id": "PFA-ND016-ANALYTICAL-FAULTS-001",
        "case_id": "REF-3PH-001",
        "quantities": {
            "sequence_current_positive_pu": {"value": {"real": True, "imag": 0.0}, "unit": "p.u."}
        },
    }
    path = tmp_path / "boolean-phasor.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(TypeError, match="real and imag parts must be numeric"):
        load_external_reference(path)
