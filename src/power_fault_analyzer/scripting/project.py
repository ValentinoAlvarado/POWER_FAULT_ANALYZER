"""Programmatic network authoring API backed by the production domain model.

This API deliberately requires explicit sequence data for equivalent sources.
It creates real domain entities through the same transactional workspace command
facade used by the Qt Workbench; it never infers connectivity from geometry.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from power_fault_analyzer.application.commands import NetworkWorkspaceCommands
from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramLabelPlacement,
    NetworkWorkspace,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.switching_device import SwitchingDeviceKind, SwitchPosition
from power_fault_analyzer.domain.services.network_validation_service import (
    DefaultNetworkValidationService,
)
from power_fault_analyzer.domain.value_objects.diagnostic import DiagnosticSeverity
from power_fault_analyzer.equipment.interfaces.unresolved_branch import (
    UnresolvedTwoTerminalEquipment,
)
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import EngineeringParameter
from power_fault_analyzer.equipment.interfaces.unresolved_single_terminal import (
    UnresolvedSingleTerminalEquipment,
)
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice


class ScriptProject:
    """Build a physical network and its diagram layout from a Python script."""

    def __init__(self, name: str = "Untitled Project") -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Project name must be a non-empty string.")
        self.name = name.strip()
        self.workspace = NetworkWorkspace(network=Network(self.name))
        self.commands = NetworkWorkspaceCommands(self.workspace, source="python-automation")
        self._validation = DefaultNetworkValidationService()

    @property
    def network(self) -> Network:
        """Return the current canonical aggregate (including after transaction rollback)."""
        return self.workspace.network

    def move_diagram_element(self, element: Bus | UUID, x: float, y: float) -> None:
        """Move a domain element in presentation space without changing topology."""
        identifier = element.id if isinstance(element, Bus) else element
        self.commands.move_elements({identifier: (x, y)})

    def rotate_bus(self, bus: Bus | UUID, rotation_deg: float) -> float:
        """Rotate a busbar in the diagram only; electrical connections are unchanged."""
        identifier = bus.id if isinstance(bus, Bus) else bus
        return self.commands.rotate_bus(identifier, rotation_deg)

    def set_switch_position(
        self, equipment: SwitchingDevice | UUID, position: SwitchPosition
    ) -> SwitchingDevice:
        """Change switch operating state through the shared application command API."""
        identifier = equipment.id if isinstance(equipment, SwitchingDevice) else equipment
        return self.commands.set_switch_position(identifier, position)

    def add_bus(
        self,
        name: str,
        voltage_kv: float,
        *,
        x: float = 420.0,
        y: float = 260.0,
        kind: BusKind = BusKind.BUSBAR,
    ) -> Bus:
        """Add a bus and its independent drawing coordinates."""
        return self.commands.add_bus(name, voltage_kv, x, y, kind=kind)

    def add_equivalent_source(
        self,
        name: str,
        bus: Bus | UUID,
        *,
        base_mva: float,
        z1_pu: complex,
        z2_pu: complex,
        z0_pu: complex,
        prefault_voltage_pu: complex = 1.0 + 0.0j,
        frequency_hz: float = 60.0,
        x: float | None = None,
        y: float | None = None,
    ) -> EquivalentSource:
        """Add an explicit three-sequence Thevenin source through the shared command bus.

        All sequence impedances are per-unit on ``base_mva`` and the bus
        line-to-line voltage base. No sequence value is assumed or copied.
        """
        target_bus = self.network.get_bus(bus.id if isinstance(bus, Bus) else bus)
        bus_position = self.workspace.diagram_positions.get(target_bus.id, (420.0, 260.0))
        source = self.commands.add_equivalent_source(
            name=name,
            bus_id=target_bus.id,
            base_power_mva=base_mva,
            positive_sequence_pu=z1_pu,
            negative_sequence_pu=z2_pu,
            zero_sequence_pu=z0_pu,
            prefault_voltage_pu=prefault_voltage_pu,
            frequency_hz=frequency_hz,
            position=(
                float(x) if x is not None else bus_position[0] - 170.0,
                float(y) if y is not None else bus_position[1] - 120.0,
            ),
        )
        return source

    def add_switching_device(
        self, name: str, from_bus: Bus | UUID, to_bus: Bus | UUID, *,
        device_kind: SwitchingDeviceKind = SwitchingDeviceKind.CIRCUIT_BREAKER,
        position: SwitchPosition = SwitchPosition.OPEN,
    ) -> SwitchingDevice:
        """Add a real two-terminal switchgear object and explicit bus connections."""
        source_bus = self.network.get_bus(from_bus.id if isinstance(from_bus, Bus) else from_bus)
        target_bus = self.network.get_bus(to_bus.id if isinstance(to_bus, Bus) else to_bus)
        identifier = uuid4()
        terminals = (
            Terminal(identifier, "FROM", source_bus.nominal_voltage),
            Terminal(identifier, "TO", target_bus.nominal_voltage),
        )
        equipment = SwitchingDevice(id=identifier, name=name, terminals=terminals,
                                     device_kind=device_kind, position=position)
        self.commands.register_equipment(
            equipment,
            ((terminals[0].id, source_bus.id), (terminals[1].id, target_bus.id)),
        )
        return equipment

    def add_unresolved_branch(
        self, name: str, from_bus: Bus | UUID, to_bus: Bus | UUID, *,
        equipment_kind: str, family: EquipmentFamily,
        parameters: tuple[tuple[str, str], ...],
    ) -> UnresolvedTwoTerminalEquipment:
        """Add topology-bearing two-terminal equipment without inventing nameplate data."""
        source_bus = self.network.get_bus(from_bus.id if isinstance(from_bus, Bus) else from_bus)
        target_bus = self.network.get_bus(to_bus.id if isinstance(to_bus, Bus) else to_bus)
        identifier = uuid4()
        terminals = (
            Terminal(identifier, "FROM", source_bus.nominal_voltage),
            Terminal(identifier, "TO", target_bus.nominal_voltage),
        )
        evidence = tuple(EngineeringParameter(key, unit) for key, unit in parameters)
        equipment = UnresolvedTwoTerminalEquipment(
            id=identifier, name=name, terminals=terminals,
            equipment_kind=equipment_kind, family=family, parameters=evidence,
        )
        self.commands.register_equipment(
            equipment,
            ((terminals[0].id, source_bus.id), (terminals[1].id, target_bus.id)),
        )
        return equipment

    def add_unresolved_single_terminal_equipment(
        self, name: str, bus: Bus | UUID, *, equipment_kind: str,
        family: EquipmentFamily, parameters: tuple[tuple[str, str], ...],
    ) -> UnresolvedSingleTerminalEquipment:
        """Add a one-terminal placeholder; calculation remains blocked by unresolved data."""
        target_bus = self.network.get_bus(bus.id if isinstance(bus, Bus) else bus)
        identifier = uuid4()
        terminal = Terminal(identifier, "TERMINAL", target_bus.nominal_voltage)
        evidence = tuple(EngineeringParameter(key, unit) for key, unit in parameters)
        equipment = UnresolvedSingleTerminalEquipment(
            id=identifier, name=name, terminal=terminal,
            equipment_kind=equipment_kind, family=family, parameters=evidence,
        )
        self.commands.register_equipment(equipment, ((terminal.id, target_bus.id),))
        return equipment

    def set_diagram_label(
        self,
        owner: Bus | UUID,
        role: str,
        text: str,
        *,
        x: float,
        y: float,
        anchor: str = "middle",
        font_family: str = "Segoe UI",
        size_pt: float = 7.5,
        weight: str = "normal",
        color: str = "#172033",
        rotation_deg: float = 0.0,
        visible: bool = True,
        layer: str = "annotations",
        priority: int = 50,
        unit: str | None = None,
        number_format: str | None = None,
    ) -> DiagramLabelPlacement:
        """Create/update an independently editable label on the shared workspace.

        ``role`` is stable across diagram regeneration (for example ``bus-name``,
        ``bus-voltage``, ``equipment-name`` or ``data-warning``). It changes only
        presentation metadata, never a bus/equipment name or an electrical value.
        """
        owner_id = owner.id if isinstance(owner, Bus) else owner
        if not isinstance(owner_id, UUID):
            raise TypeError("owner must be a Bus or UUID.")
        if not isinstance(role, str) or not role.strip():
            raise ValueError("role must be a non-empty string.")
        label_id = uuid5(NAMESPACE_URL, f"urn:pfa:diagram-label:{owner_id}:{role.strip()}")
        label = DiagramLabelPlacement(
            label_id=label_id,
            owner_id=owner_id,
            text=text,
            x=x,
            y=y,
            anchor=anchor,
            font_family=font_family,
            size_pt=size_pt,
            weight=weight,
            color=color,
            rotation_deg=rotation_deg,
            visible=visible,
            layer=layer,
            priority=priority,
            unit=unit,
            number_format=number_format,
        )
        self.commands.upsert_label(label)
        return label

    def add_annotation(
        self,
        text: str,
        x: float,
        y: float,
        *,
        anchor: str = "start",
        font_family: str = "Segoe UI",
        size_pt: float = 7.5,
        weight: str = "normal",
        color: str = "#172033",
        visible: bool = True,
        layer: str = "annotations",
    ) -> DiagramLabelPlacement:
        """Add a free engineering note to the diagram document."""
        label = DiagramLabelPlacement.create(
            text, x, y, anchor=anchor, font_family=font_family,
            size_pt=size_pt, weight=weight, color=color, visible=visible, layer=layer,
        )
        self.commands.upsert_label(label)
        return label

    def validate(self, *, for_calculation: bool = False):
        """Return domain diagnostics; errors are never silently suppressed."""
        if not isinstance(for_calculation, bool):
            raise TypeError("for_calculation must be bool.")
        if for_calculation:
            return self._validation.validate_for_calculation(self.network)
        return self._validation.validate_structure(self.network)

    def assert_valid(self, *, for_calculation: bool = False) -> None:
        diagnostics = self.validate(for_calculation=for_calculation)
        errors = [item for item in diagnostics if item.severity is DiagnosticSeverity.ERROR]
        if errors:
            details = "\\n".join(f"{item.code}: {item.message}" for item in errors)
            raise ValueError(f"Network validation failed:\\n{details}")

    def render(self):
        """Return the application workspace consumed by the desktop renderer."""
        return self.workspace
