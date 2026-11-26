from uuid import UUID, uuid4

import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.electrical_equipment import (
    ThreeTerminalEquipmentBase,
    TwoTerminalEquipmentBase,
)
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.exceptions.network_exceptions import (
    DuplicateEntityError,
    EntityInUseError,
    EntityNotFoundError,
    TerminalAlreadyConnectedError,
    VoltageIncompatibilityError,
)
from power_fault_analyzer.domain.interfaces.network_contracts import (
    BusContract,
    ElectricalEquipment,
    NetworkAggregate,
)
from power_fault_analyzer.domain.services.network_validation_service import (
    DefaultNetworkValidationService,
)
from power_fault_analyzer.domain.services.voltage_compatibility_policy import (
    NominalVoltageCompatibilityPolicy,
)
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage


class DummyLine(TwoTerminalEquipmentBase):
    def __init__(self, name: str = "LINE-01", voltage_kv: float = 13.8) -> None:
        equipment_id = uuid4()
        voltage = Voltage.from_kv(voltage_kv)
        super().__init__(
            id=equipment_id,
            name=name,
            terminals=(
                Terminal(equipment_id, "FROM", voltage),
                Terminal(equipment_id, "TO", voltage),
            ),
            family=EquipmentFamily.TRANSMISSION,
        )


class DummyThreeWindingTransformer(ThreeTerminalEquipmentBase):
    def __init__(self) -> None:
        equipment_id = uuid4()
        super().__init__(
            id=equipment_id,
            name="TR-3W",
            terminals=(
                Terminal(equipment_id, "HV", Voltage.from_kv(69.0)),
                Terminal(equipment_id, "MV", Voltage.from_kv(13.8)),
                Terminal(equipment_id, "LV", Voltage.from_kv(4.16)),
            ),
            family=EquipmentFamily.TRANSFORMER,
        )


def make_bus(name: str = "BUS-01", voltage_kv: float = 13.8) -> Bus:
    return Bus(name=name, nominal_voltage=Voltage.from_kv(voltage_kv))


def test_network_starts_empty_and_exposes_immutable_snapshots() -> None:
    network = Network("Test Network")
    assert network.name == "Test Network"
    assert network.buses == ()
    assert network.equipment == ()
    assert network.terminals == ()
    assert network.connections == ()


def test_add_bus_and_equipment() -> None:
    network = Network("Test Network")
    bus = make_bus()
    line = DummyLine()

    network.add_bus(bus)
    network.add_equipment(line)

    assert network.get_bus(bus.id) is bus
    assert network.get_equipment(line.id) is line
    assert len(network.terminals) == 2


def test_duplicate_bus_id_is_rejected() -> None:
    network = Network("Test Network")
    bus_id = uuid4()
    network.add_bus(Bus("BUS-01", Voltage.from_kv(13.8), id=bus_id))

    with pytest.raises(DuplicateEntityError):
        network.add_bus(Bus("BUS-02", Voltage.from_kv(13.8), id=bus_id))


def test_duplicate_element_names_are_case_insensitive_across_network() -> None:
    network = Network("Test Network")
    network.add_bus(make_bus("BUS-01"))
    line = DummyLine(name="bus-01")

    with pytest.raises(DuplicateEntityError):
        network.add_equipment(line)


def test_terminal_can_be_connected_to_one_bus() -> None:
    network = Network("Test Network")
    bus = make_bus()
    line = DummyLine()
    network.add_bus(bus)
    network.add_equipment(line)

    connection = network.connect(line.terminal_from.id, bus.id)

    assert connection.terminal_id == line.terminal_from.id
    assert connection.bus_id == bus.id
    assert network.get_connection(line.terminal_from.id) == connection


def test_terminal_cannot_be_connected_twice() -> None:
    network = Network("Test Network")
    bus = make_bus()
    line = DummyLine()
    network.add_bus(bus)
    network.add_equipment(line)
    network.connect(line.terminal_from.id, bus.id)

    with pytest.raises(TerminalAlreadyConnectedError):
        network.connect(line.terminal_from.id, bus.id)


def test_terminal_cannot_connect_to_incompatible_voltage_bus() -> None:
    network = Network("Test Network")
    bus = make_bus(voltage_kv=69.0)
    line = DummyLine(voltage_kv=13.8)
    network.add_bus(bus)
    network.add_equipment(line)

    with pytest.raises(VoltageIncompatibilityError):
        network.connect(line.terminal_from.id, bus.id)


def test_voltage_compatibility_policy_is_injectable() -> None:
    policy = NominalVoltageCompatibilityPolicy(relative_tolerance=0.01)
    network = Network("Test Network", voltage_compatibility_policy=policy)
    bus = make_bus(voltage_kv=13.8)
    line = DummyLine(voltage_kv=13.85)
    network.add_bus(bus)
    network.add_equipment(line)

    connection = network.connect(line.terminal_from.id, bus.id)
    assert connection.bus_id == bus.id


def test_connect_rejects_unknown_bus_or_terminal() -> None:
    network = Network("Test Network")
    bus = make_bus()
    line = DummyLine()
    network.add_bus(bus)
    network.add_equipment(line)

    with pytest.raises(EntityNotFoundError):
        network.connect(line.terminal_from.id, uuid4())
    with pytest.raises(EntityNotFoundError):
        network.connect(uuid4(), bus.id)


def test_disconnect_removes_connection() -> None:
    network = Network("Test Network")
    bus = make_bus()
    line = DummyLine()
    network.add_bus(bus)
    network.add_equipment(line)
    network.connect(line.terminal_from.id, bus.id)

    network.disconnect(line.terminal_from.id)
    assert network.connections == ()


def test_disconnect_unknown_or_unconnected_terminal_fails() -> None:
    network = Network("Test Network")
    with pytest.raises(EntityNotFoundError):
        network.disconnect(uuid4())

    line = DummyLine()
    network.add_equipment(line)
    with pytest.raises(EntityNotFoundError):
        network.disconnect(line.terminal_from.id)


def test_bus_cannot_be_removed_while_connection_references_it() -> None:
    network = Network("Test Network")
    bus = make_bus()
    line = DummyLine()
    network.add_bus(bus)
    network.add_equipment(line)
    network.connect(line.terminal_from.id, bus.id)

    with pytest.raises(EntityInUseError):
        network.remove_bus(bus.id)


def test_unreferenced_bus_can_be_removed() -> None:
    network = Network("Test Network")
    bus = make_bus()
    network.add_bus(bus)
    network.remove_bus(bus.id)
    assert network.buses == ()


def test_removing_equipment_cascades_its_connections_and_terminals() -> None:
    network = Network("Test Network")
    bus_a = make_bus("BUS-A")
    bus_b = make_bus("BUS-B")
    line = DummyLine()
    network.add_bus(bus_a)
    network.add_bus(bus_b)
    network.add_equipment(line)
    network.connect(line.terminal_from.id, bus_a.id)
    network.connect(line.terminal_to.id, bus_b.id)

    network.remove_equipment(line.id)

    assert network.equipment == ()
    assert network.terminals == ()
    assert network.connections == ()


def test_calculation_validation_reports_incomplete_network() -> None:
    network = Network("Draft Network")
    bus = make_bus()
    line = DummyLine()
    network.add_bus(bus)
    network.add_equipment(line)

    diagnostics = DefaultNetworkValidationService().validate_for_calculation(network)
    codes = {item.code for item in diagnostics}

    assert "NET-TERMINAL-UNCONNECTED" in codes


def test_calculation_validation_passes_for_connected_network_structure() -> None:
    network = Network("Connected Network")
    bus_a = make_bus("BUS-A")
    bus_b = make_bus("BUS-B")
    line = DummyLine()
    network.add_bus(bus_a)
    network.add_bus(bus_b)
    network.add_equipment(line)
    network.connect(line.terminal_from.id, bus_a.id)
    network.connect(line.terminal_to.id, bus_b.id)

    assert DefaultNetworkValidationService().validate_for_calculation(network) == ()


def test_three_terminal_equipment_is_supported() -> None:
    network = Network("Three-Winding Network")
    transformer = DummyThreeWindingTransformer()
    buses = (
        make_bus("BUS-HV", 69.0),
        make_bus("BUS-MV", 13.8),
        make_bus("BUS-LV", 4.16),
    )
    for bus in buses:
        network.add_bus(bus)
    network.add_equipment(transformer)

    for terminal, bus in zip(transformer.terminals, buses, strict=True):
        network.connect(terminal.id, bus.id)

    assert len(network.connections) == 3
    assert DefaultNetworkValidationService().validate_for_calculation(network) == ()


def test_concrete_entities_satisfy_structural_protocols() -> None:
    bus = make_bus()
    line = DummyLine()
    assert isinstance(bus, BusContract)
    assert isinstance(line, ElectricalEquipment)


def test_entity_identifiers_are_unique_across_network_entity_kinds() -> None:
    network = Network("Global IDs")
    shared_id = uuid4()
    network.add_bus(Bus("BUS-01", Voltage.from_kv(13.8), id=shared_id))
    equipment_id = shared_id
    voltage = Voltage.from_kv(13.8)
    terminals = (
        Terminal(equipment_id, "A", voltage),
        Terminal(equipment_id, "B", voltage),
    )
    line = DummyLine()
    # Rebuild an equipment object whose identity collides with a registered bus.
    from power_fault_analyzer.domain.entities.electrical_equipment import TwoTerminalEquipmentBase

    class CollidingEquipment(TwoTerminalEquipmentBase):
        def __init__(self) -> None:
            super().__init__(
                id=equipment_id,
                name="COLLISION",
                terminals=terminals,
                family=EquipmentFamily.TRANSMISSION,
            )

    with pytest.raises(DuplicateEntityError):
        network.add_equipment(CollidingEquipment())
    assert line.id not in {item.id for item in network.equipment}


def test_add_equipment_rejects_terminal_id_colliding_with_existing_bus() -> None:
    network = Network("Terminal ID collision")
    shared_id = uuid4()
    network.add_bus(Bus("BUS-01", Voltage.from_kv(13.8), id=shared_id))
    equipment_id = uuid4()
    voltage = Voltage.from_kv(13.8)
    from power_fault_analyzer.domain.entities.electrical_equipment import TwoTerminalEquipmentBase

    class CollidingTerminalEquipment(TwoTerminalEquipmentBase):
        def __init__(self) -> None:
            super().__init__(
                id=equipment_id,
                name="COLLIDING-TERMINAL",
                terminals=(
                    Terminal(equipment_id, "A", voltage, id=shared_id),
                    Terminal(equipment_id, "B", voltage),
                ),
                family=EquipmentFamily.TRANSMISSION,
            )

    with pytest.raises(DuplicateEntityError):
        network.add_equipment(CollidingTerminalEquipment())


def test_remove_bus_rejects_unknown_id() -> None:
    network = Network("Test")
    with pytest.raises(EntityNotFoundError):
        network.remove_bus(uuid4())


def test_get_methods_reject_non_uuid_arguments() -> None:
    network = Network("Test")
    with pytest.raises(TypeError):
        network.get_bus("not-a-uuid")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        network.get_equipment("not-a-uuid")  # type: ignore[arg-type]


def test_add_equipment_rejects_error_level_configuration_diagnostics() -> None:
    from power_fault_analyzer.domain.entities.electrical_equipment import TwoTerminalEquipmentBase
    from power_fault_analyzer.domain.exceptions.network_exceptions import (
        EquipmentConfigurationError,
    )

    class InvalidConfiguredEquipment(TwoTerminalEquipmentBase):
        def __init__(self) -> None:
            equipment_id = uuid4()
            voltage = Voltage.from_kv(13.8)
            super().__init__(
                id=equipment_id,
                name="INVALID-CONFIG",
                terminals=(
                    Terminal(equipment_id, "A", voltage),
                    Terminal(equipment_id, "B", voltage),
                ),
                family=EquipmentFamily.TRANSMISSION,
            )

        def validate_configuration(self) -> tuple[DomainDiagnostic, ...]:
            return (
                DomainDiagnostic(
                    code="EQP-TEST-001",
                    message="Synthetic invalid equipment configuration.",
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=self.id,
                ),
            )

    network = Network("Atomic registration")
    equipment = InvalidConfiguredEquipment()
    with pytest.raises(EquipmentConfigurationError):
        network.add_equipment(equipment)
    assert network.equipment == ()
    assert network.terminals == ()


def test_network_root_id_cannot_be_reused_by_child_entities() -> None:
    network_id = uuid4()
    network = Network("Root ID", id=network_id)
    with pytest.raises(DuplicateEntityError):
        network.add_bus(Bus("BUS-ROOT-ID", Voltage.from_kv(13.8), id=network_id))


def test_protocol_based_equipment_can_be_registered_without_base_class() -> None:
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class PluginEquipment:
        id: UUID
        name: str
        terminals: tuple[Terminal, ...]
        family: EquipmentFamily

        def validate_configuration(self) -> tuple[DomainDiagnostic, ...]:
            return ()

    equipment_id = uuid4()
    voltage = Voltage.from_kv(13.8)
    plugin = PluginEquipment(
        id=equipment_id,
        name="PLUGIN-BRANCH",
        terminals=(
            Terminal(equipment_id, "FROM", voltage),
            Terminal(equipment_id, "TO", voltage),
        ),
        family=EquipmentFamily.TRANSMISSION,
    )
    network = Network("Plugin architecture")
    network.add_equipment(plugin)
    assert network.get_equipment(equipment_id) is plugin


def test_warning_level_equipment_diagnostic_does_not_block_registration() -> None:
    from power_fault_analyzer.domain.entities.electrical_equipment import TwoTerminalEquipmentBase

    class EquipmentWithWarning(TwoTerminalEquipmentBase):
        def __init__(self) -> None:
            equipment_id = uuid4()
            voltage = Voltage.from_kv(13.8)
            super().__init__(
                id=equipment_id,
                name="WARNING-EQUIPMENT",
                terminals=(
                    Terminal(equipment_id, "A", voltage),
                    Terminal(equipment_id, "B", voltage),
                ),
                family=EquipmentFamily.TRANSMISSION,
            )

        def validate_configuration(self) -> tuple[DomainDiagnostic, ...]:
            return (
                DomainDiagnostic(
                    code="EQP-WARN-001",
                    message="Equipment has incomplete optional metadata.",
                    severity=DiagnosticSeverity.WARNING,
                    entity_id=self.id,
                ),
            )

    network = Network("Warning diagnostics")
    equipment = EquipmentWithWarning()
    network.add_equipment(equipment)
    assert network.get_equipment(equipment.id) is equipment


def test_protocol_equipment_can_expose_structural_terminal_objects() -> None:
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class PluginTerminal:
        id: UUID
        equipment_id: UUID
        designation: str
        rated_voltage: Voltage

    @dataclass(frozen=True)
    class PluginEquipment:
        id: UUID
        name: str
        terminals: tuple[PluginTerminal, ...]
        family: EquipmentFamily

        def validate_configuration(self) -> tuple[DomainDiagnostic, ...]:
            return ()

    equipment_id = uuid4()
    voltage = Voltage.from_kv(13.8)
    plugin = PluginEquipment(
        id=equipment_id,
        name="STRUCTURAL-EQUIPMENT",
        terminals=(
            PluginTerminal(uuid4(), equipment_id, "A", voltage),
            PluginTerminal(uuid4(), equipment_id, "B", voltage),
        ),
        family=EquipmentFamily.TRANSMISSION,
    )
    network = Network("Structural terminal contract")
    bus = make_bus()
    network.add_bus(bus)
    network.add_equipment(plugin)
    network.connect(plugin.terminals[0].id, bus.id)
    assert len(network.terminals) == 2
    network.remove_equipment(equipment_id)
    assert network.terminals == ()
    assert network.connections == ()


def test_network_implements_network_aggregate_protocol() -> None:
    network = Network("Protocol conformance")
    assert isinstance(network, NetworkAggregate)
