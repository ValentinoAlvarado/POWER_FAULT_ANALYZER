"""Immutable settings, phasor measurements and results for advanced protection functions.

The models expose the steady-state relay characteristics used by this package. They do not
claim dynamic relay compliance or substitute for manufacturer type-test evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from types import MappingProxyType
from uuid import UUID, uuid4

from power_fault_analyzer.domain.enums.advanced_protection import (
    DifferentialProtectionKind,
    DirectionalSense,
    DistanceCharacteristic,
    DistanceLoop,
)
from power_fault_analyzer.domain.enums.protection import ProtectionAssessmentStatus
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CurrentTransformerRatio,
    OvercurrentRelay,
)

type Complex3 = tuple[complex, complex, complex]
type CompensationMatrix = tuple[
    tuple[complex, complex, complex],
    tuple[complex, complex, complex],
    tuple[complex, complex, complex],
]


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


def _non_negative(value: float, name: str) -> float:
    result = _finite(value, name)
    if result < 0.0:
        raise ValueError(f"{name} cannot be negative.")
    return result


def _finite_complex(value: complex, name: str) -> complex:
    if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
        raise TypeError(f"{name} must be a real or complex number.")
    result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"{name} must be finite.")
    return result


def _phasor3(values: tuple[complex, ...], name: str) -> Complex3:
    if not isinstance(values, tuple) or len(values) != 3:
        raise TypeError(f"{name} must be a three-element tuple of phasors.")
    converted = tuple(
        _finite_complex(value, f"{name}[{index}]") for index, value in enumerate(values)
    )
    return (converted[0], converted[1], converted[2])


def _identity_matrix() -> CompensationMatrix:
    return (
        (1.0 + 0.0j, 0.0j, 0.0j),
        (0.0j, 1.0 + 0.0j, 0.0j),
        (0.0j, 0.0j, 1.0 + 0.0j),
    )


def _matrix3(values: tuple[tuple[complex, ...], ...]) -> CompensationMatrix:
    if not isinstance(values, tuple) or len(values) != 3:
        raise TypeError("phase_compensation_matrix must be a 3x3 tuple.")
    rows = tuple(_phasor3(row, "phase_compensation_matrix row") for row in values)
    a, b, c = rows
    determinant = (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )
    if abs(determinant) <= 1e-12:
        raise ValueError("phase_compensation_matrix must be non-singular.")
    return rows  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class VoltageTransformerRatio:
    """Primary-to-secondary voltage ratio for a distance relay VT input."""

    primary_rated_voltage_v: float
    secondary_rated_voltage_v: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "primary_rated_voltage_v",
            _positive(self.primary_rated_voltage_v, "primary_rated_voltage_v"),
        )
        object.__setattr__(
            self,
            "secondary_rated_voltage_v",
            _positive(self.secondary_rated_voltage_v, "secondary_rated_voltage_v"),
        )

    @property
    def ratio(self) -> float:
        return self.primary_rated_voltage_v / self.secondary_rated_voltage_v

    def to_secondary(self, primary_voltage_v: complex) -> complex:
        return _finite_complex(primary_voltage_v, "primary_voltage_v") / self.ratio


@dataclass(frozen=True, slots=True)
class DifferentialSideSettings:
    """Per-side current scaling and explicit phase compensation for a differential zone.

    Currents are supplied as primary phasors. The current base is the equipment-side
    rated phase current; the CT ratio is retained as engineering metadata and for
    cross-checking the associated CT performance model.
    """

    side_id: str
    current_base_primary_a: float
    current_transformer: CurrentTransformerRatio
    polarity: int = 1
    phase_compensation_matrix: CompensationMatrix = field(default_factory=_identity_matrix)

    def __post_init__(self) -> None:
        if not isinstance(self.side_id, str) or not self.side_id.strip():
            raise ValueError("side_id cannot be empty.")
        object.__setattr__(self, "side_id", self.side_id.strip())
        object.__setattr__(
            self,
            "current_base_primary_a",
            _positive(self.current_base_primary_a, "current_base_primary_a"),
        )
        if not isinstance(self.current_transformer, CurrentTransformerRatio):
            raise TypeError("current_transformer must be a CurrentTransformerRatio.")
        if isinstance(self.polarity, bool) or self.polarity not in (-1, 1):
            raise ValueError("polarity must be either -1 or +1.")
        object.__setattr__(
            self, "phase_compensation_matrix", _matrix3(self.phase_compensation_matrix)
        )


@dataclass(frozen=True, slots=True)
class DifferentialProtectionSettings:
    """Two-terminal biased differential 87L/87T steady-state characteristic."""

    name: str
    kind: DifferentialProtectionKind
    sides: tuple[DifferentialSideSettings, DifferentialSideSettings]
    minimum_pickup_pu: float
    low_slope: float
    breakpoint_restraint_pu: float
    high_slope: float
    unrestrained_pickup_pu: float | None = None
    second_harmonic_block_ratio: float | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name cannot be empty.")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.kind, DifferentialProtectionKind):
            raise TypeError("kind must be a DifferentialProtectionKind.")
        if (
            not isinstance(self.sides, tuple)
            or len(self.sides) != 2
            or any(not isinstance(item, DifferentialSideSettings) for item in self.sides)
        ):
            raise TypeError("sides must contain exactly two DifferentialSideSettings values.")
        if self.sides[0].side_id == self.sides[1].side_id:
            raise ValueError("Differential side identifiers must be unique.")
        for name in (
            "minimum_pickup_pu",
            "low_slope",
            "breakpoint_restraint_pu",
            "high_slope",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        if self.unrestrained_pickup_pu is not None:
            object.__setattr__(
                self,
                "unrestrained_pickup_pu",
                _positive(self.unrestrained_pickup_pu, "unrestrained_pickup_pu"),
            )
        if self.second_harmonic_block_ratio is not None:
            ratio = _positive(self.second_harmonic_block_ratio, "second_harmonic_block_ratio")
            if ratio > 1.0:
                raise ValueError("second_harmonic_block_ratio must not exceed 1.0.")
            object.__setattr__(self, "second_harmonic_block_ratio", ratio)


@dataclass(frozen=True, slots=True)
class DifferentialMeasurement:
    """Fundamental primary current phasors entering a protected zone at both ends."""

    side_currents_primary_a: Mapping[str, Complex3]
    second_harmonic_ratio_by_phase: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if not isinstance(self.side_currents_primary_a, Mapping):
            raise TypeError("side_currents_primary_a must be a mapping.")
        copied: dict[str, Complex3] = {}
        for side_id, values in self.side_currents_primary_a.items():
            if not isinstance(side_id, str) or not side_id.strip():
                raise TypeError("Differential measurement side IDs must be non-empty strings.")
            copied[side_id.strip()] = _phasor3(values, f"side_currents_primary_a[{side_id}]")
        if len(copied) != 2:
            raise ValueError("Differential measurement requires currents from exactly two sides.")
        if (
            not isinstance(self.second_harmonic_ratio_by_phase, tuple)
            or len(self.second_harmonic_ratio_by_phase) != 3
        ):
            raise TypeError("second_harmonic_ratio_by_phase must contain three ratios.")
        ratios = tuple(
            _non_negative(value, "second_harmonic_ratio_by_phase")
            for value in self.second_harmonic_ratio_by_phase
        )
        if any(value > 1.0 for value in ratios):
            raise ValueError("Second-harmonic ratios must not exceed 1.0.")
        object.__setattr__(self, "side_currents_primary_a", MappingProxyType(copied))
        object.__setattr__(self, "second_harmonic_ratio_by_phase", ratios)


@dataclass(frozen=True, slots=True)
class DifferentialPhaseOperation:
    phase: str
    differential_current_pu: float
    restraint_current_pu: float
    operating_threshold_pu: float
    second_harmonic_ratio: float
    blocked_by_harmonic: bool
    operated: bool


@dataclass(frozen=True, slots=True)
class DifferentialOperationResult:
    relay_id: UUID
    phases: tuple[DifferentialPhaseOperation, ...]
    operated: bool


@dataclass(frozen=True, slots=True)
class DirectionalOvercurrentSettings:
    """Directional supervision of an existing 50/51 phase or earth relay."""

    relay: OvercurrentRelay
    maximum_torque_angle_deg: float
    minimum_polarizing_voltage_v: float
    sense: DirectionalSense = DirectionalSense.FORWARD
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.relay, OvercurrentRelay):
            raise TypeError("relay must be an OvercurrentRelay.")
        angle = _finite(self.maximum_torque_angle_deg, "maximum_torque_angle_deg")
        if not -180.0 <= angle <= 180.0:
            raise ValueError("maximum_torque_angle_deg must be within [-180, 180].")
        object.__setattr__(self, "maximum_torque_angle_deg", angle)
        object.__setattr__(
            self,
            "minimum_polarizing_voltage_v",
            _positive(self.minimum_polarizing_voltage_v, "minimum_polarizing_voltage_v"),
        )
        if not isinstance(self.sense, DirectionalSense):
            raise TypeError("sense must be a DirectionalSense.")

    @property
    def name(self) -> str:
        return f"{self.relay.name} directional supervision"


@dataclass(frozen=True, slots=True)
class DirectionalMeasurement:
    operating_current_primary_a: complex
    polarizing_voltage_v: complex

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operating_current_primary_a",
            _finite_complex(self.operating_current_primary_a, "operating_current_primary_a"),
        )
        object.__setattr__(
            self,
            "polarizing_voltage_v",
            _finite_complex(self.polarizing_voltage_v, "polarizing_voltage_v"),
        )


@dataclass(frozen=True, slots=True)
class DirectionalOperationResult:
    relay_id: UUID
    overcurrent_picked_up: bool
    directional_decision: DirectionalSense | None
    directional_torque: float | None
    operated: bool
    operating_time_s: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class DistanceZoneSettings:
    """One impedance-plane zone; impedances are specified on the relay secondary."""

    zone_number: int
    characteristic: DistanceCharacteristic
    operating_time_s: float
    reach_impedance_secondary_ohm: complex | None = None
    resistance_min_ohm: float | None = None
    resistance_max_ohm: float | None = None
    reactance_min_ohm: float | None = None
    reactance_max_ohm: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.zone_number, bool) or not isinstance(self.zone_number, int):
            raise TypeError("zone_number must be an integer.")
        if self.zone_number < 1:
            raise ValueError("zone_number must be positive.")
        if not isinstance(self.characteristic, DistanceCharacteristic):
            raise TypeError("characteristic must be a DistanceCharacteristic.")
        object.__setattr__(
            self, "operating_time_s", _non_negative(self.operating_time_s, "operating_time_s")
        )
        if self.characteristic is DistanceCharacteristic.MHO:
            if self.reach_impedance_secondary_ohm is None:
                raise ValueError("MHO zones require reach_impedance_secondary_ohm.")
            reach = _finite_complex(
                self.reach_impedance_secondary_ohm, "reach_impedance_secondary_ohm"
            )
            if abs(reach) <= 1e-12 or reach.imag <= 0.0:
                raise ValueError("MHO reach must be non-zero with positive reactance.")
            object.__setattr__(self, "reach_impedance_secondary_ohm", reach)
            if any(
                value is not None
                for value in (
                    self.resistance_min_ohm,
                    self.resistance_max_ohm,
                    self.reactance_min_ohm,
                    self.reactance_max_ohm,
                )
            ):
                raise ValueError("MHO zones cannot declare quadrilateral boundaries.")
        else:
            values = (
                "resistance_min_ohm",
                "resistance_max_ohm",
                "reactance_min_ohm",
                "reactance_max_ohm",
            )
            for name in values:
                if getattr(self, name) is None:
                    raise ValueError(f"Quadrilateral zones require {name}.")
                object.__setattr__(self, name, _finite(getattr(self, name), name))
            if self.resistance_min_ohm >= self.resistance_max_ohm:
                raise ValueError("Quadrilateral resistance minimum must be below maximum.")
            if self.reactance_min_ohm >= self.reactance_max_ohm:
                raise ValueError("Quadrilateral reactance minimum must be below maximum.")
            if self.reactance_max_ohm <= 0.0:
                raise ValueError("Forward quadrilateral zone must extend into positive reactance.")


@dataclass(frozen=True, slots=True)
class DistanceProtectionSettings:
    """Distance relay with CT/VT conversion and explicitly configured impedance zones."""

    name: str
    current_transformer: CurrentTransformerRatio
    voltage_transformer: VoltageTransformerRatio
    zones: tuple[DistanceZoneSettings, ...]
    ground_compensation_factor: complex = 0.0j
    minimum_current_secondary_a: float = 0.05
    minimum_voltage_secondary_v: float = 1.0
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name cannot be empty.")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.current_transformer, CurrentTransformerRatio):
            raise TypeError("current_transformer must be a CurrentTransformerRatio.")
        if not isinstance(self.voltage_transformer, VoltageTransformerRatio):
            raise TypeError("voltage_transformer must be a VoltageTransformerRatio.")
        if (
            not isinstance(self.zones, tuple)
            or not self.zones
            or any(not isinstance(item, DistanceZoneSettings) for item in self.zones)
        ):
            raise TypeError("zones must be a non-empty tuple of DistanceZoneSettings.")
        zone_numbers = tuple(item.zone_number for item in self.zones)
        if len(zone_numbers) != len(set(zone_numbers)):
            raise ValueError("Distance zone numbers must be unique.")
        if zone_numbers != tuple(sorted(zone_numbers)):
            raise ValueError("Distance zones must be ordered by increasing zone number.")
        object.__setattr__(
            self,
            "ground_compensation_factor",
            _finite_complex(self.ground_compensation_factor, "ground_compensation_factor"),
        )
        object.__setattr__(
            self,
            "minimum_current_secondary_a",
            _positive(self.minimum_current_secondary_a, "minimum_current_secondary_a"),
        )
        object.__setattr__(
            self,
            "minimum_voltage_secondary_v",
            _positive(self.minimum_voltage_secondary_v, "minimum_voltage_secondary_v"),
        )


@dataclass(frozen=True, slots=True)
class DistanceMeasurement:
    """Primary phase voltage and current phasors at one line terminal."""

    phase_voltages_primary_v: Complex3
    phase_currents_primary_a: Complex3

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "phase_voltages_primary_v",
            _phasor3(self.phase_voltages_primary_v, "phase_voltages_primary_v"),
        )
        object.__setattr__(
            self,
            "phase_currents_primary_a",
            _phasor3(self.phase_currents_primary_a, "phase_currents_primary_a"),
        )


@dataclass(frozen=True, slots=True)
class DistanceLoopOperation:
    loop: DistanceLoop
    apparent_impedance_secondary_ohm: complex | None
    reached_zone_number: int | None
    operating_time_s: float | None
    evaluated: bool


@dataclass(frozen=True, slots=True)
class DistanceOperationResult:
    relay_id: UUID
    loops: tuple[DistanceLoopOperation, ...]
    operated: bool
    fastest_zone_number: int | None
    operating_time_s: float | None


@dataclass(frozen=True, slots=True)
class CTExcitationPoint:
    voltage_v: float
    exciting_current_a: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "voltage_v", _positive(self.voltage_v, "voltage_v"))
        object.__setattr__(
            self, "exciting_current_a", _positive(self.exciting_current_a, "exciting_current_a")
        )


@dataclass(frozen=True, slots=True)
class CurrentTransformerPerformanceModel:
    """CT excitation-curve and burden data for steady-state and transient studies."""

    name: str
    current_transformer: CurrentTransformerRatio
    secondary_winding_resistance_ohm: float
    burden_impedance_ohm: complex
    knee_point_voltage_v: float
    excitation_curve: tuple[CTExcitationPoint, ...]
    rated_frequency_hz: float
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name cannot be empty.")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.current_transformer, CurrentTransformerRatio):
            raise TypeError("current_transformer must be a CurrentTransformerRatio.")
        object.__setattr__(
            self,
            "secondary_winding_resistance_ohm",
            _non_negative(
                self.secondary_winding_resistance_ohm, "secondary_winding_resistance_ohm"
            ),
        )
        object.__setattr__(
            self,
            "burden_impedance_ohm",
            _finite_complex(self.burden_impedance_ohm, "burden_impedance_ohm"),
        )
        object.__setattr__(
            self,
            "knee_point_voltage_v",
            _positive(self.knee_point_voltage_v, "knee_point_voltage_v"),
        )
        object.__setattr__(
            self, "rated_frequency_hz", _positive(self.rated_frequency_hz, "rated_frequency_hz")
        )
        if (
            not isinstance(self.excitation_curve, tuple)
            or len(self.excitation_curve) < 2
            or any(not isinstance(item, CTExcitationPoint) for item in self.excitation_curve)
        ):
            raise TypeError("excitation_curve must contain at least two CTExcitationPoint values.")
        voltages = tuple(item.voltage_v for item in self.excitation_curve)
        currents = tuple(item.exciting_current_a for item in self.excitation_curve)
        if any(right <= left for left, right in pairwise(voltages)):
            raise ValueError("CT excitation voltages must be strictly increasing.")
        if any(right <= left for left, right in pairwise(currents)):
            raise ValueError("CT excitation currents must be strictly increasing.")


@dataclass(frozen=True, slots=True)
class CTSaturationAssessment:
    transformer_id: UUID
    status: ProtectionAssessmentStatus
    required_secondary_voltage_v: float
    knee_point_voltage_v: float
    voltage_margin_v: float
    exciting_current_a: float | None
    transient_status: ProtectionAssessmentStatus = ProtectionAssessmentStatus.NOT_EVALUATED
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.transformer_id, UUID):
            raise TypeError("transformer_id must be a UUID.")
        if not isinstance(self.status, ProtectionAssessmentStatus) or not isinstance(
            self.transient_status, ProtectionAssessmentStatus
        ):
            raise TypeError("Saturation statuses must be ProtectionAssessmentStatus values.")
        for name in (
            "required_secondary_voltage_v",
            "knee_point_voltage_v",
            "voltage_margin_v",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.exciting_current_a is not None:
            object.__setattr__(
                self,
                "exciting_current_a",
                _non_negative(self.exciting_current_a, "exciting_current_a"),
            )


@dataclass(frozen=True, slots=True)
class AdvancedProtectionFunctionBinding:
    """Attach one advanced function to an element and a declared protection zone."""

    function: (
        DifferentialProtectionSettings | DirectionalOvercurrentSettings | DistanceProtectionSettings
    )
    protected_equipment_id: UUID
    zone_id: UUID
    monitored_terminal_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.function,
            (
                DifferentialProtectionSettings,
                DirectionalOvercurrentSettings,
                DistanceProtectionSettings,
            ),
        ):
            raise TypeError("function must be a supported advanced-protection settings object.")
        if not isinstance(self.protected_equipment_id, UUID) or not isinstance(self.zone_id, UUID):
            raise TypeError("protected_equipment_id and zone_id must be UUID values.")
        if not isinstance(self.monitored_terminal_ids, tuple) or any(
            not isinstance(item, UUID) for item in self.monitored_terminal_ids
        ):
            raise TypeError("monitored_terminal_ids must be a tuple of UUID values.")
        expected = 2 if isinstance(self.function, DifferentialProtectionSettings) else 1
        if (
            len(self.monitored_terminal_ids) != expected
            or len(set(self.monitored_terminal_ids)) != expected
        ):
            raise ValueError(
                f"This function requires exactly {expected} distinct monitored terminals."
            )

    @property
    def id(self) -> UUID:
        return self.function.id


@dataclass(frozen=True, slots=True)
class CurrentTransformerPerformanceBinding:
    protection_device_id: UUID
    performance_model: CurrentTransformerPerformanceModel

    def __post_init__(self) -> None:
        if not isinstance(self.protection_device_id, UUID):
            raise TypeError("protection_device_id must be a UUID.")
        if not isinstance(self.performance_model, CurrentTransformerPerformanceModel):
            raise TypeError("performance_model must be a CurrentTransformerPerformanceModel.")


@dataclass(frozen=True, slots=True)
class AdvancedProtectionFunctionMeasurement:
    measurement: DifferentialMeasurement | DirectionalMeasurement | DistanceMeasurement
    expected_to_operate: bool

    def __post_init__(self) -> None:
        if not isinstance(
            self.measurement, (DifferentialMeasurement, DirectionalMeasurement, DistanceMeasurement)
        ):
            raise TypeError("measurement must match a supported advanced-protection function.")
        if not isinstance(self.expected_to_operate, bool):
            raise TypeError("expected_to_operate must be bool.")


@dataclass(frozen=True, slots=True)
class AdvancedProtectionScenarioMeasurements:
    scenario_id: UUID
    function_measurements: Mapping[UUID, AdvancedProtectionFunctionMeasurement]
    ct_primary_currents_a: Mapping[UUID, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, UUID):
            raise TypeError("scenario_id must be a UUID.")
        if not isinstance(self.function_measurements, Mapping):
            raise TypeError("function_measurements must be a mapping.")
        functions: dict[UUID, AdvancedProtectionFunctionMeasurement] = {}
        for function_id, measurement in self.function_measurements.items():
            if not isinstance(function_id, UUID) or not isinstance(
                measurement, AdvancedProtectionFunctionMeasurement
            ):
                raise TypeError("function_measurements must map UUIDs to advanced measurements.")
            functions[function_id] = measurement
        if not isinstance(self.ct_primary_currents_a, Mapping):
            raise TypeError("ct_primary_currents_a must be a mapping.")
        currents: dict[UUID, float] = {}
        for device_id, current in self.ct_primary_currents_a.items():
            if not isinstance(device_id, UUID):
                raise TypeError("CT current keys must be protection-device UUIDs.")
            currents[device_id] = _non_negative(current, "ct_primary_currents_a")
        object.__setattr__(self, "function_measurements", MappingProxyType(functions))
        object.__setattr__(self, "ct_primary_currents_a", MappingProxyType(currents))


@dataclass(frozen=True, slots=True)
class AdvancedProtectionFunctionAssessment:
    scenario_id: UUID
    function_id: UUID
    zone_id: UUID
    status: ProtectionAssessmentStatus
    operated: bool | None
    operation_result: (
        DifferentialOperationResult | DirectionalOperationResult | DistanceOperationResult | None
    )
    reason: str


@dataclass(frozen=True, slots=True)
class AdvancedProtectionScenarioAssessment:
    scenario_id: UUID
    function_assessments: tuple[AdvancedProtectionFunctionAssessment, ...]
    ct_assessments: Mapping[UUID, CTSaturationAssessment]
    status: ProtectionAssessmentStatus
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, UUID):
            raise TypeError("scenario_id must be a UUID.")
        if not isinstance(self.function_assessments, tuple) or any(
            not isinstance(item, AdvancedProtectionFunctionAssessment)
            for item in self.function_assessments
        ):
            raise TypeError("function_assessments must be a tuple of assessment values.")
        if not isinstance(self.ct_assessments, Mapping):
            raise TypeError("ct_assessments must be a mapping.")
        object.__setattr__(self, "ct_assessments", MappingProxyType(dict(self.ct_assessments)))
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, str) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of strings.")


@dataclass(frozen=True, slots=True)
class AdvancedProtectionNetworkAssessment:
    network_id: UUID
    scenarios: tuple[AdvancedProtectionScenarioAssessment, ...]
    status: ProtectionAssessmentStatus
