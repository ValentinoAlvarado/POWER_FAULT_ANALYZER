"""Immutable domain models for operating scenarios and topology results.

An operating scenario overlays equipment availability and switching positions on
an unchanged physical Network.  It never mutates the electrical aggregate.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID, uuid4


class SwitchPosition(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class BusOperatingState(StrEnum):
    ENERGIZED = "energized"
    DEENERGIZED = "deenergized"


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _as_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"Serialized {field_name} values must be JSON booleans.")
    return value


@dataclass(frozen=True, slots=True)
class OperatingScenario:
    """A named set of operational overrides over the physical network.

    ``switch_positions`` contains only switch equipment.  Unspecified switches
    retain their position captured from the physical equipment adapter.
    ``equipment_in_service`` defaults to True for unspecified equipment, while
    ``source_enabled`` defaults to True for recognized sources.
    """

    name: str
    scenario_id: UUID = field(default_factory=uuid4)
    switch_positions: Mapping[UUID, SwitchPosition] = field(default_factory=dict)
    equipment_in_service: Mapping[UUID, bool] = field(default_factory=dict)
    source_enabled: Mapping[UUID, bool] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Scenario name must be a non-empty string.")
        for field_name in ("switch_positions", "equipment_in_service", "source_enabled"):
            values = dict(getattr(self, field_name))
            if any(not isinstance(key, UUID) for key in values):
                raise TypeError(f"{field_name} keys must be UUID instances.")
            if field_name == "switch_positions":
                if any(not isinstance(value, SwitchPosition) for value in values.values()):
                    raise TypeError("Switch positions must use SwitchPosition values.")
            elif any(not isinstance(value, bool) for value in values.values()):
                raise TypeError(f"{field_name} values must be booleans.")
            object.__setattr__(self, field_name, MappingProxyType(values))

    def __deepcopy__(self, memo):
        # OperatingScenario is immutable; reusing it keeps NetworkWorkspace
        # transaction snapshots compatible with its MappingProxyType overlays.
        memo[id(self)] = self
        return self

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": str(self.scenario_id),
            "name": self.name,
            "description": self.description,
            "switch_positions": {str(key): value.value for key, value in self.switch_positions.items()},
            "equipment_in_service": {str(key): value for key, value in self.equipment_in_service.items()},
            "source_enabled": {str(key): value for key, value in self.source_enabled.items()},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> OperatingScenario:
        return cls(
            name=str(payload["name"]),
            scenario_id=UUID(str(payload["scenario_id"])),
            description=str(payload.get("description", "")),
            switch_positions={
                UUID(str(key)): SwitchPosition(str(value))
                for key, value in dict(payload.get("switch_positions", {})).items()
            },
            equipment_in_service={
                UUID(str(key)): _as_bool(value, "equipment_in_service")
                for key, value in dict(payload.get("equipment_in_service", {})).items()
            },
            source_enabled={
                UUID(str(key)): _as_bool(value, "source_enabled")
                for key, value in dict(payload.get("source_enabled", {})).items()
            },
        )


@dataclass(frozen=True, slots=True)
class BusRecord:
    bus_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class EquipmentRecord:
    equipment_id: UUID
    name: str
    terminal_ids: tuple[UUID, ...]
    is_switch: bool = False
    default_switch_position: SwitchPosition | None = None
    is_source: bool = False
    is_grounding_switch: bool = False
    default_in_service: bool = True
    family: str = "equipment"

    def __post_init__(self) -> None:
        if len(self.terminal_ids) != len(set(self.terminal_ids)):
            raise ValueError(f"Equipment {self.name!r} contains duplicate terminal identities.")
        if self.is_switch and self.default_switch_position is None:
            raise ValueError(f"Switch {self.name!r} requires a default OPEN/CLOSED position.")
        if self.is_grounding_switch and not self.is_switch:
            raise ValueError("A grounding switch must also be a switching device.")
        if not isinstance(self.default_in_service, bool):
            raise TypeError("default_in_service must be boolean.")


@dataclass(frozen=True, slots=True)
class TerminalConnection:
    terminal_id: UUID
    bus_id: UUID


@dataclass(frozen=True, slots=True)
class NetworkSnapshot:
    """Read-only minimal projection of the PFA physical Network aggregate."""

    network_id: UUID
    network_name: str
    buses: tuple[BusRecord, ...]
    equipment: tuple[EquipmentRecord, ...]
    connections: tuple[TerminalConnection, ...]

    def __post_init__(self) -> None:
        bus_ids = [item.bus_id for item in self.buses]
        equipment_ids = [item.equipment_id for item in self.equipment]
        terminal_ids = [terminal for item in self.equipment for terminal in item.terminal_ids]
        connection_terminal_ids = [item.terminal_id for item in self.connections]
        if len(bus_ids) != len(set(bus_ids)):
            raise ValueError("NetworkSnapshot contains duplicate bus identities.")
        if len(equipment_ids) != len(set(equipment_ids)):
            raise ValueError("NetworkSnapshot contains duplicate equipment identities.")
        if len(terminal_ids) != len(set(terminal_ids)):
            raise ValueError("A terminal identity is owned by more than one equipment.")
        if len(connection_terminal_ids) != len(set(connection_terminal_ids)):
            raise ValueError("A terminal has more than one physical bus connection.")
        unknown_terminals = set(connection_terminal_ids) - set(terminal_ids)
        unknown_buses = {item.bus_id for item in self.connections} - set(bus_ids)
        if unknown_terminals:
            raise ValueError(f"Connections reference unknown terminals: {sorted(map(str, unknown_terminals))}")
        if unknown_buses:
            raise ValueError(f"Connections reference unknown buses: {sorted(map(str, unknown_buses))}")


@dataclass(frozen=True, slots=True)
class OperationalDiagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.WARNING
    entity_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class BusOperatingResult:
    bus_id: UUID
    bus_name: str
    state: BusOperatingState
    island_id: int
    source_reachable: bool
    grounded: bool = False
    grounding_equipment_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class IslandResult:
    island_id: int
    bus_ids: tuple[UUID, ...]
    bus_names: tuple[str, ...]
    energized: bool
    source_equipment_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class EquipmentOperatingResult:
    equipment_id: UUID
    equipment_name: str
    family: str
    in_service: bool
    switch_position: SwitchPosition | None
    connected_bus_ids: tuple[UUID, ...]
    contributes_to_connectivity: bool
    is_source: bool
    source_enabled: bool | None


@dataclass(frozen=True, slots=True)
class OperatingTopologyResult:
    network_id: UUID
    scenario_id: UUID
    scenario_name: str
    buses: tuple[BusOperatingResult, ...]
    islands: tuple[IslandResult, ...]
    equipment: tuple[EquipmentOperatingResult, ...]
    diagnostics: tuple[OperationalDiagnostic, ...]

    @property
    def energized_bus_ids(self) -> frozenset[UUID]:
        return frozenset(item.bus_id for item in self.buses if item.state is BusOperatingState.ENERGIZED)

    @property
    def deenergized_bus_ids(self) -> frozenset[UUID]:
        return frozenset(item.bus_id for item in self.buses if item.state is BusOperatingState.DEENERGIZED)

    @property
    def open_switch_ids(self) -> frozenset[UUID]:
        return frozenset(
            item.equipment_id
            for item in self.equipment
            if item.switch_position is SwitchPosition.OPEN
        )

    @property
    def grounded_bus_ids(self) -> frozenset[UUID]:
        return frozenset(item.bus_id for item in self.buses if item.grounded)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible, deterministic representation."""
        return {
            "network_id": str(self.network_id),
            "scenario": {"id": str(self.scenario_id), "name": self.scenario_name},
            "summary": {
                "bus_count": len(self.buses),
                "energized_bus_count": len(self.energized_bus_ids),
                "deenergized_bus_count": len(self.deenergized_bus_ids),
                "island_count": len(self.islands),
                "energized_island_count": sum(item.energized for item in self.islands),
                "open_switch_count": len(self.open_switch_ids),
                "grounded_bus_count": len(self.grounded_bus_ids),
                "diagnostic_count": len(self.diagnostics),
            },
            "buses": [
                {
                    "id": str(item.bus_id),
                    "name": item.bus_name,
                    "state": item.state.value,
                    "island_id": item.island_id,
                    "source_reachable": item.source_reachable,
                    "grounded": item.grounded,
                    "grounding_equipment_ids": [str(value) for value in item.grounding_equipment_ids],
                }
                for item in self.buses
            ],
            "islands": [
                {
                    "id": item.island_id,
                    "bus_ids": [str(value) for value in item.bus_ids],
                    "bus_names": list(item.bus_names),
                    "energized": item.energized,
                    "source_equipment_ids": [str(value) for value in item.source_equipment_ids],
                }
                for item in self.islands
            ],
            "equipment": [
                {
                    "id": str(item.equipment_id),
                    "name": item.equipment_name,
                    "family": item.family,
                    "in_service": item.in_service,
                    "switch_position": item.switch_position.value if item.switch_position else None,
                    "connected_bus_ids": [str(value) for value in item.connected_bus_ids],
                    "contributes_to_connectivity": item.contributes_to_connectivity,
                    "is_source": item.is_source,
                    "source_enabled": item.source_enabled,
                }
                for item in self.equipment
            ],
            "diagnostics": [
                {
                    "code": item.code,
                    "message": item.message,
                    "severity": item.severity.value,
                    "entity_id": str(item.entity_id) if item.entity_id else None,
                }
                for item in self.diagnostics
            ],
        }
