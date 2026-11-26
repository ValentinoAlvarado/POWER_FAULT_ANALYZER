"""Domain abstraction for two-terminal electrical branches."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from power_fault_analyzer.domain.entities.electrical_equipment import (
    TwoTerminalEquipmentBase,
)
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.branch_equivalent import (
    BranchEquivalentModel,
)


class BranchEquipmentBase(TwoTerminalEquipmentBase, ABC):
    """Base class for equipment connecting two electrical terminals.

    Concrete branches provide a sequence-specific equivalent model. The base
    class deliberately does not assume that all branches are lines or that
    their impedance is specified per kilometre.
    """

    __slots__ = ()

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal],
        family: EquipmentFamily = EquipmentFamily.TRANSMISSION,
    ) -> None:
        super().__init__(id=id, name=name, terminals=terminals, family=family)

    @abstractmethod
    def build_sequence_equivalent(self, sequence: SequenceType) -> BranchEquivalentModel:
        """Return the branch equivalent in the requested sequence network."""
