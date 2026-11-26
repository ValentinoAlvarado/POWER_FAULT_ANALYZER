"""Transactional commands for the shared electrical/diagram workspace.

Commands operate on the same NetworkWorkspace instance used by the desktop
Workbench and the Python authoring API.  Presentation commands never infer or
modify electrical connectivity.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol, runtime_checkable
from uuid import UUID

from power_fault_analyzer.application.use_cases.network_editing import (
    AddLineBetweenBuses,
    AddSynchronousGeneratorToNetwork,
    AddTheveninEquivalentSourceToNetwork,
    LineInput,
    RemoveBusFromNetwork,
    RemoveEquipmentFromNetwork,
    SetSwitchPosition,
    SynchronousGeneratorInput,
    UpdateBusInNetwork,
)
from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramLabelPlacement,
    DiagramSymbolPlacement,
    NetworkWorkspace,
)
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.switching_device import SwitchPosition
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.interfaces.network_contracts import ElectricalEquipment
from power_fault_analyzer.domain.value_objects.voltage import Voltage


@runtime_checkable
class WorkspaceCommand(Protocol):
    """A named operation that can be committed against a NetworkWorkspace."""

    @property
    def name(self) -> str: ...

    def execute(self, workspace: NetworkWorkspace): ...


@dataclass(frozen=True, slots=True)
class MoveDiagramElements:
    """Move one or more domain elements in presentation space only."""

    positions: tuple[tuple[UUID, float, float], ...]
    name: str = "Move diagram elements"

    def __post_init__(self) -> None:
        if not self.positions:
            raise ValueError("At least one diagram position is required.")
        identifiers: set[UUID] = set()
        normalized: list[tuple[UUID, float, float]] = []
        for identifier, x, y in self.positions:
            if not isinstance(identifier, UUID):
                raise TypeError("Diagram element identifiers must be UUID values.")
            if identifier in identifiers:
                raise ValueError("A diagram element can only be moved once per command.")
            coordinates = (float(x), float(y))
            if not all(isfinite(value) and abs(value) < 1e9 for value in coordinates):
                raise ValueError("Diagram positions must be finite and bounded.")
            identifiers.add(identifier)
            normalized.append((identifier, coordinates[0], coordinates[1]))
        object.__setattr__(self, "positions", tuple(normalized))

    def execute(self, workspace: NetworkWorkspace) -> dict[UUID, tuple[float, float]]:
        allowed = {item.id for item in workspace.network.buses} | {
            item.id for item in workspace.network.equipment
        }
        missing = tuple(
            identifier
            for identifier, _x, _y in self.positions
            if identifier not in allowed
        )
        if missing:
            raise KeyError(f"Unknown diagram element(s): {', '.join(map(str, missing))}.")
        previous = {
            identifier: workspace.diagram_positions.get(identifier)
            for identifier, _, _ in self.positions
        }
        for identifier, x, y in self.positions:
            workspace.diagram_positions[identifier] = (x, y)
        return previous


@dataclass(frozen=True, slots=True)
class RemoveDiagramPosition:
    """Remove an explicit scene position and restore automatic layout placement."""

    element_id: UUID
    name: str = "Restore automatic diagram position"

    def execute(self, workspace: NetworkWorkspace) -> tuple[float, float]:
        if not isinstance(self.element_id, UUID):
            raise TypeError("element_id must be a UUID.")
        try:
            return workspace.diagram_positions.pop(self.element_id)
        except KeyError as exc:
            raise KeyError(f"No explicit diagram position exists for '{self.element_id}'.") from exc


@dataclass(frozen=True, slots=True)
class RemoveDiagramRotation:
    """Remove an explicit bus rotation and restore the default orientation."""

    bus_id: UUID
    name: str = "Restore automatic bus orientation"

    def execute(self, workspace: NetworkWorkspace) -> float:
        if not isinstance(self.bus_id, UUID):
            raise TypeError("bus_id must be a UUID.")
        try:
            return workspace.diagram_rotations.pop(self.bus_id)
        except KeyError as exc:
            raise KeyError(f"No explicit diagram rotation exists for '{self.bus_id}'.") from exc


@dataclass(frozen=True, slots=True)
class MoveDiagramSymbol:
    instance_id: UUID
    x: float
    y: float
    rotation_deg: float | None = None
    label: str | None = None
    name: str = "Move diagram symbol"

    def execute(self, workspace: NetworkWorkspace) -> DiagramSymbolPlacement:
        return workspace.update_diagram_symbol(
            self.instance_id,
            x=self.x,
            y=self.y,
            rotation_deg=self.rotation_deg,
            label=self.label,
        )


@dataclass(frozen=True, slots=True)
class UpsertDiagramSymbol:
    placement: DiagramSymbolPlacement
    name: str = "Update diagram symbol placement"

    def execute(self, workspace: NetworkWorkspace) -> DiagramSymbolPlacement:
        current = workspace.diagram_symbols.get(self.placement.instance_id)
        if current is None:
            workspace.add_diagram_symbol(self.placement)
        else:
            workspace.diagram_symbols[self.placement.instance_id] = self.placement
        return self.placement


@dataclass(frozen=True, slots=True)
class RemoveDiagramSymbol:
    instance_id: UUID
    name: str = "Remove diagram symbol placement"

    def execute(self, workspace: NetworkWorkspace) -> DiagramSymbolPlacement:
        return workspace.remove_diagram_symbol(self.instance_id)


@dataclass(frozen=True, slots=True)
class RotateBusbar:
    bus_id: UUID
    rotation_deg: float
    name: str = "Rotate busbar"

    def execute(self, workspace: NetworkWorkspace) -> float:
        return workspace.update_diagram_rotation(self.bus_id, self.rotation_deg)


@dataclass(frozen=True, slots=True)
class UpsertDiagramLabel:
    label: DiagramLabelPlacement
    name: str = "Update diagram annotation"

    def execute(self, workspace: NetworkWorkspace) -> DiagramLabelPlacement:
        workspace.upsert_diagram_label(self.label)
        return self.label


@dataclass(frozen=True, slots=True)
class RemoveDiagramLabel:
    """Remove a presentation-label override, revealing its generated default."""

    label_id: UUID
    name: str = "Remove diagram annotation override"

    def execute(self, workspace: NetworkWorkspace) -> DiagramLabelPlacement:
        if not isinstance(self.label_id, UUID):
            raise TypeError("label_id must be a UUID.")
        try:
            return workspace.diagram_labels.pop(self.label_id)
        except KeyError as exc:
            raise KeyError(f"Unknown diagram label '{self.label_id}'.") from exc


@dataclass(frozen=True, slots=True)
class SetEquipmentSwitchPosition:
    equipment_id: UUID
    position: SwitchPosition
    name: str = "Set switching device position"

    def execute(self, workspace: NetworkWorkspace):
        return SetSwitchPosition().execute(workspace.network, self.equipment_id, self.position)


@dataclass(frozen=True, slots=True)
class RegisterEquipment:
    """Register a fully constructed domain equipment object and explicit connections."""

    equipment: ElectricalEquipment
    connections: tuple[tuple[UUID, UUID], ...]
    position: tuple[float, float] | None = None
    name: str = "Register electrical equipment"

    def execute(self, workspace: NetworkWorkspace) -> ElectricalEquipment:
        workspace.network.add_equipment(self.equipment)
        for terminal_id, bus_id in self.connections:
            workspace.network.connect(terminal_id, bus_id)
        if self.position is not None:
            x, y = (float(self.position[0]), float(self.position[1]))
            if not isfinite(x) or not isfinite(y):
                raise ValueError("Equipment drawing position must be finite.")
            workspace.diagram_positions[self.equipment.id] = (x, y)
        return self.equipment


@dataclass(frozen=True, slots=True)
class AddTheveninSource:
    name_value: str
    bus_id: UUID
    base_power_mva: float
    positive_sequence_pu: complex
    negative_sequence_pu: complex
    zero_sequence_pu: complex
    prefault_voltage_pu: complex
    frequency_hz: float = 60.0
    position: tuple[float, float] | None = None
    name: str = "Add Thevenin equivalent source"

    def execute(self, workspace: NetworkWorkspace):
        source = AddTheveninEquivalentSourceToNetwork().execute(
            workspace.network,
            name=self.name_value,
            bus_id=self.bus_id,
            base_power_mva=self.base_power_mva,
            positive_sequence_pu=self.positive_sequence_pu,
            negative_sequence_pu=self.negative_sequence_pu,
            zero_sequence_pu=self.zero_sequence_pu,
            prefault_voltage_pu=self.prefault_voltage_pu,
            frequency_hz=self.frequency_hz,
        )
        if self.position is not None:
            workspace.diagram_positions[source.id] = tuple(map(float, self.position))
        return source


@dataclass(frozen=True, slots=True)
class AddSynchronousGenerator:
    specification: SynchronousGeneratorInput
    position: tuple[float, float] | None = None
    name: str = "Add synchronous generator"

    def execute(self, workspace: NetworkWorkspace):
        generator = AddSynchronousGeneratorToNetwork().execute(
            workspace.network, self.specification
        )
        if self.position is not None:
            workspace.diagram_positions[generator.id] = tuple(map(float, self.position))
        return generator


@dataclass(frozen=True, slots=True)
class AddTransmissionLine:
    specification: LineInput
    name: str = "Add transmission line"

    def execute(self, workspace: NetworkWorkspace):
        return AddLineBetweenBuses().execute(workspace.network, self.specification)


@dataclass(frozen=True, slots=True)
class AddBus:
    bus_name: str
    nominal_voltage_kv: float
    x: float
    y: float
    kind: BusKind = BusKind.BUSBAR
    name: str = "Add AC bus"

    def execute(self, workspace: NetworkWorkspace):
        bus = Bus(
            name=self.bus_name,
            nominal_voltage=Voltage.from_kv(self.nominal_voltage_kv),
            kind=self.kind,
        )
        workspace.network.add_bus(bus)
        workspace.diagram_positions[bus.id] = (float(self.x), float(self.y))
        return bus


@dataclass(frozen=True, slots=True)
class UpdateBus:
    bus_id: UUID
    new_name: str
    nominal_voltage_kv: float
    name: str = "Update bus properties"

    def execute(self, workspace: NetworkWorkspace):
        updated = UpdateBusInNetwork().execute(
            workspace.network,
            self.bus_id,
            new_name=self.new_name,
            nominal_voltage_kv=self.nominal_voltage_kv,
        )
        current = workspace.network
        for attribute in Network.__slots__:
            setattr(current, attribute, getattr(updated, attribute))
        return current.get_bus(self.bus_id)


@dataclass(frozen=True, slots=True)
class RemoveBus:
    bus_id: UUID
    name: str = "Remove AC bus"

    def execute(self, workspace: NetworkWorkspace) -> None:
        RemoveBusFromNetwork().execute(workspace.network, self.bus_id)
        workspace.diagram_positions.pop(self.bus_id, None)
        workspace.diagram_rotations.pop(self.bus_id, None)
        for label_id, label in tuple(workspace.diagram_labels.items()):
            if label.owner_id == self.bus_id:
                workspace.diagram_labels.pop(label_id, None)


@dataclass(frozen=True, slots=True)
class RemoveEquipment:
    equipment_id: UUID
    name: str = "Remove electrical equipment"

    def execute(self, workspace: NetworkWorkspace) -> None:
        RemoveEquipmentFromNetwork().execute(workspace.network, self.equipment_id)
        workspace.diagram_positions.pop(self.equipment_id, None)
        for instance_id, placement in tuple(workspace.diagram_symbols.items()):
            if placement.equipment_id == self.equipment_id:
                workspace.diagram_symbols.pop(instance_id, None)
        for label_id, label in tuple(workspace.diagram_labels.items()):
            if label.owner_id == self.equipment_id:
                workspace.diagram_labels.pop(label_id, None)


@dataclass(frozen=True, slots=True)
class SetDiagramGrid:
    spacing: float
    enabled: bool
    name: str = "Set diagram grid"

    def execute(self, workspace: NetworkWorkspace) -> tuple[float, bool]:
        spacing = float(self.spacing)
        if not isfinite(spacing) or not 2.0 <= spacing <= 200.0:
            raise ValueError("grid spacing must be between 2 and 200 scene units.")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool.")
        previous = (workspace.grid_spacing, workspace.snap_enabled)
        workspace.grid_spacing = spacing
        workspace.snap_enabled = self.enabled
        return previous
