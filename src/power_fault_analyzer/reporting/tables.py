"""Tabular projections shared by CSV and Excel report exporters."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from power_fault_analyzer.results.result_models import EngineeringStudyReport, PhasorValue

REPORT_TABLE_HEADERS: dict[str, tuple[str, ...]] = {
    "Study": ("field", "value"),
    "Faults": (
        "fault_id",
        "location_kind",
        "location_id",
        "location_name",
        "fault_type",
        "current_case",
        "fault_impedance_pu_real",
        "fault_impedance_pu_imaginary",
        "base_power_mva",
        "base_voltage_kv_ll",
        "base_current_ka",
        "maximum_phase_current_ka",
        "voltage_factor_c",
        "equivalent_voltage_pu_real",
        "equivalent_voltage_pu_imaginary",
        "fault_duration_s",
        "frequency_hz",
        "first_pole_contact_separation_time_s",
        "ground_current_pu_magnitude",
        "ground_current_ka_magnitude",
        "line_branch_id",
        "line_name",
        "from_bus_name",
        "to_bus_name",
        "distance_from_km",
        "distance_to_km",
    ),
    "Phases": (
        "fault_id",
        "phase",
        "current_pu_real",
        "current_pu_imaginary",
        "current_pu_magnitude",
        "current_pu_angle_deg",
        "current_ka_real",
        "current_ka_imaginary",
        "current_ka_magnitude",
        "current_ka_angle_deg",
        "voltage_pu_real",
        "voltage_pu_imaginary",
        "voltage_pu_magnitude",
        "voltage_pu_angle_deg",
        "voltage_kv_ln_real",
        "voltage_kv_ln_imaginary",
        "voltage_kv_ln_magnitude",
        "voltage_kv_ln_angle_deg",
    ),
    "Sequences": (
        "fault_id",
        "sequence",
        "current_pu_real",
        "current_pu_imaginary",
        "current_pu_magnitude",
        "current_pu_angle_deg",
        "voltage_pu_real",
        "voltage_pu_imaginary",
        "voltage_pu_magnitude",
        "voltage_pu_angle_deg",
        "z_th_pu_real",
        "z_th_pu_imaginary",
        "z_th_pu_magnitude",
        "z_th_pu_angle_deg",
        "prefault_voltage_pu_real",
        "prefault_voltage_pu_imaginary",
        "prefault_voltage_pu_magnitude",
        "prefault_voltage_pu_angle_deg",
    ),
    "IEC Quantities": (
        "fault_id",
        "quantity",
        "value",
        "unit",
        "status",
        "classification",
        "method_reference",
        "reason",
    ),
    "Sources": (
        "fault_id",
        "scenario_id",
        "source_id",
        "source_name",
        "source_family",
        "source_mode",
        "domain",
        "component",
        "unit",
        "model_reference",
        "current_ka_real",
        "current_ka_imaginary",
        "current_ka_magnitude",
        "current_ka_angle_deg",
    ),
    "Source Balance": (
        "fault_id",
        "scenario_id",
        "domain",
        "component",
        "residual_ka",
        "method_id",
    ),
    "Branches": (
        "fault_id",
        "branch_id",
        "branch_name",
        "equipment_type",
        "terminal",
        "bus_id",
        "bus_name",
        "phase",
        "direction_convention",
        "unit",
        "current_pu_real",
        "current_pu_imaginary",
        "current_pu_magnitude",
        "current_pu_angle_deg",
        "current_ka_real",
        "current_ka_imaginary",
        "current_ka_magnitude",
        "current_ka_angle_deg",
    ),
    "Corrections": ("fault_id", "factor", "value", "provenance"),
    "Diagnostics": ("code", "severity", "message", "entity_id"),
}


def _phasor_columns(prefix: str, value: PhasorValue | None) -> dict[str, float | None]:
    if value is None:
        return {
            f"{prefix}_real": None,
            f"{prefix}_imaginary": None,
            f"{prefix}_magnitude": None,
            f"{prefix}_angle_deg": None,
        }
    return {
        f"{prefix}_real": value.real,
        f"{prefix}_imaginary": value.imaginary,
        f"{prefix}_magnitude": value.magnitude,
        f"{prefix}_angle_deg": value.angle_degrees,
    }


def spreadsheet_safe_value(value: Any) -> Any:
    """Keep untrusted text from being interpreted as a spreadsheet formula.

    Numeric values remain numeric. Text whose first non-whitespace character is
    one of Excel's formula introducers is prefixed with an apostrophe in CSV/XLSX.
    JSON remains unchanged because it is not a spreadsheet execution format.
    """
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def build_report_tables(report: EngineeringStudyReport) -> OrderedDict[str, list[dict[str, Any]]]:
    """Convert an immutable report to rectangular, unit-labelled tables."""
    if not isinstance(report, EngineeringStudyReport):
        raise TypeError("report must be an EngineeringStudyReport.")

    metadata = report.metadata
    study_rows = [
        {"field": "study_id", "value": metadata.study_id},
        {"field": "project_name", "value": metadata.project_name},
        {"field": "study_name", "value": metadata.study_name},
        {"field": "network_name", "value": metadata.network_name},
        {"field": "generated_at_utc", "value": metadata.generated_at_utc},
        {"field": "standard_edition", "value": metadata.standard_edition or "not specified"},
        {"field": "schema_version", "value": metadata.schema_version},
        {"field": "fault_count", "value": len(report.faults)},
        {"field": "source_contribution_rows", "value": len(report.source_contributions)},
        {"field": "branch_current_rows", "value": len(report.branch_currents)},
    ]
    study_rows.extend(
        {"field": f"assumption_{index + 1}", "value": value}
        for index, value in enumerate(report.assumptions)
    )
    study_rows.extend(
        {"field": f"limitation_{index + 1}", "value": value}
        for index, value in enumerate(report.limitations)
    )

    fault_rows: list[dict[str, Any]] = []
    phase_rows: list[dict[str, Any]] = []
    sequence_rows: list[dict[str, Any]] = []
    quantity_rows: list[dict[str, Any]] = []
    correction_rows: list[dict[str, Any]] = []
    for fault in report.faults:
        fault_rows.append(
            {
                "fault_id": fault.fault_id,
                "location_kind": fault.location_kind.value,
                "location_id": fault.location_id,
                "location_name": fault.location_name,
                "fault_type": fault.fault_type,
                "current_case": fault.current_case or "not specified",
                "fault_impedance_pu_real": fault.fault_impedance_pu.real,
                "fault_impedance_pu_imaginary": fault.fault_impedance_pu.imaginary,
                "base_power_mva": fault.base_power_mva,
                "base_voltage_kv_ll": fault.base_voltage_kv,
                "base_current_ka": fault.base_current_ka,
                "maximum_phase_current_ka": fault.maximum_phase_current_ka,
                "voltage_factor_c": fault.voltage_factor,
                "equivalent_voltage_pu_real": (
                    fault.equivalent_voltage_pu.real
                    if fault.equivalent_voltage_pu is not None
                    else None
                ),
                "equivalent_voltage_pu_imaginary": (
                    fault.equivalent_voltage_pu.imaginary
                    if fault.equivalent_voltage_pu is not None
                    else None
                ),
                "fault_duration_s": fault.fault_duration_s,
                "frequency_hz": fault.frequency_hz,
                "first_pole_contact_separation_time_s": fault.first_pole_contact_separation_time_s,
                "ground_current_pu_magnitude": fault.ground_current_pu.magnitude,
                "ground_current_ka_magnitude": fault.ground_current_ka.magnitude,
                "line_branch_id": fault.line_branch_id or "",
                "line_name": fault.line_name or "",
                "from_bus_name": fault.from_bus_name or "",
                "to_bus_name": fault.to_bus_name or "",
                "distance_from_km": fault.distance_from_km,
                "distance_to_km": fault.distance_to_km,
            }
        )
        for phase in fault.phase_quantities:
            row = {"fault_id": fault.fault_id, "phase": phase.phase}
            row.update(_phasor_columns("current_pu", phase.current_pu))
            row.update(_phasor_columns("current_ka", phase.current_ka))
            row.update(_phasor_columns("voltage_pu", phase.voltage_pu))
            row.update(_phasor_columns("voltage_kv_ln", phase.voltage_kv))
            phase_rows.append(row)
        for sequence in fault.sequence_quantities:
            row = {"fault_id": fault.fault_id, "sequence": sequence.sequence}
            row.update(_phasor_columns("current_pu", sequence.current_pu))
            row.update(_phasor_columns("voltage_pu", sequence.voltage_pu))
            row.update(_phasor_columns("z_th_pu", sequence.driving_point_impedance_pu))
            row.update(_phasor_columns("prefault_voltage_pu", sequence.prefault_voltage_pu))
            sequence_rows.append(row)
        for quantity in fault.iec_quantities:
            quantity_rows.append(
                {
                    "fault_id": fault.fault_id,
                    "quantity": quantity.name,
                    "value": quantity.value,
                    "unit": quantity.unit,
                    "status": quantity.status.value,
                    "classification": quantity.classification,
                    "method_reference": quantity.method_reference or "",
                    "reason": quantity.reason or "",
                }
            )
        for factor in fault.correction_factors:
            correction_rows.append(
                {
                    "fault_id": fault.fault_id,
                    "factor": factor.name,
                    "value": factor.value,
                    "provenance": factor.provenance,
                }
            )

    source_rows: list[dict[str, Any]] = []
    for item in report.source_contributions:
        row = {
            "fault_id": item.fault_id,
            "scenario_id": item.scenario_id,
            "source_id": item.source_id,
            "source_name": item.source_name,
            "source_family": item.source_family,
            "source_mode": item.source_mode,
            "domain": item.domain,
            "component": item.component,
            "unit": "kA",
            "model_reference": item.model_reference or "",
        }
        row.update(_phasor_columns("current_ka", item.current_ka))
        source_rows.append(row)

    source_balance_rows = [
        {
            "fault_id": item.fault_id,
            "scenario_id": item.scenario_id,
            "domain": item.domain,
            "component": item.component,
            "residual_ka": item.residual_ka,
            "method_id": item.method_id,
        }
        for item in report.source_balance_residuals
    ]

    branch_rows: list[dict[str, Any]] = []
    for item in report.branch_currents:
        row = {
            "fault_id": item.fault_id,
            "branch_id": item.branch_id,
            "branch_name": item.branch_name,
            "equipment_type": item.equipment_type,
            "terminal": item.terminal,
            "bus_id": item.bus_id,
            "bus_name": item.bus_name,
            "phase": item.phase,
            "direction_convention": item.direction_convention,
            "unit": "kA",
        }
        row.update(_phasor_columns("current_pu", item.current_pu))
        row.update(_phasor_columns("current_ka", item.current_ka))
        branch_rows.append(row)

    diagnostic_rows = [
        {
            "code": item.code,
            "severity": item.severity,
            "message": item.message,
            "entity_id": item.entity_id or "",
        }
        for item in report.diagnostics
    ]
    return OrderedDict(
        (
            ("Study", study_rows),
            ("Faults", fault_rows),
            ("Phases", phase_rows),
            ("Sequences", sequence_rows),
            ("IEC Quantities", quantity_rows),
            ("Sources", source_rows),
            ("Source Balance", source_balance_rows),
            ("Branches", branch_rows),
            ("Corrections", correction_rows),
            ("Diagnostics", diagnostic_rows),
        )
    )
