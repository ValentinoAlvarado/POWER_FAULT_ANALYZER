from __future__ import annotations

import copy
import json
from uuid import uuid4

from power_fault_analyzer.application.commands import NetworkWorkspaceCommands
from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.switching_device import SwitchingDeviceKind
from power_fault_analyzer.domain.enums.switching_device import (
    SwitchPosition as DomainSwitchPosition,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)
from power_fault_analyzer.operations import (
    OperatingScenario,
    SwitchPosition,
    analyze_workspace,
    scenario_from_physical_network,
)


def _workspace():
    voltage = Voltage.from_kv(13.8)
    network = Network("Workspace operating overlay")
    first, second = Bus("BUS-A", voltage), Bus("BUS-B", voltage)
    network.add_bus(first)
    network.add_bus(second)
    switch_id = uuid4()
    terminals = (Terminal(switch_id, "A", voltage), Terminal(switch_id, "B", voltage))
    switch = SwitchingDevice(
        id=switch_id, name="CB-A-B", terminals=terminals,
        device_kind=SwitchingDeviceKind.CIRCUIT_BREAKER,
        position=DomainSwitchPosition.CLOSED,
    )
    network.add_equipment(switch)
    network.connect(terminals[0].id, first.id)
    network.connect(terminals[1].id, second.id)
    return NetworkWorkspace(network), switch, first, second


def test_workspace_commands_edit_overlay_without_mutating_physical_switch_or_topology():
    workspace, switch, _first, _second = _workspace()
    commands = NetworkWorkspaceCommands(workspace)
    physical_connections = workspace.network.connections
    scenario = scenario_from_physical_network(workspace.network, "Outage")
    commands.upsert_operating_scenario(scenario)
    commands.set_active_operating_scenario(scenario.scenario_id)
    commands.set_operating_switch_position(scenario.scenario_id, switch.id, SwitchPosition.OPEN)

    result = analyze_workspace(workspace)

    assert result.deenergized_bus_ids
    assert switch.position is DomainSwitchPosition.CLOSED
    assert workspace.network.connections == physical_connections
    assert workspace.active_operating_scenario.switch_positions[switch.id] is SwitchPosition.OPEN


def test_workspace_snapshot_deepcopy_supports_immutable_operating_scenarios():
    workspace, _switch, _first, _second = _workspace()
    scenario = scenario_from_physical_network(workspace.network, "Snapshot")
    workspace.operating_scenarios[scenario.scenario_id] = scenario
    workspace.active_operating_scenario_id = scenario.scenario_id

    duplicate = copy.deepcopy(workspace)

    assert duplicate.active_operating_scenario == scenario
    assert duplicate.operating_scenarios is not workspace.operating_scenarios


def test_operating_scenarios_round_trip_in_network_document(tmp_path):
    workspace, switch, _first, _second = _workspace()
    scenario = OperatingScenario(
        name="Maintenance",
        switch_positions={switch.id: SwitchPosition.OPEN},
    )
    commands = NetworkWorkspaceCommands(workspace)
    commands.upsert_operating_scenario(scenario)
    commands.set_active_operating_scenario(scenario.scenario_id)
    path = JSONNetworkDocumentRepository().save(workspace, tmp_path / "operations.pfan")
    payload = json.loads(path.read_text(encoding="utf-8"))

    loaded = JSONNetworkDocumentRepository().load(path)

    assert payload["schema_version"] == "1.6"
    assert loaded.operating_scenarios[scenario.scenario_id] == scenario
    assert loaded.active_operating_scenario_id == scenario.scenario_id
    assert loaded.network.get_equipment(switch.id).position is DomainSwitchPosition.CLOSED
