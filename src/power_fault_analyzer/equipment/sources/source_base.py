"""Shared one-terminal source equipment base class."""

from __future__ import annotations

from abc import ABC
from uuid import UUID

from power_fault_analyzer.domain.entities.electrical_equipment import ElectricalEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.value_objects.frequency import Frequency


class SourceEquipmentBase(ElectricalEquipmentBase, ABC):
    """Base for one-terminal equipment injecting power into a network bus."""

    __slots__ = ("_frequency",)

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminal: Terminal,
        frequency: Frequency,
        family: EquipmentFamily = EquipmentFamily.SOURCE,
    ) -> None:
        if not isinstance(terminal, Terminal):
            raise TypeError("terminal must be a Terminal entity.")
        if not isinstance(frequency, Frequency):
            raise TypeError("frequency must be a Frequency value.")
        super().__init__(
            id=id,
            name=name,
            terminals=(terminal,),
            family=family,
        )
        self._frequency = frequency

    @property
    def terminal(self) -> Terminal:
        return self.terminals[0]

    @property
    def frequency(self) -> Frequency:
        return self._frequency
