from __future__ import annotations

from uuid import UUID, uuid4

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
    RestorationPlanner,
    SwitchingSequence,
    SwitchingSequenceService,
    SwitchingSequenceStatus,
    SwitchingStep,
    SwitchPosition,
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
        super().__init__(id=equipment_id, name=name, terminals=terminals, family=family)


def _workspace() -> tuple[NetworkWorkspace, dict[str, object]]:
    voltage = Voltage.from_kv(13.8)
    buses = (Bus("BUS-A", voltage), Bus("BUS-B", voltage), Bus("BUS-C", voltage))
    network = Network("Operations 002 physical preservation fixture")
    for bus in buses:
        network.add_bus(bus)

    source_id = uuid4()
    source_terminal = Terminal(source_id, "GRID", voltage)
    network.add_equipment(
        _EquipmentStub(
            equipment_id=source_id,
            name="GRID",
            terminals=(source_terminal,),
            family=EquipmentFamily.SOURCE,
        )
    )
    network.connect(source_terminal.id, buses[0].id)

    line_id = uuid4()
    line_terminals = (Terminal(line_id, "FROM", voltage), Terminal(line_id, "TO", voltage))
    network.add_equipment(
        _EquipmentStub(
            equipment_id=line_id,
            name="LINE-A-B",
            terminals=line_terminals,
            family=EquipmentFamily.TRANSMISSION,
        )
    )
    network.connect(line_terminals[0].id, buses[0].id)
    network.connect(line_terminals[1].id, buses[1].id)

    breaker_id = uuid4()
    breaker_terminals = (Terminal(breaker_id, "A", voltage), Terminal(breaker_id, "B", voltage))
    breaker = SwitchingDevice(
        id=breaker_id,
        name="CB-B-C",
        terminals=breaker_terminals,
        device_kind=SwitchingDeviceKind.CIRCUIT_BREAKER,
        position=DomainSwitchPosition.CLOSED,
    )
    network.add_equipment(breaker)
    network.connect(breaker_terminals[0].id, buses[1].id)
    network.connect(breaker_terminals[1].id, buses[2].id)
    return NetworkWorkspace(network=network), {
        "buses": buses,
        "breaker": breaker,
        "breaker_id": breaker_id,
        "line_id": line_id,
    }


def test_switching_sequence_changes_scenario_not_physical_device_or_connections() -> None:
    workspace, data = _workspace()
    network = workspace.network
    switch = data["breaker"]
    connections_before = network.connections
    physical_position_before = switch.position
    sequence = SwitchingSequence(
        name="Open CB-B-C for contingency",
        steps=(SwitchingStep(
            equipment_id=data["breaker_id"],
            expected_position=SwitchPosition.CLOSED,
            target_position=SwitchPosition.OPEN,
        ),),
    )

    result = SwitchingSequenceService().simulate(network, sequence)

    assert result.status is SwitchingSequenceStatus.COMPLETED
    assert result.final_topology.deenergized_bus_ids == {data["buses"][2].id}
    assert network.connections == connections_before
    assert switch.position is physical_position_before


def test_restoration_proposal_uses_real_switch_and_restores_deenergized_bus() -> None:
    workspace, data = _workspace()
    network = workspace.network
    connections_before = network.connections
    switch = data["breaker"]
    position_before = switch.position
    contingency = OperatingScenario(
        name="CB-B-C outage",
        switch_positions={data["breaker_id"]: SwitchPosition.OPEN},
    )

    proposal = RestorationPlanner().propose(
        network,
        contingency,
        target_bus_ids=(data["buses"][2].id,),
    )
    simulated = SwitchingSequenceService().simulate(network, proposal.sequence)

    assert proposal.complete_for_target
    assert proposal.restored_bus_ids == (data["buses"][2].id,)
    assert simulated.status is SwitchingSequenceStatus.COMPLETED
    assert network.connections == connections_before
    assert switch.position is position_before


def test_sequence_can_be_replayed_from_a_json_compatible_scenario_contract() -> None:
    workspace, data = _workspace()
    scenario = OperatingScenario(
        name="Restoration base",
        switch_positions={data["breaker_id"]: SwitchPosition.OPEN},
    )
    cloned = OperatingScenario.from_dict(scenario.to_dict())
    result = SwitchingSequenceService().simulate(
        workspace.network,
        SwitchingSequence(
            name="Reclose CB-B-C",
            initial_scenario=cloned,
            steps=(SwitchingStep(
                data["breaker_id"], SwitchPosition.OPEN, SwitchPosition.CLOSED
            ),),
        ),
    )
    assert result.status is SwitchingSequenceStatus.COMPLETED
    assert result.final_topology.energized_bus_ids == {item.id for item in data["buses"]}
