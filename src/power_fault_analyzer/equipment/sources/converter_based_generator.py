"""Converter-interfaced generation represented by current capability limits."""

from __future__ import annotations

from uuid import UUID

from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.converter_control_mode import (
    ConverterControlMode,
    ConverterCurrentPriority,
)
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.source_models import (
    ConverterFaultCurrentCapability,
)
from power_fault_analyzer.equipment.sources.source_base import SourceEquipmentBase


class ConverterBasedGenerator(SourceEquipmentBase):
    """Converter source; not misrepresented as a fixed Thevenin impedance.

    This class stores the declared current capability and control classification.
    A dynamic control response / fault-current solver is a separate future adapter.
    """

    __slots__ = ("_capability", "_control_mode", "_current_priority")

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminal: Terminal,
        frequency: Frequency,
        control_mode: ConverterControlMode,
        current_priority: ConverterCurrentPriority,
        fault_current_capability: ConverterFaultCurrentCapability,
    ) -> None:
        if not isinstance(terminal, Terminal):
            raise TypeError("terminal must be a Terminal entity.")
        if not isinstance(frequency, Frequency):
            raise TypeError("frequency must be a Frequency value.")
        if not isinstance(control_mode, ConverterControlMode):
            raise TypeError("control_mode must be a ConverterControlMode value.")
        if not isinstance(current_priority, ConverterCurrentPriority):
            raise TypeError("current_priority must be a ConverterCurrentPriority value.")
        if not isinstance(fault_current_capability, ConverterFaultCurrentCapability):
            raise TypeError("fault_current_capability must be ConverterFaultCurrentCapability.")
        tolerance = max(1e-9, terminal.rated_voltage.value_kv * 1e-9)
        if (
            abs(fault_current_capability.base.base_voltage_kv - terminal.rated_voltage.value_kv)
            > tolerance
        ):
            raise ValueError("Converter current base voltage must match terminal rated voltage.")
        super().__init__(
            id=id,
            name=name,
            terminal=terminal,
            frequency=frequency,
            family=EquipmentFamily.CONVERTER,
        )
        self._control_mode = control_mode
        self._current_priority = current_priority
        self._capability = fault_current_capability

    @property
    def control_mode(self) -> ConverterControlMode:
        return self._control_mode

    @property
    def current_priority(self) -> ConverterCurrentPriority:
        return self._current_priority

    @property
    def fault_current_capability(self) -> ConverterFaultCurrentCapability:
        return self._capability
