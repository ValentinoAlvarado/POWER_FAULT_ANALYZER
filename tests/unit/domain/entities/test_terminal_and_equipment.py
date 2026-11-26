from uuid import uuid4

import pytest

from power_fault_analyzer.domain.entities.electrical_equipment import (
    ThreeTerminalEquipmentBase,
    TwoTerminalEquipmentBase,
)
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.value_objects.voltage import Voltage


class DummyTwoTerminalEquipment(TwoTerminalEquipmentBase):
    def __init__(self, name: str = "LINE-01") -> None:
        equipment_id = uuid4()
        voltage = Voltage.from_kv(13.8)
        terminals = (
            Terminal(equipment_id, "A", voltage),
            Terminal(equipment_id, "B", voltage),
        )
        super().__init__(
            id=equipment_id,
            name=name,
            terminals=terminals,
            family=EquipmentFamily.TRANSMISSION,
        )


class DummyThreeTerminalEquipment(ThreeTerminalEquipmentBase):
    def __init__(self) -> None:
        equipment_id = uuid4()
        voltage = Voltage.from_kv(13.8)
        terminals = (
            Terminal(equipment_id, "HV", voltage),
            Terminal(equipment_id, "MV", voltage),
            Terminal(equipment_id, "LV", voltage),
        )
        super().__init__(id=equipment_id, name="TR-3W", terminals=terminals)


class InvalidOwnerEquipment(TwoTerminalEquipmentBase):
    def __init__(self) -> None:
        equipment_id = uuid4()
        other_id = uuid4()
        voltage = Voltage.from_kv(13.8)
        terminals = (
            Terminal(equipment_id, "A", voltage),
            Terminal(other_id, "B", voltage),
        )
        super().__init__(id=equipment_id, name="INVALID", terminals=terminals)


def test_terminal_requires_valid_owner_and_designation() -> None:
    equipment_id = uuid4()
    terminal = Terminal(equipment_id, "HV", Voltage.from_kv(13.8))
    assert terminal.equipment_id == equipment_id
    assert terminal.designation == "HV"

    with pytest.raises(ValueError):
        Terminal(equipment_id, "  ", Voltage.from_kv(13.8))


def test_terminal_requires_line_to_line_voltage() -> None:
    from power_fault_analyzer.domain.value_objects.voltage import VoltageReference

    with pytest.raises(ValueError, match="line-to-line"):
        Terminal(
            uuid4(),
            "A",
            Voltage.from_kv(7.967, VoltageReference.PHASE_TO_NEUTRAL),
        )


def test_two_terminal_equipment_enforces_exact_cardinality() -> None:
    equipment = DummyTwoTerminalEquipment()
    assert len(equipment.terminals) == 2
    assert equipment.terminal_from.designation == "A"
    assert equipment.terminal_to.designation == "B"
    assert equipment.family is EquipmentFamily.TRANSMISSION


def test_three_terminal_equipment_enforces_exact_cardinality() -> None:
    equipment = DummyThreeTerminalEquipment()
    assert len(equipment.terminals) == 3


def test_equipment_rejects_terminal_with_different_owner() -> None:
    with pytest.raises(ValueError, match="equipment_id"):
        InvalidOwnerEquipment()


def test_equipment_rejects_duplicate_terminal_designations() -> None:
    equipment_id = uuid4()
    voltage = Voltage.from_kv(13.8)
    terminals = (
        Terminal(equipment_id, "A", voltage),
        Terminal(equipment_id, "a", voltage),
    )
    with pytest.raises(ValueError, match="designations must be unique"):
        DummyTwoTerminalEquipment.__mro__[1](
            id=equipment_id,
            name="DUP-DESIGNATION",
            terminals=terminals,
        )


def test_base_equipment_exposes_immutable_terminal_tuple() -> None:
    equipment = DummyTwoTerminalEquipment()
    assert isinstance(equipment.terminals, tuple)
    with pytest.raises(AttributeError):
        equipment.terminals = ()  # type: ignore[misc]
