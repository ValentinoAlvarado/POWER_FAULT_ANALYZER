from uuid import uuid4

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.electrical_equipment import TwoTerminalEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.services.network_validation_service import (
    DefaultNetworkValidationService,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage


class DummyLine(TwoTerminalEquipmentBase):
    def __init__(self) -> None:
        equipment_id = uuid4()
        voltage = Voltage.from_kv(13.8)
        super().__init__(
            id=equipment_id,
            name="LINE-01",
            terminals=(
                Terminal(equipment_id, "FROM", voltage),
                Terminal(equipment_id, "TO", voltage),
            ),
            family=EquipmentFamily.TRANSMISSION,
        )


def test_validator_reports_empty_network() -> None:
    network = Network("Empty")
    diagnostics = DefaultNetworkValidationService().validate_for_calculation(network)
    codes = {item.code for item in diagnostics}
    assert "NET-EMPTY-BUS" in codes
    assert "NET-EMPTY-EQUIPMENT" in codes


def test_validator_accepts_connected_network_structure() -> None:
    network = Network("Connected")
    line = DummyLine()
    bus_a = Bus("BUS-A", Voltage.from_kv(13.8))
    bus_b = Bus("BUS-B", Voltage.from_kv(13.8))
    network.add_bus(bus_a)
    network.add_bus(bus_b)
    network.add_equipment(line)
    network.connect(line.terminals[0].id, bus_a.id)
    network.connect(line.terminals[1].id, bus_b.id)

    assert DefaultNetworkValidationService().validate_for_calculation(network) == ()
