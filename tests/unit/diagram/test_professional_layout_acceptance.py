from __future__ import annotations

from itertools import pairwise
from uuid import uuid4

import pytest

from examples.canonical_model_scenarios import build_multibus_network
from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.application.use_cases.reference_network_template import (
    BuildReferenceNetworkTemplate,
)
from power_fault_analyzer.application.use_cases.substation_engineering import (
    BuildPFAES001Substation,
)
from power_fault_analyzer.diagram.model_document_export import render_engineering_svg
from power_fault_analyzer.diagram.layout import Point
from power_fault_analyzer.diagram.model_projection import (
    project_network_to_diagram,
    validate_diagram_document,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.equipment_interface import ParameterEvidenceStatus
from power_fault_analyzer.domain.enums.switching_device import SwitchingDeviceKind, SwitchPosition
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.interfaces.unresolved_branch import (
    UnresolvedTwoTerminalEquipment,
)
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import EngineeringParameter
from power_fault_analyzer.equipment.interfaces.unresolved_single_terminal import (
    UnresolvedSingleTerminalEquipment,
)
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice


def _assert_no_label_collisions(document) -> None:
    collisions = [item for item in document.diagnostics if item.startswith("LABEL_COLLISION:")]
    assert collisions == []


def _build_three_feeder_bays() -> NetworkWorkspace:
    network = Network("Automatic three-feeder bay layout")
    nominal = Voltage.from_kv(13.8)
    source = Bus("BUS-MAIN", nominal, kind=BusKind.BUSBAR)
    feeders = [
        Bus(f"FEEDER-{index:02d}", nominal, kind=BusKind.BUSBAR)
        for index in range(1, 4)
    ]
    network.add_bus(source)
    for bus in feeders:
        network.add_bus(bus)
        identifier = uuid4()
        terminals = (
            Terminal(identifier, "FROM", nominal),
            Terminal(identifier, "TO", nominal),
        )
        line = UnresolvedTwoTerminalEquipment(
            id=identifier,
            name=f"LINE-FEEDER-{bus.name[-2:]}",
            terminals=terminals,
            equipment_kind="line",
            family=EquipmentFamily.TRANSMISSION,
            parameters=(EngineeringParameter("length_km", "km"),),
        )
        network.add_equipment(line)
        network.connect(terminals[0].id, source.id)
        network.connect(terminals[1].id, bus.id)
    return NetworkWorkspace(network)


def _build_resolved_and_unresolved_shunts() -> NetworkWorkspace:
    network = Network("Resolved and pending equipment symbols")
    nominal = Voltage.from_kv(13.8)
    bus_a = Bus("BUS-A", nominal, kind=BusKind.BUSBAR)
    bus_b = Bus("BUS-B", nominal, kind=BusKind.BUSBAR)
    network.add_bus(bus_a)
    network.add_bus(bus_b)
    switch_id = uuid4()
    switch_terminals = (
        Terminal(switch_id, "LINE", nominal),
        Terminal(switch_id, "BUS", nominal),
    )
    switch = SwitchingDevice(
        id=switch_id,
        name="CB-RESOLVED",
        terminals=switch_terminals,
        device_kind=SwitchingDeviceKind.CIRCUIT_BREAKER,
        position=SwitchPosition.CLOSED,
    )
    network.add_equipment(switch)
    network.connect(switch_terminals[0].id, bus_a.id)
    network.connect(switch_terminals[1].id, bus_b.id)

    cases = (
        ("LOAD-01", "static_load", EquipmentFamily.LOAD),
        ("CAP-BANK-01", "capacitor_bank", EquipmentFamily.COMPENSATION),
        ("REACTOR-01", "shunt_reactor", EquipmentFamily.COMPENSATION),
        ("SVC-01", "svc", EquipmentFamily.COMPENSATION),
    )
    for name, kind, family in cases:
        identifier = uuid4()
        terminal = Terminal(identifier, "HV", nominal)
        parameters = (
            EngineeringParameter(
                "rated_power_mva", "MVA", 8.0,
                ParameterEvidenceStatus.USER_CONFIRMED, "acceptance fixture",
            ),
            EngineeringParameter("sequence_model", "model"),
        ) if family is EquipmentFamily.LOAD else (
            EngineeringParameter("rated_power_mvar", "MVAr"),
        )
        equipment = UnresolvedSingleTerminalEquipment(
            id=identifier,
            name=name,
            terminal=terminal,
            equipment_kind=kind,
            family=family,
            parameters=parameters,
        )
        network.add_equipment(equipment)
        network.connect(terminal.id, bus_b.id)
    return NetworkWorkspace(network)


def test_reference_case_layout_keeps_explicit_terminal_integrity_and_svg_busbar():
    workspace = BuildReferenceNetworkTemplate().execute().workspace
    document = project_network_to_diagram(workspace)
    assert validate_diagram_document(workspace, document) == ()
    _assert_no_label_collisions(document)
    assert len(document.buses) == 1
    assert document.buses[0].kind == "busbar"
    assert len(document.symbols) == 1
    svg = render_engineering_svg(document)
    assert 'data-family="busbar"' in svg
    assert 'data-family="source"' in svg


def test_pfa_es001_svg_preserves_physical_busbars_and_internal_connection_nodes():
    built = BuildPFAES001Substation().execute()
    document = project_network_to_diagram(built.workspace)
    errors = validate_diagram_document(built.workspace, document)
    if errors:
        relevant_labels = [
            (item.text, item.position, item.anchor)
            for item in document.labels
            if item.text in {"N-TR-BREAKER", "Q-TR-DS-EQUIPMENT (CLOSED)"}
        ]
        pytest.fail(f"Projection validation errors: {errors}; label positions: {relevant_labels}")
    _assert_no_label_collisions(document)
    assert len(document.buses) == 8
    assert sum(item.kind == "busbar" for item in document.buses) == 2
    assert sum(item.kind == "connection_node" for item in document.buses) == 6
    assert len(document.symbols) == 10
    assert len(document.conductors) == 18
    canonical_by_id = {item.equipment_id: item for item in document.symbols}
    mapped_switches = [
        item for item in built.workspace.diagram_symbols.values() if item.equipment_id is not None
    ]
    assert len(mapped_switches) == 8
    for placement in mapped_switches:
        projected = canonical_by_id[placement.equipment_id]
        # QET placement coordinates describe the independent source overlay.
        # Canonical switch contacts follow the actual vertical bay topology.
        assert abs(projected.orientation_deg) == 90.0
        assert projected.center != Point(placement.x, placement.y)
    svg = render_engineering_svg(document)
    assert svg.count('data-family="connection_node"') == 6
    assert "Equipment parameters unresolved" in svg
    assert built.validation.structurally_valid is True
    assert built.validation.study_ready is False


def test_auto_layout_allocates_three_feeder_bays_without_losing_connections():
    workspace = _build_three_feeder_bays()
    document = project_network_to_diagram(workspace)
    assert validate_diagram_document(workspace, document) == ()
    bus_by_name = {item.name: item for item in document.buses}
    main = bus_by_name["BUS-MAIN"]
    feeders = [bus_by_name[f"FEEDER-{index:02d}"] for index in range(1, 4)]
    assert len({round(item.center.x, 3) for item in feeders}) == 3
    assert all(item.center.y > main.center.y for item in feeders)
    lines = [item for item in document.symbols if item.family == "line"]
    assert len(lines) == 3
    assert all(abs(item.orientation_deg) == 90.0 for item in lines)
    lane_centers = sorted(item.center.x for item in lines)
    assert all(right - left >= 200.0 for left, right in pairwise(lane_centers))
    assert document.connection_pairs == frozenset(
        (item.terminal_id, item.bus_id) for item in workspace.network.connections
    )


def test_multibus_automatic_layout_and_unresolved_equipment_remain_bijective():
    workspace = build_multibus_network()
    document = project_network_to_diagram(workspace)
    assert validate_diagram_document(workspace, document) == ()
    assert document.equipment_ids == frozenset(item.id for item in workspace.network.equipment)
    assert document.terminal_ids == frozenset(
        terminal.id for item in workspace.network.equipment for terminal in item.terminals
    )
    assert document.connection_pairs == frozenset(
        (item.terminal_id, item.bus_id) for item in workspace.network.connections
    )


def test_load_and_compensation_families_have_distinct_glyphs_and_unresolved_state():
    workspace = _build_resolved_and_unresolved_shunts()
    document = project_network_to_diagram(workspace)
    assert validate_diagram_document(workspace, document) == ()
    by_name = {item.name: item for item in document.symbols}
    assert by_name["CB-RESOLVED"].state == "closed"
    assert by_name["LOAD-01"].family == "load"
    assert by_name["LOAD-01"].state == "partial-data"
    assert by_name["CAP-BANK-01"].family == "capacitor"
    assert by_name["CAP-BANK-01"].state == "unresolved"
    assert by_name["REACTOR-01"].family == "reactor"
    assert by_name["SVC-01"].family == "compensation"
    svg = render_engineering_svg(document)
    assert 'data-family="load" data-model-state="partial-data"' in svg
    assert 'data-family="capacitor" data-model-state="unresolved"' in svg
    assert 'data-family="reactor" data-model-state="unresolved"' in svg
    assert 'data-family="compensation" data-model-state="unresolved"' in svg
    assert "Equipment parameters unresolved" in svg


def test_rotated_busbar_bounds_are_not_rotated_twice_in_svg():
    source = BuildReferenceNetworkTemplate().execute().workspace
    bus = source.network.buses[0]
    workspace = NetworkWorkspace(
        network=source.network,
        diagram_positions=dict(source.diagram_positions),
        diagram_rotations={bus.id: 90.0},
        grid_spacing=source.grid_spacing,
        snap_enabled=source.snap_enabled,
    )
    document = project_network_to_diagram(workspace)
    projected_bus = document.buses[0]
    assert projected_bus.bounds.height > projected_bus.bounds.width
    svg = render_engineering_svg(document)
    bus_group = svg.split(f'id="equipment-{bus.id}"', 1)[1].split("</g>", 1)[0]
    assert 'transform="translate(' in bus_group
    assert 'rotate(0)' in bus_group


def test_svg_model_state_is_separate_from_switch_operating_position():
    workspace = _build_resolved_and_unresolved_shunts()
    document = project_network_to_diagram(workspace)
    svg = render_engineering_svg(document)
    switch = next(item for item in document.symbols if item.name == "CB-RESOLVED")
    group = svg.split(f'id="equipment-{switch.equipment_id}"', 1)[1].split("</g>", 1)[0]
    assert 'data-model-state="resolved"' in group
    assert switch.state == "closed"
