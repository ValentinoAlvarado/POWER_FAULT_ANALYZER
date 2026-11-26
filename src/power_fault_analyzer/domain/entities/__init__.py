"""Electrical domain entities and equipment abstractions."""

from power_fault_analyzer.domain.entities.branch_equipment import BranchEquipmentBase
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.electrical_equipment import (
    ElectricalEquipmentBase,
    ThreeTerminalEquipmentBase,
    TwoTerminalEquipmentBase,
)
from power_fault_analyzer.domain.entities.terminal import Terminal

__all__ = [
    "BranchEquipmentBase",
    "Bus",
    "ElectricalEquipmentBase",
    "Terminal",
    "ThreeTerminalEquipmentBase",
    "TwoTerminalEquipmentBase",
]
