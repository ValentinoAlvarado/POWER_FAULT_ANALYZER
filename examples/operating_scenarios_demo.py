"""Demonstrate operating scenarios against PFA's canonical Network aggregate.

The source and branch are topology-only fixture equipment: this example exercises
operational graph semantics, not electrical parameter models or load flow.
Run from the POWER_FAULT_ANALYZER repository root after installing the package.
"""
from __future__ import annotations

import json
from uuid import uuid4

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


class _DemoTopologyEquipment(ElectricalEquipmentBase):
    """Topology-only fixture; deliberately has no electrical parameter model."""

    __slots__ = ()

    def __init__(self, *, equipment_id, name, terminals, family):
        super().__init__(id=equipment_id, name=name, terminals=terminals, family=family)


def build_demo_network() -> tuple[Network, object]:
    voltage = Voltage.from_kv(13.8)
    bus_a, bus_b, bus_c = (
        Bus("BUS-A", voltage),
        Bus("BUS-B", voltage),
        Bus("BUS-C", voltage),
    )
    network = Network("PFA operating scenarios demonstration")
    for bus in (bus_a, bus_b, bus_c):
        network.add_bus(bus)

    source_id = uuid4()
    source_terminal = Terminal(source_id, "GRID", voltage)
    source = _DemoTopologyEquipment(
        equipment_id=source_id,
        name="GRID-EQUIVALENT",
        terminals=(source_terminal,),
        family=EquipmentFamily.SOURCE,
    )
    network.add_equipment(source)
    network.connect(source_terminal.id, bus_a.id)

    line_id = uuid4()
    line_terminals = (
        Terminal(line_id, "FROM", voltage),
        Terminal(line_id, "TO", voltage),
    )
    line = _DemoTopologyEquipment(
        equipment_id=line_id,
        name="LINE-A-B",
        terminals=line_terminals,
        family=EquipmentFamily.TRANSMISSION,
    )
    network.add_equipment(line)
    network.connect(line_terminals[0].id, bus_a.id)
    network.connect(line_terminals[1].id, bus_b.id)

    breaker_id = uuid4()
    breaker_terminals = (
        Terminal(breaker_id, "A", voltage),
        Terminal(breaker_id, "B", voltage),
    )
    breaker = SwitchingDevice(
        id=breaker_id,
        name="CB-B-C",
        terminals=breaker_terminals,
        device_kind=SwitchingDeviceKind.CIRCUIT_BREAKER,
        position=DomainSwitchPosition.CLOSED,
    )
    network.add_equipment(breaker)
    network.connect(breaker_terminals[0].id, bus_b.id)
    network.connect(breaker_terminals[1].id, bus_c.id)
    return network, breaker


def main() -> None:
    network, breaker = build_demo_network()
    service = OperatingTopologyService()
    original_connections = network.connections

    normal = service.analyze(network, OperatingScenario("Normal operation"))
    contingency = service.analyze(
        network,
        OperatingScenario(
            "CB-B-C open",
            switch_positions={breaker.id: SwitchPosition.OPEN},
        ),
    )
    impact = compare_scenarios(normal, contingency)

    print("NORMAL OPERATION")
    print(json.dumps(normal.to_dict(), indent=2, ensure_ascii=False))
    print("\nCONTINGENCY: CB-B-C OPEN")
    print(json.dumps(contingency.to_dict(), indent=2, ensure_ascii=False))
    print("\nSCENARIO IMPACT")
    print(json.dumps(impact.to_dict(), indent=2, ensure_ascii=False))
    print("\nPHYSICAL MODEL PRESERVED:", network.connections == original_connections)
    print("PHYSICAL BREAKER POSITION:", breaker.position.value)


if __name__ == "__main__":
    main()
