"""Interchange contract for independently produced electrical benchmark results."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.validation.benchmark_runner import compare_external_values
from power_fault_analyzer.validation.models import QuantityComparison

_EXTERNAL_RESULT_FIELDS: dict[str, tuple[str, str]] = {
    "sequence_current_zero_pu": ("sequence_zero", "p.u."),
    "sequence_current_positive_pu": ("sequence_positive", "p.u."),
    "sequence_current_negative_pu": ("sequence_negative", "p.u."),
    "ground_current_pu": ("ground_current_pu", "p.u."),
    "ground_current_ka": ("ground_current_ka", "kA"),
    "base_current_ka": ("base_current_ka", "kA"),
    "phase_current_A_pu": ("phase_current_A_pu", "p.u."),
    "phase_current_B_pu": ("phase_current_B_pu", "p.u."),
    "phase_current_C_pu": ("phase_current_C_pu", "p.u."),
    "phase_current_A_ka": ("phase_current_A_ka", "kA"),
    "phase_current_B_ka": ("phase_current_B_ka", "kA"),
    "phase_current_C_ka": ("phase_current_C_ka", "kA"),
    "phase_voltage_A_pu": ("phase_voltage_A_pu", "p.u."),
    "phase_voltage_B_pu": ("phase_voltage_B_pu", "p.u."),
    "phase_voltage_C_pu": ("phase_voltage_C_pu", "p.u."),
    "phase_voltage_A_kv": ("phase_voltage_A_kv", "kV"),
    "phase_voltage_B_kv": ("phase_voltage_B_kv", "kV"),
    "phase_voltage_C_kv": ("phase_voltage_C_kv", "kV"),
}


def _parse_numeric(value: object, *, name: str) -> complex | float:
    if isinstance(value, bool):
        raise TypeError(f"External quantity '{name}' cannot be boolean.")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"External quantity '{name}' must be finite.")
        return number
    if isinstance(value, dict) and set(value) == {"real", "imag"}:
        real, imag = value["real"], value["imag"]
        if any(
            isinstance(item, bool) or not isinstance(item, (int, float)) for item in (real, imag)
        ):
            raise TypeError(f"External phasor '{name}' real and imag parts must be numeric.")
        number = complex(float(real), float(imag))
        if not math.isfinite(number.real) or not math.isfinite(number.imag):
            raise ValueError(f"External phasor '{name}' must be finite.")
        return number
    raise ValueError(f"External quantity '{name}' must be a number or a real/imag phasor object.")


def load_external_reference(path: str | Path) -> dict[str, Any]:
    """Load a provenance-labelled JSON export from a third-party study tool."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "tool_name",
        "tool_version",
        "reference_dataset_id",
        "case_id",
        "quantities",
    }
    if not isinstance(payload, dict):
        raise TypeError("External reference document root must be a JSON object.")
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"External reference document is missing fields: {sorted(missing)}")
    if payload["schema_version"] != "1.0.0":
        raise ValueError("Unsupported external reference schema_version; expected 1.0.0.")
    for key in ("tool_name", "tool_version", "reference_dataset_id", "case_id"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise ValueError(f"{key} must be a non-empty string.")
    if not isinstance(payload["quantities"], dict) or not payload["quantities"]:
        raise ValueError("quantities must be a non-empty object.")
    for name, item in payload["quantities"].items():
        if not isinstance(name, str) or not name.strip() or name not in _EXTERNAL_RESULT_FIELDS:
            raise ValueError(f"Unsupported external result quantity: {name!r}.")
        if not isinstance(item, dict) or set(item) != {"value", "unit"}:
            raise ValueError(f"Quantity '{name}' must contain exactly value and unit.")
        if item["unit"] != _EXTERNAL_RESULT_FIELDS[name][1]:
            raise ValueError(
                f"Quantity '{name}' requires unit '{_EXTERNAL_RESULT_FIELDS[name][1]}'."
            )
        _parse_numeric(item["value"], name=name)
    return payload


def compare_external_reference_document(
    document: dict[str, Any],
    result: ShortCircuitResult,
    *,
    absolute_tolerance: float = 1e-8,
    relative_tolerance: float = 1e-5,
) -> tuple[QuantityComparison, ...]:
    """Compare an imported third-party result record with an actual solver result."""
    if not isinstance(result, ShortCircuitResult):
        raise TypeError("result must be a ShortCircuitResult.")
    if not isinstance(document, dict) or not isinstance(document.get("quantities"), dict):
        raise TypeError("document must be a loaded external reference object.")
    actual: dict[str, complex | float] = {
        "sequence_current_zero_pu": result.sequence_currents_pu.get(SequenceType.ZERO, 0.0j),
        "sequence_current_positive_pu": result.sequence_currents_pu.get(
            SequenceType.POSITIVE, 0.0j
        ),
        "sequence_current_negative_pu": result.sequence_currents_pu.get(
            SequenceType.NEGATIVE, 0.0j
        ),
        "ground_current_pu": result.ground_current_pu,
        "ground_current_ka": result.ground_current_ka,
        "base_current_ka": result.base_current_ka,
    }
    for index, phase in enumerate("ABC"):
        actual[f"phase_current_{phase}_pu"] = result.phase_currents_pu[index]
        actual[f"phase_current_{phase}_ka"] = result.phase_currents_ka[index]
        actual[f"phase_voltage_{phase}_pu"] = result.phase_voltages_pu[index]
        actual[f"phase_voltage_{phase}_kv"] = result.phase_voltages_kv[index]
    expected: dict[str, complex | float] = {}
    units: dict[str, str] = {}
    for name, item in document["quantities"].items():
        if name not in _EXTERNAL_RESULT_FIELDS:
            raise ValueError(f"Unsupported external result quantity: {name!r}.")
        expected[name] = _parse_numeric(item["value"], name=name)
        units[name] = item["unit"]
    engine_values = {name: actual[name] for name in expected}
    return compare_external_values(
        expected=expected,
        actual=engine_values,
        unit_by_quantity=units,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        case_id=str(document.get("case_id", "EXTERNAL-REFERENCE")),
    )
