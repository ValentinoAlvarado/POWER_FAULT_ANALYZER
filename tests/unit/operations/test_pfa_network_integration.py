from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.electrical_equipment import ElectricalEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.switching_device import (
    SwitchingDeviceKind,
)
from power_fault_analyzer.domain.enums.switching_device import (
    SwitchPosition as DomainSwitchPosition,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.operations import (
    OperatingScenario,
    OperatingTopologyService,
    SwitchPosition,
    compare_scenarios,
)


class _EquipmentStub(ElectricalEquipmentBase):
    __slots__ = ()

    def __init__(
        self,
        *,
        equipment_id: UUID,
        name: str,
        terminals: tuple[Terminal, ...],
        family: EquipmentFamily,
    ) -> None:
        super().__init__(
            id=equipment_id,
            name=name,
            terminals=terminals,
            family=family,
        )


def _build_workspace() -> tuple[NetworkWorkspace, dict[str, object]]:
    voltage = Voltage.from_kv(13.8)
    buses = (
        Bus("BUS-A", voltage),
        Bus("BUS-B", voltage),
        Bus("BUS-C", voltage),
    )
    network = Network("Operations integration fixture")
    for bus in buses:
        network.add_bus(bus)

    source_id = uuid4()
    source_terminal = Terminal(source_id, "GRID", voltage)
    source = _EquipmentStub(
        equipment_id=source_id,
        name="GRID-EQUIVALENT",
        terminals=(source_terminal,),
        family=EquipmentFamily.SOURCE,
    )
    network.add_equipment(source)
    network.connect(source_terminal.id, buses[0].id)

    line_id = uuid4()
    line_terminals = (
        Terminal(line_id, "FROM", voltage),
        Terminal(line_id, "TO", voltage),
    )
    line = _EquipmentStub(
        equipment_id=line_id,
        name="LINE-A-B",
        terminals=line_terminals,
        family=EquipmentFamily.TRANSMISSION,
    )
    network.add_equipment(line)
    network.connect(line_terminals[0].id, buses[0].id)
    network.connect(line_terminals[1].id, buses[1].id)

    switch_id = uuid4()
    switch_terminals = (
        Terminal(switch_id, "A", voltage),
        Terminal(switch_id, "B", voltage),
    )
    switch = SwitchingDevice(
        id=switch_id,
        name="CB-B-C",
        terminals=switch_terminals,
        device_kind=SwitchingDeviceKind.CIRCUIT_BREAKER,
        position=DomainSwitchPosition.CLOSED,
    )
    network.add_equipment(switch)
    network.connect(switch_terminals[0].id, buses[1].id)
    network.connect(switch_terminals[1].id, buses[2].id)
    return NetworkWorkspace(network=network), {
        "buses": buses,
        "source_id": source_id,
        "line_id": line_id,
        "switch_id": switch_id,
        "switch": switch,
    }


def test_real_network_adapter_reads_pfa_equipment_family_and_switch_position() -> None:
    workspace, ids = _build_workspace()
    normal = OperatingTopologyService().analyze_workspace(
        workspace, OperatingScenario("Normal")
    )

    assert normal.energized_bus_ids == {item.id for item in ids["buses"]}
    equipment = {item.equipment_id: item for item in normal.equipment}
    assert equipment[ids["source_id"]].is_source is True
    assert equipment[ids["line_id"]].family == "transmission"
    assert equipment[ids["switch_id"]].switch_position is SwitchPosition.CLOSED


def test_opening_real_pfa_breaker_deenergizes_downstream_bus_without_mutating_network() -> None:
    workspace, ids = _build_workspace()
    physical_connections_before = workspace.network.connections

    result = OperatingTopologyService().analyze_workspace(
        workspace,
        OperatingScenario(
            "CB-B-C open",
            switch_positions={ids["switch_id"]: SwitchPosition.OPEN},
        ),
    )

    assert result.energized_bus_ids == {ids["buses"][0].id, ids["buses"][1].id}
    assert result.deenergized_bus_ids == {ids["buses"][2].id}
    assert len(result.islands) == 2
    assert workspace.network.connections == physical_connections_before
    assert ids["switch"].position is DomainSwitchPosition.CLOSED


def test_out_of_service_line_creates_unenergized_downstream_island() -> None:
    workspace, ids = _build_workspace()
    result = OperatingTopologyService().analyze_workspace(
        workspace,
        OperatingScenario(
            "Line A-B out of service",
            equipment_in_service={ids["line_id"]: False},
        ),
    )

    assert result.energized_bus_ids == {ids["buses"][0].id}
    assert result.deenergized_bus_ids == {ids["buses"][1].id, ids["buses"][2].id}
    assert len(result.islands) == 2


def test_source_disable_does_not_change_physical_connections() -> None:
    workspace, ids = _build_workspace()
    before = workspace.network.connections
    result = OperatingTopologyService().analyze_workspace(
        workspace,
        OperatingScenario("Grid unavailable", source_enabled={ids["source_id"]: False}),
    )

    assert result.energized_bus_ids == frozenset()
    assert result.deenergized_bus_ids == {item.id for item in ids["buses"]}
    assert workspace.network.connections == before


def test_scenario_comparison_reports_real_breaker_outage_impact() -> None:
    workspace, ids = _build_workspace()
    service = OperatingTopologyService()
    normal = service.analyze_workspace(workspace, OperatingScenario("Normal"))
    contingency = service.analyze_workspace(
        workspace,
        OperatingScenario(
            "CB-B-C open",
            switch_positions={ids["switch_id"]: SwitchPosition.OPEN},
        ),
    )

    comparison = compare_scenarios(normal, contingency)

    assert comparison.newly_deenergized_bus_ids == (ids["buses"][2].id,)
    assert comparison.opened_switch_ids == (ids["switch_id"],)
    assert comparison.island_count_delta == 1


def test_switch_override_on_real_non_switch_equipment_is_rejected() -> None:
    workspace, ids = _build_workspace()
    with pytest.raises(ValueError, match="non-switch"):
        OperatingTopologyService().analyze_workspace(
            workspace,
            OperatingScenario(
                "Invalid line switching override",
                switch_positions={ids["line_id"]: SwitchPosition.OPEN},
            ),
        )
