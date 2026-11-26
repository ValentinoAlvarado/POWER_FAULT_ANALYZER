"""PFA-ES-001: double-bus 220 kV substation engineering template and validation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramSymbolPlacement,
    NetworkWorkspace,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.equipment_interface import EquipmentInterfaceKind
from power_fault_analyzer.domain.enums.switching_device import SwitchingDeviceKind, SwitchPosition
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    UnresolvedEquipmentInterface,
)
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice

# Terminal UUIDs come from the pinned QElectroTech source assets in
# RESEARCH/qelectrotech-symbol-candidates.csv. They are source graphics pins,
# not IEC terminal designations.
_BREAKER_TOP = "107d9040-63a1-425e-a310-9bfd94db2170"
_BREAKER_BOTTOM = "5caa3d81-f1a0-45b3-ac3f-ecc247f4cc3e"
_DISCONNECTOR_TOP = "0d83daea-f83f-45d2-b1ae-46976aa54b4e"
_DISCONNECTOR_BOTTOM = "2359645e-b42a-4767-ab0f-6444ee8e07a4"
_LINE_YARD_PIN = "98140bcd-cdf9-4d53-97fa-0fb9dc31da92"
_TRANSFORMER_HV_PIN = "509b3f49-5a5e-407e-a737-43aa7eeecb50"


@dataclass(frozen=True, slots=True)
class InterfaceReadiness:
    equipment_id: UUID
    equipment_name: str
    interface_kind: EquipmentInterfaceKind
    unresolved_parameters: tuple[str, ...]
    connected_busbar_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SubstationValidationReport:
    diagnostics: tuple[DomainDiagnostic, ...]
    interfaces: tuple[InterfaceReadiness, ...]
    structurally_valid: bool
    study_ready: bool


@dataclass(frozen=True, slots=True)
class PFAES001BuildResult:
    workspace: NetworkWorkspace
    validation: SubstationValidationReport


class BuildPFAES001Substation:
    """Build a real terminal/switch topology and its QET-sourced one-line view.

    The external line and transformer are represented as one-terminal boundary
    interfaces until their actual nameplate and sequence data are supplied.
    They deliberately block numerical studies; no impedance is fabricated.
    """

    def execute(self) -> PFAES001BuildResult:
        nominal_voltage = Voltage.from_kv(220.0)
        network = Network("PFA-ES-001 · Double-bus 220 kV substation")
        bus_1 = Bus("BB-220-1", nominal_voltage, kind=BusKind.BUSBAR)
        bus_2 = Bus("BB-220-2", nominal_voltage, kind=BusKind.BUSBAR)
        network.add_bus(bus_1)
        network.add_bus(bus_2)

        positions: dict[UUID, tuple[float, float]] = {
            bus_1.id: (600.0, 120.0),
            bus_2.id: (600.0, 780.0),
        }
        columns = {"LINE": 410.0, "TR": 790.0}
        bay_nodes: dict[str, tuple[Bus, Bus, Bus]] = {}
        for prefix, x in columns.items():
            selector = Bus(
                f"N-{prefix}-BUS-SELECTOR", nominal_voltage, kind=BusKind.CONNECTION_NODE
            )
            breaker = Bus(f"N-{prefix}-BREAKER", nominal_voltage, kind=BusKind.CONNECTION_NODE)
            equipment = Bus(f"N-{prefix}-EQUIPMENT", nominal_voltage, kind=BusKind.CONNECTION_NODE)
            for node, y in ((selector, 300.0), (breaker, 450.0), (equipment, 600.0)):
                network.add_bus(node)
                positions[node.id] = (x, y)
            bay_nodes[prefix] = (selector, breaker, equipment)

        symbols: dict[UUID, DiagramSymbolPlacement] = {}
        for prefix, equipment_label, x in (
            ("LINE", "L-220-01", columns["LINE"]),
            ("TR", "TR-220-01", columns["TR"]),
        ):
            selector, breaker_node, equipment_node = bay_nodes[prefix]
            # The order of each switch's domain terminals is explicitly top-to-bottom
            # in the one-line view. A normally open bus selector is kept separate.
            devices = (
                self._add_switch(
                    network,
                    name=f"Q-{prefix}-DS-BB1",
                    top_bus=bus_1,
                    bottom_bus=selector,
                    device_kind=SwitchingDeviceKind.DISCONNECTOR,
                    position=SwitchPosition.CLOSED,
                    asset_id="IEC-DISCONNECTOR",
                    source_pins=(_DISCONNECTOR_TOP, _DISCONNECTOR_BOTTOM),
                    x=x,
                    top_y=120.0,
                    bottom_y=300.0,
                    label=f"Q-{prefix}-DS-BB1",
                ),
                self._add_switch(
                    network,
                    name=f"Q-{prefix}-DS-BB2",
                    top_bus=selector,
                    bottom_bus=bus_2,
                    device_kind=SwitchingDeviceKind.DISCONNECTOR,
                    position=SwitchPosition.OPEN,
                    asset_id="IEC-DISCONNECTOR",
                    source_pins=(_DISCONNECTOR_TOP, _DISCONNECTOR_BOTTOM),
                    x=x,
                    top_y=300.0,
                    bottom_y=780.0,
                    label=f"Q-{prefix}-DS-BB2 (OPEN)",
                ),
                self._add_switch(
                    network,
                    name=f"Q-{prefix}-CB",
                    top_bus=selector,
                    bottom_bus=breaker_node,
                    device_kind=SwitchingDeviceKind.CIRCUIT_BREAKER,
                    position=SwitchPosition.CLOSED,
                    asset_id="IEC-BREAKER",
                    source_pins=(_BREAKER_TOP, _BREAKER_BOTTOM),
                    x=x,
                    top_y=300.0,
                    bottom_y=450.0,
                    label=f"Q-{prefix}-CB",
                ),
                self._add_switch(
                    network,
                    name=f"Q-{prefix}-DS-EQUIPMENT",
                    top_bus=breaker_node,
                    bottom_bus=equipment_node,
                    device_kind=SwitchingDeviceKind.DISCONNECTOR,
                    position=SwitchPosition.CLOSED,
                    asset_id="IEC-DISCONNECTOR",
                    source_pins=(_DISCONNECTOR_TOP, _DISCONNECTOR_BOTTOM),
                    x=x,
                    top_y=450.0,
                    bottom_y=600.0,
                    label=f"Q-{prefix}-DS-EQUIPMENT",
                ),
            )
            for item in devices:
                symbols[item.instance_id] = item

        line_interface = self._add_interface(
            network,
            name="L-220-01 · line-side boundary (model unresolved)",
            interface_kind=EquipmentInterfaceKind.TRANSMISSION_LINE,
            connected_bus=bay_nodes["LINE"][2],
        )
        transformer_interface = self._add_interface(
            network,
            name="TR-220-01 · 220 kV HV boundary (model unresolved)",
            interface_kind=EquipmentInterfaceKind.POWER_TRANSFORMER,
            connected_bus=bay_nodes["TR"][2],
        )
        symbols.update(
            self._add_boundary_symbol(
                line_interface,
                asset_id="IEC-LINE-OVERHEAD",
                source_pin=_LINE_YARD_PIN,
                x=columns["LINE"],
                y=600.0,
                label="L-220-01 · datos de línea pendientes",
                local_pin=(10.0, 30.0),
            )
        )
        symbols.update(
            self._add_boundary_symbol(
                transformer_interface,
                asset_id="IEC-TRAFO-3PH-YD",
                source_pin=_TRANSFORMER_HV_PIN,
                x=columns["TR"],
                y=600.0,
                label="TR-220-01 · datos de placa pendientes",
                local_pin=(56.0, 182.0),
            )
        )

        workspace = NetworkWorkspace(
            network=network,
            diagram_positions=positions,
            diagram_symbols=symbols,
            grid_spacing=20.0,
            snap_enabled=True,
        )
        validation = validate_substation_topology(network)
        return PFAES001BuildResult(workspace=workspace, validation=validation)

    @staticmethod
    def _add_switch(
        network: Network,
        *,
        name: str,
        top_bus: Bus,
        bottom_bus: Bus,
        device_kind: SwitchingDeviceKind,
        position: SwitchPosition,
        asset_id: str,
        source_pins: tuple[str, str],
        x: float,
        top_y: float,
        bottom_y: float,
        label: str,
    ) -> DiagramSymbolPlacement:
        identifier = uuid4()
        terminals = (
            Terminal(identifier, "TOP", top_bus.nominal_voltage),
            Terminal(identifier, "BOTTOM", bottom_bus.nominal_voltage),
        )
        device = SwitchingDevice(
            id=identifier,
            name=name,
            terminals=terminals,
            device_kind=device_kind,
            position=position,
        )
        network.add_equipment(device)
        network.connect(terminals[0].id, top_bus.id)
        network.connect(terminals[1].id, bottom_bus.id)
        placement_y = (top_y + bottom_y) / 2.0 - 40.0
        state_label = f"{label.split(' (', 1)[0]} ({position.value.upper()})"
        placement = DiagramSymbolPlacement.create(
            asset_id,
            x - 11.0,
            placement_y,
            equipment_id=device.id,
            terminal_mappings=(
                (source_pins[0], terminals[0].id),
                (source_pins[1], terminals[1].id),
            ),
            label=state_label,
        )
        return placement

    @staticmethod
    def _add_interface(
        network: Network,
        *,
        name: str,
        interface_kind: EquipmentInterfaceKind,
        connected_bus: Bus,
    ) -> UnresolvedEquipmentInterface:
        identifier = uuid4()
        terminal = Terminal(identifier, "HV-BOUNDARY", connected_bus.nominal_voltage)
        interface = UnresolvedEquipmentInterface(
            id=identifier,
            name=name,
            terminal=terminal,
            interface_kind=interface_kind,
        )
        network.add_equipment(interface)
        network.connect(terminal.id, connected_bus.id)
        return interface

    @staticmethod
    def _add_boundary_symbol(
        interface: UnresolvedEquipmentInterface,
        *,
        asset_id: str,
        source_pin: str,
        x: float,
        y: float,
        label: str,
        local_pin: tuple[float, float],
    ) -> dict[UUID, DiagramSymbolPlacement]:
        # Only the yard-side source pin is mapped. The opposite pin remains an
        # explicit external boundary, not a fabricated remote network terminal.
        placement = DiagramSymbolPlacement.create(
            asset_id,
            x - local_pin[0],
            y - local_pin[1],
            equipment_id=interface.id,
            terminal_mappings=((source_pin, interface.terminals[0].id),),
            label=label,
        )
        return {placement.instance_id: placement}


def validate_substation_topology(network: Network) -> SubstationValidationReport:
    """Validate switch connectivity and evidence readiness without running a solver."""
    diagnostics: list[DomainDiagnostic] = []
    bus_by_id = {item.id: item for item in network.buses}
    connection_by_terminal = {item.terminal_id: item.bus_id for item in network.connections}
    parent = {identifier: identifier for identifier in bus_by_id}

    def find(identifier: UUID) -> UUID:
        while parent[identifier] != identifier:
            parent[identifier] = parent[parent[identifier]]
            identifier = parent[identifier]
        return identifier

    def union(first: UUID, second: UUID) -> None:
        left, right = find(first), find(second)
        if left != right:
            # Stable representative makes reports and sequence-node identifiers reproducible.
            keep, merge = sorted((left, right), key=str)
            parent[merge] = keep

    for equipment in network.equipment:
        if not isinstance(equipment, SwitchingDevice):
            continue
        terminal_buses = [connection_by_terminal.get(item.id) for item in equipment.terminals]
        if any(item is None for item in terminal_buses):
            diagnostics.append(
                DomainDiagnostic(
                    code="ES001-SWITCH-UNCONNECTED-TERMINAL",
                    message=f"Switch '{equipment.name}' has an unconnected terminal.",
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=equipment.id,
                )
            )
            continue
        first, second = terminal_buses
        if bus_by_id[first].nominal_voltage != bus_by_id[second].nominal_voltage:
            diagnostics.append(
                DomainDiagnostic(
                    code="ES001-SWITCH-VOLTAGE-MISMATCH",
                    message=f"Switch '{equipment.name}' connects incompatible voltage levels.",
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=equipment.id,
                )
            )
        if equipment.is_closed:
            union(first, second)

    busbars_by_root: dict[UUID, list[str]] = {}
    for bus in network.buses:
        if bus.kind is BusKind.BUSBAR:
            busbars_by_root.setdefault(find(bus.id), []).append(bus.name)

    interface_results: list[InterfaceReadiness] = []
    for equipment in network.equipment:
        if not isinstance(equipment, UnresolvedEquipmentInterface):
            continue
        connected_bus_id = connection_by_terminal.get(equipment.terminals[0].id)
        connected_busbars = (
            tuple(sorted(busbars_by_root.get(find(connected_bus_id), [])))
            if connected_bus_id is not None
            else ()
        )
        if len(connected_busbars) != 1:
            diagnostics.append(
                DomainDiagnostic(
                    code="ES001-BAY-BUSBAR-SELECTION",
                    message=(
                        f"Interface '{equipment.name}' must be connected to exactly one active "
                        f"busbar; found {len(connected_busbars)}. Check bus-selector positions."
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=equipment.id,
                )
            )
        unresolved = tuple(item.name for item in equipment.unresolved_parameters)
        interface_results.append(
            InterfaceReadiness(
                equipment_id=equipment.id,
                equipment_name=equipment.name,
                interface_kind=equipment.interface_kind,
                unresolved_parameters=unresolved,
                connected_busbar_names=connected_busbars,
            )
        )
        if unresolved:
            diagnostics.append(
                DomainDiagnostic(
                    code="ES001-EQUIPMENT-DATA-UNRESOLVED",
                    message=(
                        f"'{equipment.name}' is not calculation-ready. Missing/conflicting data: "
                        + ", ".join(unresolved)
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=equipment.id,
                )
            )
        else:
            diagnostics.append(
                DomainDiagnostic(
                    code="ES001-EQUIPMENT-ADAPTER-REQUIRED",
                    message=(
                        f"'{equipment.name}' still requires conversion to a concrete electrical "
                        "equipment model before it can be included in a study."
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=equipment.id,
                )
            )

    structural_error_prefixes = (
        "ES001-SWITCH-",
        "ES001-BAY-",
    )
    structural_errors = any(
        item.severity is DiagnosticSeverity.ERROR
        and item.code.startswith(structural_error_prefixes)
        for item in diagnostics
    )
    return SubstationValidationReport(
        diagnostics=tuple(diagnostics),
        interfaces=tuple(interface_results),
        structurally_valid=not structural_errors,
        study_ready=not structural_errors and not interface_results,
    )
