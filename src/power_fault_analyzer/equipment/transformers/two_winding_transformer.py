"""Two-winding transformer entity and sequence leakage data."""

from __future__ import annotations

from uuid import UUID

from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PerUnitImpedance,
    SequencePerUnitImpedance,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import EngineeringParameter
from power_fault_analyzer.equipment.transformers.transformer_base import (
    TransformerEquipmentBase,
)


class TwoWindingTransformer(TransformerEquipmentBase):
    """Two-terminal transformer with explicit HV/LV winding and vector-group data."""

    __slots__ = ("_data_evidence", "_sequence_impedances", "_vector_group")

    @property
    def winding_count(self) -> int:
        return 2

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal],
        windings: tuple[TransformerWinding, TransformerWinding],
        frequency: Frequency,
        vector_group: VectorGroup,
        sequence_impedances: SequencePerUnitImpedance,
        data_evidence: tuple[EngineeringParameter, ...] = (),
    ) -> None:
        if not isinstance(windings, tuple) or len(windings) != 2:
            raise ValueError("windings must be a tuple containing exactly HV and LV.")
        if any(not isinstance(winding, TransformerWinding) for winding in windings):
            raise TypeError("Every winding must be a TransformerWinding value.")
        if not isinstance(vector_group, VectorGroup):
            raise TypeError("vector_group must be a VectorGroup value.")
        if not isinstance(sequence_impedances, SequencePerUnitImpedance):
            raise TypeError("sequence_impedances must be SequencePerUnitImpedance.")
        if not isinstance(data_evidence, tuple) or any(
            not isinstance(item, EngineeringParameter) for item in data_evidence
        ):
            raise TypeError("data_evidence must be a tuple of EngineeringParameter values.")
        if not isinstance(terminals, tuple):
            raise TypeError("terminals must be an immutable tuple.")
        if len(terminals) != 2:
            raise ValueError("Two-winding transformer requires exactly two terminals.")
        expected = (WindingDesignation.HIGH_VOLTAGE, WindingDesignation.LOW_VOLTAGE)
        if tuple(w.designation for w in windings) != expected:
            raise ValueError("Two-winding transformer order must be (HV, LV).")
        if vector_group.reference_connection is not windings[0].connection:
            raise ValueError("Vector-group reference connection must match HV winding.")
        if vector_group.secondary_connection is not windings[1].connection:
            raise ValueError("Vector-group secondary connection must match LV winding.")
        tolerance = max(1e-9, windings[0].rated_voltage_kv * 1e-9)
        if abs(sequence_impedances.base.base_voltage_kv - windings[0].rated_voltage_kv) > tolerance:
            raise ValueError("Impedance base voltage must match the HV winding rated voltage.")
        super().__init__(
            id=id,
            name=name,
            terminals=terminals,
            windings=windings,
            frequency=frequency,
        )
        self._vector_group = vector_group
        self._sequence_impedances = sequence_impedances
        self._data_evidence = data_evidence

    @property
    def data_evidence(self) -> tuple[EngineeringParameter, ...]:
        return self._data_evidence

    @property
    def vector_group(self) -> VectorGroup:
        return self._vector_group

    @property
    def sequence_impedances(self) -> SequencePerUnitImpedance:
        return self._sequence_impedances

    @property
    def vector_group_notation(self) -> str:
        hv, lv = self.windings
        return self.vector_group.notation_with_neutrals(
            hv.neutral_terminal_available, lv.neutral_terminal_available
        )

    def get_sequence_impedance_pu(self, sequence: SequenceType) -> PerUnitImpedance:
        """Return the declared per-unit leakage impedance for one sequence.

        This method exposes electrical data only. It does not apply vector-group
        zero-sequence blocking or grounding connections; those belong to the
        transformer sequence-network adapter.
        """
        if not isinstance(sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        return self.sequence_impedances.for_sequence(sequence)
