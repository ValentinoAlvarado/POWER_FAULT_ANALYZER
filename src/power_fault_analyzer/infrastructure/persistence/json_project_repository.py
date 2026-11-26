"""Atomic JSON persistence for local desktop project workspaces."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.projects.models import (
    Project,
    ProjectStudyRun,
    TheveninStudySettings,
)


class ProjectFileError(ValueError):
    """Raised when a project file cannot be parsed or has an unsupported schema."""


class JSONProjectRepository:
    """Persist a complete project and its numerical study history in one ``.pfa`` file."""

    SCHEMA_VERSION = "1.0"

    def load(self, path: str | Path) -> Project:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectFileError(f"Cannot read project file '{source}': {exc}") from exc
        if not isinstance(payload, dict):
            raise ProjectFileError("Project document root must be a JSON object.")
        if payload.get("schema_version") != self.SCHEMA_VERSION:
            raise ProjectFileError(
                f"Unsupported project schema {payload.get('schema_version')!r}; "
                f"expected {self.SCHEMA_VERSION!r}."
            )
        try:
            project_payload = payload["project"]
            settings = _settings_from_dict(project_payload["study_settings"])
            history = tuple(
                _run_from_dict(item) for item in project_payload.get("study_history", [])
            )
            return Project(
                project_id=UUID(project_payload["project_id"]),
                name=project_payload["name"],
                description=project_payload.get("description", ""),
                created_at=datetime.fromisoformat(project_payload["created_at"]),
                modified_at=datetime.fromisoformat(project_payload["modified_at"]),
                study_settings=settings,
                study_history=history,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjectFileError(f"Invalid project document '{source}': {exc}") from exc

    def save(self, project: Project, path: str | Path) -> Path:
        if not isinstance(project, Project):
            raise TypeError("project must be a Project aggregate.")
        target = Path(path)
        if target.suffix.lower() != ".pfa":
            target = target.with_suffix(".pfa")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "application": "POWER_FAULT_ANALYZER",
            "project": {
                "project_id": str(project.project_id),
                "name": project.name,
                "description": project.description,
                "created_at": project.created_at.isoformat(),
                "modified_at": project.modified_at.isoformat(),
                "study_settings": _settings_to_dict(project.study_settings),
                "study_history": [_run_to_dict(item) for item in project.study_history],
            },
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        temporary: str | None = None
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
                temporary = stream.name
                stream.write(serialized)
            os.replace(temporary, target)
        except Exception:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            raise
        return target


def _complex_to_json(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _complex_from_json(value: Any) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ProjectFileError("Complex values must be encoded as [real, imaginary].")
    return complex(float(value[0]), float(value[1]))


def _settings_to_dict(settings: TheveninStudySettings) -> dict[str, Any]:
    return {
        "bus_name": settings.bus_name,
        "study_name": settings.study_name,
        "base_power_mva": settings.base_power_mva,
        "base_voltage_ll_kv": settings.base_voltage_ll_kv,
        "prefault_positive_voltage_pu": _complex_to_json(settings.prefault_positive_voltage_pu),
        "positive_sequence_impedance_pu": _complex_to_json(settings.positive_sequence_impedance_pu),
        "negative_sequence_impedance_pu": _complex_to_json(settings.negative_sequence_impedance_pu),
        "zero_sequence_impedance_pu": _complex_to_json(settings.zero_sequence_impedance_pu),
        "fault_type": settings.fault_type.value,
        "fault_impedance_pu": _complex_to_json(settings.fault_impedance_pu),
    }


def _settings_from_dict(payload: dict[str, Any]) -> TheveninStudySettings:
    return TheveninStudySettings(
        bus_name=payload["bus_name"],
        study_name=payload["study_name"],
        base_power_mva=payload["base_power_mva"],
        base_voltage_ll_kv=payload["base_voltage_ll_kv"],
        prefault_positive_voltage_pu=_complex_from_json(payload["prefault_positive_voltage_pu"]),
        positive_sequence_impedance_pu=_complex_from_json(
            payload["positive_sequence_impedance_pu"]
        ),
        negative_sequence_impedance_pu=_complex_from_json(
            payload["negative_sequence_impedance_pu"]
        ),
        zero_sequence_impedance_pu=_complex_from_json(payload["zero_sequence_impedance_pu"]),
        fault_type=FaultType(payload["fault_type"]),
        fault_impedance_pu=_complex_from_json(payload["fault_impedance_pu"]),
    )


def _run_to_dict(run: ProjectStudyRun) -> dict[str, Any]:
    def encode_entries(
        entries: tuple[tuple[str, tuple[float, float]], ...],
    ) -> list[dict[str, Any]]:
        return [{"sequence": sequence, "phasor": list(value)} for sequence, value in entries]

    return {
        "run_id": str(run.run_id),
        "study_name": run.study_name,
        "executed_at": run.executed_at.isoformat(),
        "fault_type": run.fault_type.value,
        "settings_snapshot": _settings_to_dict(run.settings_snapshot),
        "base_power_mva": run.base_power_mva,
        "base_voltage_kv": run.base_voltage_kv,
        "prefault_sequence_voltages_pu": encode_entries(run.prefault_sequence_voltages_pu),
        "driving_point_impedances_pu": encode_entries(run.driving_point_impedances_pu),
        "sequence_currents_pu": encode_entries(run.sequence_currents_pu),
        "sequence_voltages_pu": encode_entries(run.sequence_voltages_pu),
        "ground_current_pu": list(run.ground_current_pu),
        "ground_current_ka": list(run.ground_current_ka),
        "phase_currents_pu": [list(item) for item in run.phase_currents_pu],
        "phase_voltages_pu": [list(item) for item in run.phase_voltages_pu],
        "phase_currents_ka": [list(item) for item in run.phase_currents_ka],
        "phase_voltages_kv": [list(item) for item in run.phase_voltages_kv],
    }


def _run_from_dict(payload: dict[str, Any]) -> ProjectStudyRun:
    def decode_entries(name: str) -> tuple[tuple[str, tuple[float, float]], ...]:
        return tuple(
            (item["sequence"], (float(item["phasor"][0]), float(item["phasor"][1])))
            for item in payload.get(name, [])
        )

    def decode_phases(name: str) -> tuple[tuple[float, float], ...]:
        return tuple((float(item[0]), float(item[1])) for item in payload[name])

    return ProjectStudyRun(
        run_id=UUID(payload["run_id"]),
        study_name=payload["study_name"],
        executed_at=datetime.fromisoformat(payload["executed_at"]),
        fault_type=FaultType(payload["fault_type"]),
        settings_snapshot=_settings_from_dict(payload["settings_snapshot"]),
        base_power_mva=payload["base_power_mva"],
        base_voltage_kv=payload["base_voltage_kv"],
        prefault_sequence_voltages_pu=decode_entries("prefault_sequence_voltages_pu"),
        driving_point_impedances_pu=decode_entries("driving_point_impedances_pu"),
        sequence_currents_pu=decode_entries("sequence_currents_pu"),
        sequence_voltages_pu=decode_entries("sequence_voltages_pu"),
        ground_current_pu=(
            float(payload["ground_current_pu"][0]),
            float(payload["ground_current_pu"][1]),
        ),
        ground_current_ka=(
            float(payload["ground_current_ka"][0]),
            float(payload["ground_current_ka"][1]),
        ),
        phase_currents_pu=decode_phases("phase_currents_pu"),
        phase_voltages_pu=decode_phases("phase_voltages_pu"),
        phase_currents_ka=decode_phases("phase_currents_ka"),
        phase_voltages_kv=decode_phases("phase_voltages_kv"),
    )
