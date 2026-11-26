"""Immutable project and single-bus Thevenin study definitions.

The project document is a local engineering workspace. It is deliberately
independent of Qt, persistence libraries, report exporters and numerical solvers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult

type ComplexPair = tuple[float, float]


def _finite_number(value: float, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be greater than zero.")
    return result


def _finite_complex(value: complex, name: str, *, nonzero: bool = False) -> complex:
    if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
        raise TypeError(f"{name} must be a real or complex number, not bool.")
    result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"{name} must have finite real and imaginary components.")
    if nonzero and abs(result) <= 1e-15:
        raise ValueError(f"{name} cannot be zero.")
    return result


def complex_to_pair(value: complex) -> ComplexPair:
    number = complex(value)
    return (float(number.real), float(number.imag))


def pair_to_complex(value: ComplexPair) -> complex:
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError("A complex pair must be a two-value tuple.")
    return complex(
        _finite_number(value[0], "complex real part"),
        _finite_number(value[1], "complex imaginary part"),
    )


@dataclass(frozen=True, slots=True)
class TheveninStudySettings:
    """Explicit single-bus Thevenin study inputs in per-unit quantities."""

    bus_name: str = "101"
    study_name: str = "REF-3PH-001B"
    base_power_mva: float = 100.0
    base_voltage_ll_kv: float = 13.8
    prefault_positive_voltage_pu: complex = 1.02 + 0.025j
    positive_sequence_impedance_pu: complex = 0.08 + 0.24j
    negative_sequence_impedance_pu: complex = 0.11 + 0.31j
    zero_sequence_impedance_pu: complex = 0.18 + 0.52j
    fault_type: FaultType = FaultType.THREE_PHASE
    fault_impedance_pu: complex = 0.025 + 0.07j

    def __post_init__(self) -> None:
        for name in ("bus_name", "study_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
            object.__setattr__(self, name, value.strip())
        object.__setattr__(
            self,
            "base_power_mva",
            _finite_number(self.base_power_mva, "base_power_mva", positive=True),
        )
        object.__setattr__(
            self,
            "base_voltage_ll_kv",
            _finite_number(self.base_voltage_ll_kv, "base_voltage_ll_kv", positive=True),
        )
        if not isinstance(self.fault_type, FaultType):
            raise TypeError("fault_type must be a FaultType value.")
        object.__setattr__(
            self,
            "prefault_positive_voltage_pu",
            _finite_complex(
                self.prefault_positive_voltage_pu,
                "prefault_positive_voltage_pu",
                nonzero=True,
            ),
        )
        for name in (
            "positive_sequence_impedance_pu",
            "negative_sequence_impedance_pu",
            "zero_sequence_impedance_pu",
        ):
            impedance = _finite_complex(getattr(self, name), name, nonzero=True)
            if impedance.real < 0.0:
                raise ValueError(f"{name} resistance cannot be negative.")
            object.__setattr__(self, name, impedance)
        fault_impedance = _finite_complex(self.fault_impedance_pu, "fault_impedance_pu")
        if fault_impedance.real < 0.0:
            raise ValueError("Fault resistance cannot be negative.")
        object.__setattr__(self, "fault_impedance_pu", fault_impedance)


@dataclass(frozen=True, slots=True)
class ProjectStudyRun:
    """Persistable numerical snapshot of one executed bus-fault study."""

    run_id: UUID
    study_name: str
    executed_at: datetime
    fault_type: FaultType
    settings_snapshot: TheveninStudySettings
    base_power_mva: float
    base_voltage_kv: float
    prefault_sequence_voltages_pu: tuple[tuple[str, ComplexPair], ...]
    driving_point_impedances_pu: tuple[tuple[str, ComplexPair], ...]
    sequence_currents_pu: tuple[tuple[str, ComplexPair], ...]
    sequence_voltages_pu: tuple[tuple[str, ComplexPair], ...]
    ground_current_pu: ComplexPair
    ground_current_ka: ComplexPair
    phase_currents_pu: tuple[ComplexPair, ComplexPair, ComplexPair]
    phase_voltages_pu: tuple[ComplexPair, ComplexPair, ComplexPair]
    phase_currents_ka: tuple[ComplexPair, ComplexPair, ComplexPair]
    phase_voltages_kv: tuple[ComplexPair, ComplexPair, ComplexPair]

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be a UUID.")
        if not isinstance(self.study_name, str) or not self.study_name.strip():
            raise ValueError("study_name cannot be empty.")
        if not isinstance(self.executed_at, datetime) or self.executed_at.tzinfo is None:
            raise ValueError("executed_at must be timezone-aware.")
        if not isinstance(self.fault_type, FaultType):
            raise TypeError("fault_type must be a FaultType.")
        if not isinstance(self.settings_snapshot, TheveninStudySettings):
            raise TypeError("settings_snapshot must be a TheveninStudySettings.")
        if self.fault_type is not self.settings_snapshot.fault_type:
            raise ValueError("Stored run fault type differs from its settings snapshot.")
        if self.base_power_mva != self.settings_snapshot.base_power_mva:
            raise ValueError("Stored run MVA base differs from its settings snapshot.")
        if self.base_voltage_kv != self.settings_snapshot.base_voltage_ll_kv:
            raise ValueError("Stored run kV base differs from its settings snapshot.")
        object.__setattr__(
            self,
            "base_power_mva",
            _finite_number(self.base_power_mva, "base_power_mva", positive=True),
        )
        object.__setattr__(
            self,
            "base_voltage_kv",
            _finite_number(self.base_voltage_kv, "base_voltage_kv", positive=True),
        )
        for name in (
            "phase_currents_pu",
            "phase_voltages_pu",
            "phase_currents_ka",
            "phase_voltages_kv",
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or len(values) != 3:
                raise ValueError(f"{name} must contain exactly three A-B-C values.")
            object.__setattr__(
                self,
                name,
                tuple(complex_to_pair(pair_to_complex(item)) for item in values),
            )
        object.__setattr__(
            self,
            "ground_current_pu",
            complex_to_pair(pair_to_complex(self.ground_current_pu)),
        )
        object.__setattr__(
            self,
            "ground_current_ka",
            complex_to_pair(pair_to_complex(self.ground_current_ka)),
        )
        for name in (
            "prefault_sequence_voltages_pu",
            "driving_point_impedances_pu",
            "sequence_currents_pu",
            "sequence_voltages_pu",
        ):
            entries = getattr(self, name)
            if not isinstance(entries, tuple):
                raise TypeError(f"{name} must be a tuple.")
            normalized = []
            for sequence, pair in entries:
                if sequence not in {item.value for item in SequenceType}:
                    raise ValueError(f"Unsupported sequence: {sequence!r}.")
                normalized.append((sequence, complex_to_pair(pair_to_complex(pair))))
            object.__setattr__(self, name, tuple(normalized))

    @classmethod
    def from_result(
        cls,
        result: ShortCircuitResult,
        *,
        study_name: str,
        settings_snapshot: TheveninStudySettings,
        executed_at: datetime | None = None,
    ) -> ProjectStudyRun:
        if not isinstance(result, ShortCircuitResult):
            raise TypeError("result must be a ShortCircuitResult.")
        if not isinstance(settings_snapshot, TheveninStudySettings):
            raise TypeError("settings_snapshot must be a TheveninStudySettings.")
        if result.fault_type is not settings_snapshot.fault_type:
            raise ValueError("Result fault type differs from the stored study settings.")
        if result.fault_impedance_pu != settings_snapshot.fault_impedance_pu:
            raise ValueError("Result fault impedance differs from the stored study settings.")
        if result.base_power_mva != settings_snapshot.base_power_mva:
            raise ValueError("Result power base differs from the stored study settings.")
        if result.base_voltage_kv != settings_snapshot.base_voltage_ll_kv:
            raise ValueError("Result voltage base differs from the stored study settings.")
        timestamp = executed_at or datetime.now(UTC)
        return cls(
            run_id=uuid4(),
            study_name=study_name,
            executed_at=timestamp,
            fault_type=result.fault_type,
            settings_snapshot=settings_snapshot,
            base_power_mva=result.base_power_mva,
            base_voltage_kv=result.base_voltage_kv,
            prefault_sequence_voltages_pu=tuple(
                (sequence.value, complex_to_pair(value))
                for sequence, value in result.prefault_sequence_voltages_pu.items()
            ),
            driving_point_impedances_pu=tuple(
                (sequence.value, complex_to_pair(value))
                for sequence, value in result.driving_point_impedances_pu.items()
            ),
            sequence_currents_pu=tuple(
                (sequence.value, complex_to_pair(value))
                for sequence, value in result.sequence_currents_pu.items()
            ),
            sequence_voltages_pu=tuple(
                (sequence.value, complex_to_pair(value))
                for sequence, value in result.sequence_fault_voltages_pu.items()
            ),
            ground_current_pu=complex_to_pair(result.ground_current_pu),
            ground_current_ka=complex_to_pair(result.ground_current_ka),
            phase_currents_pu=tuple(complex_to_pair(value) for value in result.phase_currents_pu),
            phase_voltages_pu=tuple(complex_to_pair(value) for value in result.phase_voltages_pu),
            phase_currents_ka=tuple(complex_to_pair(value) for value in result.phase_currents_ka),
            phase_voltages_kv=tuple(complex_to_pair(value) for value in result.phase_voltages_kv),
        )


@dataclass(frozen=True, slots=True)
class Project:
    """Project aggregate persisted as one portable ``.pfa`` JSON document."""

    project_id: UUID
    name: str
    description: str
    created_at: datetime
    modified_at: datetime
    study_settings: TheveninStudySettings
    study_history: tuple[ProjectStudyRun, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, UUID):
            raise TypeError("project_id must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Project name cannot be empty.")
        if not isinstance(self.description, str):
            raise TypeError("Project description must be text.")
        for name in ("created_at", "modified_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware.")
        if not isinstance(self.study_settings, TheveninStudySettings):
            raise TypeError("study_settings must be a TheveninStudySettings.")
        if not isinstance(self.study_history, tuple) or any(
            not isinstance(item, ProjectStudyRun) for item in self.study_history
        ):
            raise TypeError("study_history must be a tuple of ProjectStudyRun values.")
        object.__setattr__(self, "name", self.name.strip())

    @classmethod
    def create(
        cls,
        name: str = "Untitled Project",
        description: str = "",
        study_settings: TheveninStudySettings | None = None,
    ) -> Project:
        now = datetime.now(UTC)
        return cls(
            project_id=uuid4(),
            name=name,
            description=description,
            created_at=now,
            modified_at=now,
            study_settings=study_settings or TheveninStudySettings(),
        )

    def with_settings(self, settings: TheveninStudySettings) -> Project:
        if not isinstance(settings, TheveninStudySettings):
            raise TypeError("settings must be a TheveninStudySettings.")
        return replace(self, study_settings=settings, modified_at=datetime.now(UTC))

    def with_study_run(self, run: ProjectStudyRun) -> Project:
        if not isinstance(run, ProjectStudyRun):
            raise TypeError("run must be a ProjectStudyRun.")
        if any(item.run_id == run.run_id for item in self.study_history):
            raise ValueError(f"Study run '{run.run_id}' is already recorded in this project.")
        return replace(
            self,
            study_history=(*self.study_history, run),
            modified_at=datetime.now(UTC),
        )
