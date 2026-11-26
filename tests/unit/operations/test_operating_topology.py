from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from power_fault_analyzer.operations import (
    BusOperatingState,
    BusRecord,
    EquipmentRecord,
    NetworkSnapshot,
    OperatingScenario,
    OperatingScenarioError,
    OperatingTopologyService,
    SwitchPosition,
    TerminalConnection,
    compare_scenarios,
    network_to_snapshot,
)


@dataclass(frozen=True)
class FakeBus:
    id: UUID
    name: str


@dataclass(frozen=True)
class FakeTerminal:
    id: UUID


@dataclass(frozen=True)
class FakeConnection:
    terminal_id: UUID
    bus_id: UUID


@dataclass(frozen=True)
class FakeSwitch:
    id: UUID
    name: str
    terminals: tuple[FakeTerminal, ...]
    device_kind: str
    position: str


@dataclass(frozen=True)
class FakeEquipment:
    id: UUID
    name: str
    terminals: tuple[FakeTerminal, ...]
    equipment_kind: str = "line"
    in_service: bool = True


@dataclass(frozen=True)
class FakeNetwork:
    id: UUID
    name: str
    buses: tuple[FakeBus, ...]
    equipment: tuple[object, ...]
    connections: tuple[FakeConnection, ...]


def uid(value: int) -> UUID:
    return UUID(int=value)


def make_snapshot() -> tuple[NetworkSnapshot, dict[str, UUID]]:
    ids = {name: uid(index) for index, name in enumerate(
        ("network", "b1", "b2", "b3", "source", "line", "switch12", "switch23"), 1
    )}
    terminals = {name: uid(index + 20) for index, name in enumerate(
        ("src", "line1", "line2", "sw12a", "sw12b", "sw23a", "sw23b"), 1
    )}
    snapshot = NetworkSnapshot(
        network_id=ids["network"],
        network_name="Three-bus test network",
        buses=(
            BusRecord(ids["b1"], "BUS-1"),
            BusRecord(ids["b2"], "BUS-2"),
            BusRecord(ids["b3"], "BUS-3"),
        ),
        equipment=(
            EquipmentRecord(ids["source"], "GRID", (terminals["src"],), is_source=True, family="source"),
            EquipmentRecord(ids["line"], "LINE-12", (terminals["line1"], terminals["line2"]), family="line"),
            EquipmentRecord(ids["switch12"], "CB-12", (terminals["sw12a"], terminals["sw12b"]), True, SwitchPosition.CLOSED, family="circuit_breaker"),
            EquipmentRecord(ids["switch23"], "CB-23", (terminals["sw23a"], terminals["sw23b"]), True, SwitchPosition.CLOSED, family="circuit_breaker"),
        ),
        connections=(
            TerminalConnection(terminals["src"], ids["b1"]),
            TerminalConnection(terminals["line1"], ids["b1"]),
            TerminalConnection(terminals["line2"], ids["b2"]),
            TerminalConnection(terminals["sw12a"], ids["b1"]),
            TerminalConnection(terminals["sw12b"], ids["b2"]),
            TerminalConnection(terminals["sw23a"], ids["b2"]),
            TerminalConnection(terminals["sw23b"], ids["b3"]),
        ),
    )
    return snapshot, {**ids, **terminals}


def test_normal_scenario_energizes_all_buses_and_keeps_one_island():
    snapshot, _ = make_snapshot()
    result = OperatingTopologyService().analyze_snapshot(snapshot, OperatingScenario("Normal"))
    assert result.energized_bus_ids == {uid(2), uid(3), uid(4)}
    assert result.deenergized_bus_ids == set()
    assert len(result.islands) == 1
    assert result.islands[0].energized is True


def test_opening_coupler_separates_bus_3_and_reports_deenergized_island():
    snapshot, ids = make_snapshot()
    scenario = OperatingScenario("CB-23 open", switch_positions={ids["switch23"]: SwitchPosition.OPEN})
    result = OperatingTopologyService().analyze_snapshot(snapshot, scenario)
    assert result.energized_bus_ids == {ids["b1"], ids["b2"]}
    assert result.deenergized_bus_ids == {ids["b3"]}
    assert len(result.islands) == 2
    assert any(item.code == "UNENERGIZED_ISLAND" for item in result.diagnostics)


def test_opening_first_switch_is_not_bypassed_by_parallel_line_when_line_connects_same_buses():
    snapshot, ids = make_snapshot()
    scenario = OperatingScenario("parallel path", switch_positions={ids["switch12"]: SwitchPosition.OPEN})
    result = OperatingTopologyService().analyze_snapshot(snapshot, scenario)
    # LINE-12 remains closed/in-service, so BUS-1 and BUS-2 remain connected.
    assert result.energized_bus_ids == {ids["b1"], ids["b2"], ids["b3"]}
    assert len(result.islands) == 1


def test_out_of_service_line_and_open_switch_split_bus_2_from_source():
    snapshot, ids = make_snapshot()
    scenario = OperatingScenario(
        "line unavailable and coupler open",
        equipment_in_service={ids["line"]: False},
        switch_positions={ids["switch12"]: SwitchPosition.OPEN},
    )
    result = OperatingTopologyService().analyze_snapshot(snapshot, scenario)
    assert result.energized_bus_ids == {ids["b1"]}
    assert result.deenergized_bus_ids == {ids["b2"], ids["b3"]}


def test_disabling_source_deenergizes_all_buses_without_changing_island_count():
    snapshot, ids = make_snapshot()
    result = OperatingTopologyService().analyze_snapshot(
        snapshot,
        OperatingScenario("No grid", source_enabled={ids["source"]: False}),
    )
    assert result.energized_bus_ids == set()
    assert result.deenergized_bus_ids == {ids["b1"], ids["b2"], ids["b3"]}
    assert len(result.islands) == 1


def test_scenario_is_immutable_and_does_not_mutate_snapshot():
    snapshot, ids = make_snapshot()
    positions = {ids["switch23"]: SwitchPosition.OPEN}
    scenario = OperatingScenario("Open tie", switch_positions=positions)
    positions[ids["switch23"]] = SwitchPosition.CLOSED
    result = OperatingTopologyService().analyze_snapshot(snapshot, scenario)
    assert result.open_switch_ids == {ids["switch23"]}
    assert snapshot.equipment[-1].default_switch_position is SwitchPosition.CLOSED


def test_unknown_equipment_override_is_rejected():
    snapshot, _ = make_snapshot()
    with pytest.raises(OperatingScenarioError, match="unknown equipment"):
        OperatingTopologyService().analyze_snapshot(
            snapshot, OperatingScenario("Bad", equipment_in_service={uuid4(): False})
        )


def test_switch_override_on_line_is_rejected():
    snapshot, ids = make_snapshot()
    with pytest.raises(OperatingScenarioError, match="non-switch"):
        OperatingTopologyService().analyze_snapshot(
            snapshot,
            OperatingScenario("Bad", switch_positions={ids["line"]: SwitchPosition.OPEN}),
        )


def test_source_override_on_non_source_is_rejected():
    snapshot, ids = make_snapshot()
    with pytest.raises(OperatingScenarioError, match="non-source"):
        OperatingTopologyService().analyze_snapshot(
            snapshot, OperatingScenario("Bad", source_enabled={ids["line"]: False})
        )


def test_result_serializes_to_json_with_summary_and_identifiers():
    snapshot, _ = make_snapshot()
    result = OperatingTopologyService().analyze_snapshot(snapshot, OperatingScenario("Normal"))
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["summary"]["energized_bus_count"] == 3
    assert payload["scenario"]["name"] == "Normal"


def test_scenario_comparison_reports_bus_outage_and_switch_action():
    snapshot, ids = make_snapshot()
    service = OperatingTopologyService()
    normal = service.analyze_snapshot(snapshot, OperatingScenario("Normal"))
    contingency = service.analyze_snapshot(
        snapshot, OperatingScenario("Tie open", switch_positions={ids["switch23"]: SwitchPosition.OPEN})
    )
    comparison = compare_scenarios(normal, contingency)
    assert comparison.newly_deenergized_bus_ids == (ids["b3"],)
    assert comparison.opened_switch_ids == (ids["switch23"],)
    assert comparison.island_count_delta == 1


def test_comparison_rejects_different_physical_networks():
    first, _ = make_snapshot()
    second = NetworkSnapshot(uuid4(), "other", first.buses, first.equipment, first.connections)
    service = OperatingTopologyService()
    with pytest.raises(ValueError, match="different physical networks"):
        compare_scenarios(
            service.analyze_snapshot(first, OperatingScenario("A")),
            service.analyze_snapshot(second, OperatingScenario("B")),
        )


def test_adapter_reads_switch_position_and_recognizes_equivalent_source():
    buses = (FakeBus(uid(101), "BUS-A"), FakeBus(uid(102), "BUS-B"))
    source = FakeEquipment(uid(103), "GRID", (FakeTerminal(uid(201)),), "source")
    switch = FakeSwitch(
        uid(104), "CB-1", (FakeTerminal(uid(202)), FakeTerminal(uid(203))), "circuit_breaker", "closed"
    )
    network = FakeNetwork(
        uid(100), "Adapter fixture", buses, (source, switch),
        (FakeConnection(uid(201), uid(101)), FakeConnection(uid(202), uid(101)), FakeConnection(uid(203), uid(102))),
    )
    snapshot = network_to_snapshot(network)
    assert snapshot.equipment[0].is_source is True
    assert snapshot.equipment[1].is_switch is True
    assert snapshot.equipment[1].default_switch_position is SwitchPosition.CLOSED
    result = OperatingTopologyService().analyze_snapshot(snapshot, OperatingScenario("Adapter"))
    assert result.energized_bus_ids == {uid(101), uid(102)}


def test_explicit_source_ids_support_custom_source_classes():
    bus = FakeBus(uid(301), "BUS-X")
    custom = FakeEquipment(uid(302), "CUSTOM GRID", (FakeTerminal(uid(303)),), "custom_source")
    network = FakeNetwork(uid(300), "Custom source", (bus,), (custom,), (FakeConnection(uid(303), uid(301)),))
    snapshot = network_to_snapshot(network, source_equipment_ids=(custom.id,))
    result = OperatingTopologyService().analyze_snapshot(snapshot, OperatingScenario("Custom"))
    assert result.energized_bus_ids == {bus.id}


def test_snapshot_rejects_duplicate_terminal_connections():
    snapshot, _ = make_snapshot()
    with pytest.raises(ValueError, match="more than one physical bus connection"):
        NetworkSnapshot(
            snapshot.network_id,
            snapshot.network_name,
            snapshot.buses,
            snapshot.equipment,
            (*snapshot.connections, snapshot.connections[0]),
        )


def test_multiterminal_equipment_connects_all_its_connected_buses():
    bus_ids = (uid(401), uid(402), uid(403))
    terminal_ids = (uid(411), uid(412), uid(413))
    snapshot = NetworkSnapshot(
        uid(400), "Three winding transformer abstraction",
        tuple(BusRecord(item, f"BUS-{index}") for index, item in enumerate(bus_ids, 1)),
        (
            EquipmentRecord(uid(420), "GRID", (uid(421),), is_source=True),
            EquipmentRecord(uid(430), "T-3W", terminal_ids, family="transformer"),
        ),
        (
            TerminalConnection(uid(421), bus_ids[0]),
            *(TerminalConnection(terminal, bus) for terminal, bus in zip(terminal_ids, bus_ids, strict=True)),
        ),
    )
    result = OperatingTopologyService().analyze_snapshot(snapshot, OperatingScenario("3W"))
    assert result.energized_bus_ids == set(bus_ids)
    assert len(result.islands) == 1


def test_isolated_bus_is_reported_as_own_deenergized_island():
    snapshot, ids = make_snapshot()
    # Remove the only physical terminal attachment to BUS-3 but retain the bus entity.
    reduced = NetworkSnapshot(
        snapshot.network_id,
        snapshot.network_name,
        snapshot.buses,
        snapshot.equipment,
        tuple(item for item in snapshot.connections if item.bus_id != ids["b3"]),
    )
    result = OperatingTopologyService().analyze_snapshot(reduced, OperatingScenario("Isolated"))
    bus = next(item for item in result.buses if item.bus_id == ids["b3"])
    assert bus.state is BusOperatingState.DEENERGIZED
    assert any(item.code == "UNENERGIZED_ISLAND" and item.entity_id == ids["b3"] for item in result.diagnostics)


def test_closed_grounding_switch_flags_bus_and_reports_hazard_when_bus_is_energized():
    bus_id, source_id, grounding_id = uid(501), uid(502), uid(503)
    source_terminal, ground_terminal = uid(504), uid(505)
    snapshot = NetworkSnapshot(
        uid(500), "Grounding fixture", (BusRecord(bus_id, "BUS-G"),),
        (
            EquipmentRecord(source_id, "GRID", (source_terminal,), is_source=True),
            EquipmentRecord(
                grounding_id, "ES-1", (ground_terminal,), is_switch=True,
                default_switch_position=SwitchPosition.CLOSED, is_grounding_switch=True,
                family="earthing_switch",
            ),
        ),
        (TerminalConnection(source_terminal, bus_id), TerminalConnection(ground_terminal, bus_id)),
    )
    result = OperatingTopologyService().analyze_snapshot(snapshot, OperatingScenario("Grounded live bus"))
    assert result.energized_bus_ids == {bus_id}
    assert result.grounded_bus_ids == {bus_id}
    assert any(item.code == "ENERGIZED_BUS_GROUNDED" for item in result.diagnostics)


def test_open_grounding_switch_does_not_mark_bus_grounded():
    bus_id, source_id, grounding_id = uid(511), uid(512), uid(513)
    source_terminal, ground_terminal = uid(514), uid(515)
    snapshot = NetworkSnapshot(
        uid(510), "Open grounding fixture", (BusRecord(bus_id, "BUS-G"),),
        (
            EquipmentRecord(source_id, "GRID", (source_terminal,), is_source=True),
            EquipmentRecord(
                grounding_id, "ES-1", (ground_terminal,), is_switch=True,
                default_switch_position=SwitchPosition.CLOSED, is_grounding_switch=True,
                family="earthing_switch",
            ),
        ),
        (TerminalConnection(source_terminal, bus_id), TerminalConnection(ground_terminal, bus_id)),
    )
    result = OperatingTopologyService().analyze_snapshot(
        snapshot,
        OperatingScenario("Ground switch open", switch_positions={grounding_id: SwitchPosition.OPEN}),
    )
    assert result.grounded_bus_ids == set()
    assert not any(item.code == "ENERGIZED_BUS_GROUNDED" for item in result.diagnostics)


def test_scenario_json_round_trip_preserves_switch_and_service_overrides():
    _, ids = make_snapshot()
    scenario = OperatingScenario(
        "Saved switching plan",
        switch_positions={ids["switch12"]: SwitchPosition.OPEN},
        equipment_in_service={ids["line"]: False},
        source_enabled={ids["source"]: False},
        description="Planned outage",
    )
    restored = OperatingScenario.from_dict(json.loads(json.dumps(scenario.to_dict())))
    assert restored.scenario_id == scenario.scenario_id
    assert restored.switch_positions == scenario.switch_positions
    assert restored.equipment_in_service == scenario.equipment_in_service
    assert restored.source_enabled == scenario.source_enabled
    assert restored.description == scenario.description


def test_partial_terminal_connection_is_reported_without_mutating_physical_network():
    snapshot, ids = make_snapshot()
    reduced = NetworkSnapshot(
        snapshot.network_id,
        snapshot.network_name,
        snapshot.buses,
        snapshot.equipment,
        tuple(item for item in snapshot.connections if item.terminal_id != ids["line2"]),
    )
    result = OperatingTopologyService().analyze_snapshot(reduced, OperatingScenario("Partial line"))
    assert any(
        item.code == "EQUIPMENT_TERMINAL_UNCONNECTED" and item.entity_id == ids["line"]
        for item in result.diagnostics
    )
