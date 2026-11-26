"""Immutable topology bindings, protection zones and integrated-study results."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from numbers import Real
from types import MappingProxyType
from uuid import UUID, uuid4

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.protection import (
    ProtectionAssessmentStatus,
    ProtectionStage,
)
from power_fault_analyzer.domain.enums.protection_network import (
    ProtectionFaultLocationKind,
    ProtectionRole,
)
from power_fault_analyzer.domain.value_objects.advanced_protection import (
    AdvancedProtectionFunctionBinding,
    CurrentTransformerPerformanceBinding,
)
from power_fault_analyzer.domain.value_objects.diagnostic import DomainDiagnostic
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    FuseLink,
    OvercurrentRelay,
)

ProtectionOperatingDevice = OvercurrentRelay | FuseLink


def _non_negative(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
    return result


def _unique_uuid_tuple(values: tuple[UUID, ...], name: str, *, non_empty: bool) -> tuple[UUID, ...]:
    if not isinstance(values, tuple) or any(not isinstance(item, UUID) for item in values):
        raise TypeError(f"{name} must be a tuple of UUID values.")
    if non_empty and not values:
        raise ValueError(f"{name} cannot be empty.")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} cannot contain duplicate identifiers.")
    return values


@dataclass(frozen=True, slots=True)
class ProtectionDeviceBinding:
    """Bind a relay/fuse and optional relay-operated breaker to a physical terminal.

    The relay CT or fuse element is located at ``monitored_terminal_id``. The
    network builder resolves that terminal to a physical bus and validates
    equipment ownership and interrupting-device voltage compatibility.
    A relay may omit its breaker only for relay-response studies; such a binding
    cannot demonstrate a complete primary or backup clearing operation.
    """

    device: ProtectionOperatingDevice
    monitored_equipment_id: UUID
    monitored_terminal_id: UUID
    breaker: CircuitBreaker | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.device, (OvercurrentRelay, FuseLink)):
            raise TypeError("device must be an OvercurrentRelay or FuseLink.")
        if not isinstance(self.monitored_equipment_id, UUID):
            raise TypeError("monitored_equipment_id must be a UUID.")
        if not isinstance(self.monitored_terminal_id, UUID):
            raise TypeError("monitored_terminal_id must be a UUID.")
        if self.breaker is not None and not isinstance(self.breaker, CircuitBreaker):
            raise TypeError("breaker must be a CircuitBreaker or None.")
        if isinstance(self.device, FuseLink) and self.breaker is not None:
            raise ValueError(
                "A fuse link is itself the interrupting device; do not attach a breaker."
            )

    @property
    def id(self) -> UUID:
        return self.device.id


@dataclass(frozen=True, slots=True)
class ProtectionBackupRelationship:
    """Explicit directional relationship: backup device protects primary failure."""

    primary_device_id: UUID
    backup_device_id: UUID
    minimum_coordination_interval_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.primary_device_id, UUID) or not isinstance(
            self.backup_device_id, UUID
        ):
            raise TypeError("Backup relationship device identifiers must be UUID values.")
        if self.primary_device_id == self.backup_device_id:
            raise ValueError("A device cannot be its own backup.")
        object.__setattr__(
            self,
            "minimum_coordination_interval_s",
            _non_negative(
                self.minimum_coordination_interval_s,
                "minimum_coordination_interval_s",
            ),
        )


@dataclass(frozen=True, slots=True)
class ProtectionZone:
    """Protection boundary and its explicitly assigned primary/backup devices."""

    name: str
    protected_element_ids: tuple[UUID, ...]
    primary_device_ids: tuple[UUID, ...]
    backup_device_ids: tuple[UUID, ...] = ()
    backup_relationships: tuple[ProtectionBackupRelationship, ...] = ()
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Protection-zone name cannot be empty.")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(
            self,
            "protected_element_ids",
            _unique_uuid_tuple(self.protected_element_ids, "protected_element_ids", non_empty=True),
        )
        object.__setattr__(
            self,
            "primary_device_ids",
            _unique_uuid_tuple(self.primary_device_ids, "primary_device_ids", non_empty=True),
        )
        object.__setattr__(
            self,
            "backup_device_ids",
            _unique_uuid_tuple(self.backup_device_ids, "backup_device_ids", non_empty=False),
        )
        if set(self.primary_device_ids) & set(self.backup_device_ids):
            raise ValueError("A device cannot be both primary and backup in the same zone.")
        if not isinstance(self.backup_relationships, tuple) or any(
            not isinstance(item, ProtectionBackupRelationship) for item in self.backup_relationships
        ):
            raise TypeError("backup_relationships must be a tuple of ProtectionBackupRelationship.")
        relationship_pairs = tuple(
            (item.primary_device_id, item.backup_device_id) for item in self.backup_relationships
        )
        if len(relationship_pairs) != len(set(relationship_pairs)):
            raise ValueError("Backup relationships cannot contain duplicate device pairs.")
        for relationship in self.backup_relationships:
            if relationship.primary_device_id not in self.primary_device_ids:
                raise ValueError("Backup relationship primary is not a primary zone device.")
            if relationship.backup_device_id not in self.backup_device_ids:
                raise ValueError("Backup relationship backup is not a backup zone device.")


@dataclass(frozen=True, slots=True)
class ProtectionNetworkModel:
    """Validated protection-to-network binding model."""

    network_id: UUID
    bindings: tuple[ProtectionDeviceBinding, ...]
    zones: tuple[ProtectionZone, ...]
    binding_bus_ids: Mapping[UUID, UUID]
    binding_equipment_names: Mapping[UUID, str]
    diagnostics: tuple[DomainDiagnostic, ...] = ()
    advanced_function_bindings: tuple[AdvancedProtectionFunctionBinding, ...] = ()
    ct_performance_bindings: tuple[CurrentTransformerPerformanceBinding, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.network_id, UUID):
            raise TypeError("network_id must be a UUID.")
        if not isinstance(self.bindings, tuple) or any(
            not isinstance(item, ProtectionDeviceBinding) for item in self.bindings
        ):
            raise TypeError("bindings must be a tuple of ProtectionDeviceBinding values.")
        if not isinstance(self.zones, tuple) or any(
            not isinstance(item, ProtectionZone) for item in self.zones
        ):
            raise TypeError("zones must be a tuple of ProtectionZone values.")
        binding_ids = tuple(item.id for item in self.bindings)
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("A protection device can only be bound once in one model.")
        zone_ids = tuple(item.id for item in self.zones)
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("Protection-zone IDs must be unique.")
        if not isinstance(self.binding_bus_ids, Mapping):
            raise TypeError("binding_bus_ids must be a mapping.")
        copied: dict[UUID, UUID] = {}
        for device_id, bus_id in self.binding_bus_ids.items():
            if not isinstance(device_id, UUID) or not isinstance(bus_id, UUID):
                raise TypeError("binding_bus_ids must map UUID device IDs to UUID bus IDs.")
            copied[device_id] = bus_id
        if set(copied) != set(binding_ids):
            raise ValueError("Every protection binding must have exactly one resolved bus ID.")
        known_devices = set(binding_ids)
        for zone in self.zones:
            referenced = set(zone.primary_device_ids) | set(zone.backup_device_ids)
            missing = referenced - known_devices
            if missing:
                raise ValueError(f"Protection zone references unknown devices: {missing}.")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of DomainDiagnostic values.")
        object.__setattr__(self, "binding_bus_ids", MappingProxyType(copied))
        if not isinstance(self.binding_equipment_names, Mapping):
            raise TypeError("binding_equipment_names must be a mapping.")
        names: dict[UUID, str] = {}
        for device_id, equipment_name in self.binding_equipment_names.items():
            if not isinstance(device_id, UUID) or not isinstance(equipment_name, str):
                raise TypeError("binding_equipment_names must map UUIDs to strings.")
            if not equipment_name.strip():
                raise ValueError("Equipment names cannot be empty.")
            names[device_id] = equipment_name.strip()
        if set(names) != set(binding_ids):
            raise ValueError("Every protection binding must have one resolved equipment name.")
        object.__setattr__(self, "binding_equipment_names", MappingProxyType(names))
        if not isinstance(self.advanced_function_bindings, tuple) or any(
            not isinstance(item, AdvancedProtectionFunctionBinding)
            for item in self.advanced_function_bindings
        ):
            raise TypeError("advanced_function_bindings must contain advanced-function bindings.")
        advanced_ids = tuple(item.id for item in self.advanced_function_bindings)
        if len(advanced_ids) != len(set(advanced_ids)):
            raise ValueError("Advanced protection function IDs must be unique.")
        if set(advanced_ids) & set(binding_ids):
            raise ValueError("Advanced function IDs cannot collide with primary device IDs.")
        known_zone_ids = set(zone_ids)
        if any(item.zone_id not in known_zone_ids for item in self.advanced_function_bindings):
            raise ValueError("Every advanced protection function must reference a known zone.")
        if any(
            item.protected_equipment_id
            not in next(
                zone for zone in self.zones if zone.id == item.zone_id
            ).protected_element_ids
            for item in self.advanced_function_bindings
        ):
            raise ValueError("Advanced protection function equipment must belong to its zone.")
        if not isinstance(self.ct_performance_bindings, tuple) or any(
            not isinstance(item, CurrentTransformerPerformanceBinding)
            for item in self.ct_performance_bindings
        ):
            raise TypeError("ct_performance_bindings must contain CT performance bindings.")
        ct_device_ids = tuple(item.protection_device_id for item in self.ct_performance_bindings)
        if len(ct_device_ids) != len(set(ct_device_ids)):
            raise ValueError("A protection device can have only one CT performance model.")
        ct_model_ids = tuple(item.performance_model.id for item in self.ct_performance_bindings)
        if len(ct_model_ids) != len(set(ct_model_ids)):
            raise ValueError("CT performance model IDs must be unique.")
        if not set(ct_device_ids).issubset(set(binding_ids)):
            raise ValueError("CT performance bindings must reference known protection devices.")

    @property
    def binding_by_device_id(self) -> Mapping[UUID, ProtectionDeviceBinding]:
        return MappingProxyType({item.id: item for item in self.bindings})

    @property
    def roles_by_device_id(self) -> Mapping[UUID, tuple[ProtectionRole, ...]]:
        """Return the primary/backup roles assigned to each device across all zones."""
        roles: dict[UUID, set[ProtectionRole]] = {}
        for zone in self.zones:
            for device_id in zone.primary_device_ids:
                roles.setdefault(device_id, set()).add(ProtectionRole.PRIMARY)
            for device_id in zone.backup_device_ids:
                roles.setdefault(device_id, set()).add(ProtectionRole.BACKUP)
        return MappingProxyType(
            {
                device_id: tuple(
                    role
                    for role in (ProtectionRole.PRIMARY, ProtectionRole.BACKUP)
                    if role in device_roles
                )
                for device_id, device_roles in roles.items()
            }
        )


@dataclass(frozen=True, slots=True)
class ProtectionFaultScenario:
    """A topology-derived fault location to be solved by the electrical engine."""

    name: str
    location_kind: ProtectionFaultLocationKind
    location_id: UUID
    fault_type: FaultType
    current_case: IEC60909CurrentCase | None = None
    fraction_from: float | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Scenario name cannot be empty.")
        if not isinstance(self.location_kind, ProtectionFaultLocationKind):
            raise TypeError("location_kind must be a ProtectionFaultLocationKind.")
        if not isinstance(self.location_id, UUID):
            raise TypeError("location_id must be a UUID.")
        if not isinstance(self.fault_type, FaultType):
            raise TypeError("fault_type must be a FaultType.")
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if self.location_kind is ProtectionFaultLocationKind.BUS:
            if not isinstance(self.current_case, IEC60909CurrentCase):
                raise TypeError("Bus-fault scenarios require an IEC60909 current case.")
            if self.fraction_from is not None:
                raise ValueError("Bus-fault scenarios cannot declare fraction_from.")
        else:
            if self.current_case is not None:
                raise ValueError("Interior-line scenarios are not labeled as IEC 60909 cases.")
            if self.fraction_from is None or isinstance(self.fraction_from, bool):
                raise TypeError("Interior-line scenarios require a numeric fraction_from.")
            if not isinstance(self.fraction_from, Real):
                raise TypeError("fraction_from must be a real numeric value.")
            fraction = float(self.fraction_from)
            if not math.isfinite(fraction) or not 0.0 < fraction < 1.0:
                raise ValueError("fraction_from must be between zero and one.")
            object.__setattr__(self, "fraction_from", fraction)
        object.__setattr__(self, "name", self.name.strip())


@dataclass(frozen=True, slots=True)
class ProtectionCurrentMeasurement:
    """Primary RMS current magnitudes seen by a phase or earth element."""

    phase_current_a: float
    earth_current_a: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "phase_current_a", _non_negative(self.phase_current_a, "phase_current_a")
        )
        object.__setattr__(
            self, "earth_current_a", _non_negative(self.earth_current_a, "earth_current_a")
        )


@dataclass(frozen=True, slots=True)
class ProtectionScenarioMeasurements:
    """Measured device currents for one planned fault scenario."""

    scenario: ProtectionFaultScenario
    device_currents_a: Mapping[UUID, ProtectionCurrentMeasurement]

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, ProtectionFaultScenario):
            raise TypeError("scenario must be a ProtectionFaultScenario.")
        if not isinstance(self.device_currents_a, Mapping):
            raise TypeError("device_currents_a must be a mapping.")
        copied: dict[UUID, ProtectionCurrentMeasurement] = {}
        for device_id, measurement in self.device_currents_a.items():
            if not isinstance(device_id, UUID):
                raise TypeError("Measurement keys must be protection-device UUIDs.")
            if not isinstance(measurement, ProtectionCurrentMeasurement):
                raise TypeError("Measurement values must be ProtectionCurrentMeasurement values.")
            copied[device_id] = measurement
        object.__setattr__(self, "device_currents_a", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class ProtectionDeviceOperation:
    scenario_id: UUID
    device_id: UUID
    measured_current_a: float | None
    picked_up: bool | None
    stage: ProtectionStage | None
    operating_time_s: float | None
    clearing_time_s: float | None
    diagnostics: tuple[DomainDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, UUID) or not isinstance(self.device_id, UUID):
            raise TypeError("scenario_id and device_id must be UUID values.")
        if self.measured_current_a is not None:
            object.__setattr__(
                self,
                "measured_current_a",
                _non_negative(self.measured_current_a, "measured_current_a"),
            )
        if self.picked_up is not None and not isinstance(self.picked_up, bool):
            raise TypeError("picked_up must be bool or None.")
        if self.stage is not None and not isinstance(self.stage, ProtectionStage):
            raise TypeError("stage must be a ProtectionStage or None.")
        for name in ("operating_time_s", "clearing_time_s"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_negative(value, name))
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of DomainDiagnostic values.")


@dataclass(frozen=True, slots=True)
class ProtectionBackupCheck:
    primary_device_id: UUID
    backup_device_id: UUID
    minimum_required_margin_s: float
    achieved_margin_s: float | None
    status: ProtectionAssessmentStatus

    def __post_init__(self) -> None:
        if not isinstance(self.primary_device_id, UUID) or not isinstance(
            self.backup_device_id, UUID
        ):
            raise TypeError("Backup-check device IDs must be UUID values.")
        object.__setattr__(
            self,
            "minimum_required_margin_s",
            _non_negative(self.minimum_required_margin_s, "minimum_required_margin_s"),
        )
        if self.achieved_margin_s is not None:
            value = float(self.achieved_margin_s)
            if not math.isfinite(value):
                raise ValueError("achieved_margin_s must be finite.")
            object.__setattr__(self, "achieved_margin_s", value)
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")


@dataclass(frozen=True, slots=True)
class ProtectionZoneScenarioAssessment:
    scenario_id: UUID
    zone_id: UUID
    status: ProtectionAssessmentStatus
    primary_coverage: ProtectionAssessmentStatus
    backup_checks: tuple[ProtectionBackupCheck, ...]
    diagnostics: tuple[DomainDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, UUID) or not isinstance(self.zone_id, UUID):
            raise TypeError("scenario_id and zone_id must be UUID values.")
        if not isinstance(self.status, ProtectionAssessmentStatus) or not isinstance(
            self.primary_coverage, ProtectionAssessmentStatus
        ):
            raise TypeError("Assessment statuses must be ProtectionAssessmentStatus values.")
        if not isinstance(self.backup_checks, tuple) or any(
            not isinstance(item, ProtectionBackupCheck) for item in self.backup_checks
        ):
            raise TypeError("backup_checks must be a tuple of ProtectionBackupCheck values.")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of DomainDiagnostic values.")


@dataclass(frozen=True, slots=True)
class ProtectionNetworkAssessment:
    network_id: UUID
    status: ProtectionAssessmentStatus
    scenarios: tuple[ProtectionFaultScenario, ...]
    device_operations: tuple[ProtectionDeviceOperation, ...]
    zone_assessments: tuple[ProtectionZoneScenarioAssessment, ...]
    diagnostics: tuple[DomainDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.network_id, UUID):
            raise TypeError("network_id must be a UUID.")
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")
        for name, expected_type in (
            ("scenarios", ProtectionFaultScenario),
            ("device_operations", ProtectionDeviceOperation),
            ("zone_assessments", ProtectionZoneScenarioAssessment),
            ("diagnostics", DomainDiagnostic),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, expected_type) for item in values
            ):
                raise TypeError(f"{name} must be a tuple of {expected_type.__name__} values.")
