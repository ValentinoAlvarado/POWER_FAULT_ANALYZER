"""Versioned JSON export for engineering study reports."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from power_fault_analyzer.reporting.tables import build_report_tables
from power_fault_analyzer.results.result_models import EngineeringStudyReport, PhasorValue


def _phasor(value: PhasorValue) -> dict[str, float]:
    return {
        "real": value.real,
        "imaginary": value.imaginary,
        "magnitude": value.magnitude,
        "angle_degrees": value.angle_degrees,
    }


def report_to_dict(report: EngineeringStudyReport) -> dict[str, Any]:
    """Return a JSON-ready, fully unit-labelled representation."""
    tables = build_report_tables(report)
    return {
        "schema_version": report.metadata.schema_version,
        "metadata": {
            "study_id": report.metadata.study_id,
            "project_name": report.metadata.project_name,
            "study_name": report.metadata.study_name,
            "network_name": report.metadata.network_name,
            "generated_at_utc": report.metadata.generated_at_utc,
            "standard_edition": report.metadata.standard_edition,
        },
        "faults": [
            {
                "fault_id": fault.fault_id,
                "location": {
                    "kind": fault.location_kind.value,
                    "id": fault.location_id,
                    "name": fault.location_name,
                    "line": None
                    if fault.line_branch_id is None
                    else {
                        "branch_id": fault.line_branch_id,
                        "name": fault.line_name,
                        "from_bus": fault.from_bus_name,
                        "to_bus": fault.to_bus_name,
                        "distance_from_km": fault.distance_from_km,
                        "distance_to_km": fault.distance_to_km,
                    },
                },
                "fault_type": fault.fault_type,
                "current_case": fault.current_case,
                "fault_impedance_pu": _phasor(fault.fault_impedance_pu),
                "base": {
                    "power_mva": fault.base_power_mva,
                    "voltage_kv_line_to_line": fault.base_voltage_kv,
                    "current_ka": fault.base_current_ka,
                },
                "maximum_phase_current_ka": fault.maximum_phase_current_ka,
                "iec_study_settings": {
                    "voltage_factor_c": fault.voltage_factor,
                    "equivalent_voltage_pu": (
                        _phasor(fault.equivalent_voltage_pu)
                        if fault.equivalent_voltage_pu is not None
                        else None
                    ),
                    "fault_duration_s": fault.fault_duration_s,
                    "frequency_hz": fault.frequency_hz,
                    "first_pole_contact_separation_time_s": fault.first_pole_contact_separation_time_s,
                },
                "ground_current": {
                    "pu": _phasor(fault.ground_current_pu),
                    "ka": _phasor(fault.ground_current_ka),
                },
                "phases": [
                    {
                        "phase": item.phase,
                        "current_pu": _phasor(item.current_pu),
                        "current_ka": _phasor(item.current_ka),
                        "voltage_pu": _phasor(item.voltage_pu),
                        "voltage_kv_line_to_neutral": _phasor(item.voltage_kv),
                    }
                    for item in fault.phase_quantities
                ],
                "sequences": [
                    {
                        "sequence": item.sequence,
                        "current_pu": _phasor(item.current_pu)
                        if item.current_pu is not None
                        else None,
                        "voltage_pu": _phasor(item.voltage_pu)
                        if item.voltage_pu is not None
                        else None,
                        "driving_point_impedance_pu": (
                            _phasor(item.driving_point_impedance_pu)
                            if item.driving_point_impedance_pu is not None
                            else None
                        ),
                        "prefault_voltage_pu": (
                            _phasor(item.prefault_voltage_pu)
                            if item.prefault_voltage_pu is not None
                            else None
                        ),
                    }
                    for item in fault.sequence_quantities
                ],
                "iec_quantities": [
                    {
                        "name": item.name,
                        "value": item.value,
                        "unit": item.unit,
                        "status": item.status.value,
                        "classification": item.classification,
                        "method_reference": item.method_reference,
                        "reason": item.reason,
                    }
                    for item in fault.iec_quantities
                ],
                "correction_factors": [
                    {"name": item.name, "value": item.value, "provenance": item.provenance}
                    for item in fault.correction_factors
                ],
                "diagnostics": [
                    {
                        "code": item.code,
                        "severity": item.severity,
                        "message": item.message,
                        "entity_id": item.entity_id,
                    }
                    for item in fault.diagnostics
                ],
            }
            for fault in report.faults
        ],
        "source_contributions": [
            {
                "fault_id": item.fault_id,
                "scenario_id": item.scenario_id,
                "source_id": item.source_id,
                "source_name": item.source_name,
                "source_family": item.source_family,
                "source_mode": item.source_mode,
                "domain": item.domain,
                "component": item.component,
                "current_ka": _phasor(item.current_ka),
                "model_reference": item.model_reference,
            }
            for item in report.source_contributions
        ],
        "source_balance_residuals": [
            {
                "fault_id": item.fault_id,
                "scenario_id": item.scenario_id,
                "domain": item.domain,
                "component": item.component,
                "residual_ka": item.residual_ka,
                "method_id": item.method_id,
            }
            for item in report.source_balance_residuals
        ],
        "branch_currents": [
            {
                "fault_id": item.fault_id,
                "branch_id": item.branch_id,
                "branch_name": item.branch_name,
                "equipment_type": item.equipment_type,
                "terminal": item.terminal,
                "bus_id": item.bus_id,
                "bus_name": item.bus_name,
                "phase": item.phase,
                "direction_convention": item.direction_convention,
                "current_pu": _phasor(item.current_pu),
                "current_ka": _phasor(item.current_ka),
            }
            for item in report.branch_currents
        ],
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
                "entity_id": item.entity_id,
            }
            for item in report.diagnostics
        ],
        "assumptions": list(report.assumptions),
        "limitations": list(report.limitations),
        "table_index": {name: len(rows) for name, rows in tables.items()},
    }


class JSONReportExporter:
    """Write report JSON atomically to avoid partially-written deliverables."""

    def export(self, report: EngineeringStudyReport, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report_to_dict(report), ensure_ascii=False, indent=2, allow_nan=False)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_name = stream.name
                stream.write(payload)
                stream.write("\n")
            os.replace(temporary_name, target)
        except Exception:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
            raise
        return target
