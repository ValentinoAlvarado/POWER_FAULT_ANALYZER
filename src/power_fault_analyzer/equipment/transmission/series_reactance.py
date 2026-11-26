"""Lumped series reactance domain entity."""

from uuid import UUID

from power_fault_analyzer.domain.entities.branch_equipment import BranchEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.branch_equivalent import (
    BranchEquivalentModel,
)
from power_fault_analyzer.domain.value_objects.impedance import Admittance
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    SequenceImpedanceSet,
)


class SeriesReactance(BranchEquipmentBase):
    """Lumped two-terminal series impedance, distinct from a line per km."""

    __slots__ = ("_sequence_impedances",)

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal],
        sequence_impedances: SequenceImpedanceSet,
        family: EquipmentFamily = EquipmentFamily.COMPENSATION,
    ) -> None:
        if not isinstance(sequence_impedances, SequenceImpedanceSet):
            raise TypeError("sequence_impedances must be a SequenceImpedanceSet.")
        super().__init__(
            id=id,
            name=name,
            terminals=terminals,
            family=family,
        )
        self._sequence_impedances = sequence_impedances

    @property
    def sequence_impedances(self) -> SequenceImpedanceSet:
        return self._sequence_impedances

    def build_sequence_equivalent(self, sequence: SequenceType) -> BranchEquivalentModel:
        zero_shunt = Admittance.zero()
        return BranchEquivalentModel(
            series_impedance=self.sequence_impedances.for_sequence(sequence),
            shunt_admittance_from=zero_shunt,
            shunt_admittance_to=zero_shunt,
        )
