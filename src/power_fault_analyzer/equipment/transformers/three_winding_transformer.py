"""Three-winding transformer entity with pairwise test impedances."""

from __future__ import annotations

from uuid import UUID

from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.three_winding_zero_sequence import (
    ThreeWindingZeroSequencePortModel,
)
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PairwiseTransformerImpedances,
    ThreeWindingStarEquivalent,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
from power_fault_analyzer.equipment.transformers.transformer_base import (
    TransformerEquipmentBase,
)


class ThreeWindingTransformer(TransformerEquipmentBase):
    """Three-terminal transformer with HV/MV/LV windings and pairwise tests."""

    __slots__ = (
        "_hv_lv_vector_group",
        "_hv_mv_vector_group",
        "_pairwise_impedances",
        "_zero_sequence_port_model",
    )

    @property
    def winding_count(self) -> int:
        return 3

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal, Terminal],
        windings: tuple[TransformerWinding, TransformerWinding, TransformerWinding],
        frequency: Frequency,
        hv_mv_vector_group: VectorGroup,
        hv_lv_vector_group: VectorGroup,
        pairwise_impedances: PairwiseTransformerImpedances,
        zero_sequence_port_model: ThreeWindingZeroSequencePortModel | None = None,
    ) -> None:
        if not isinstance(windings, tuple) or len(windings) != 3:
            raise ValueError("windings must be a tuple containing exactly HV, MV and LV.")
        if any(not isinstance(winding, TransformerWinding) for winding in windings):
            raise TypeError("Every winding must be a TransformerWinding value.")
        if not isinstance(hv_mv_vector_group, VectorGroup):
            raise TypeError("hv_mv_vector_group must be a VectorGroup value.")
        if not isinstance(hv_lv_vector_group, VectorGroup):
            raise TypeError("hv_lv_vector_group must be a VectorGroup value.")
        if not isinstance(pairwise_impedances, PairwiseTransformerImpedances):
            raise TypeError("pairwise_impedances must be PairwiseTransformerImpedances.")
        if zero_sequence_port_model is not None and not isinstance(
            zero_sequence_port_model, ThreeWindingZeroSequencePortModel
        ):
            raise TypeError(
                "zero_sequence_port_model must be a ThreeWindingZeroSequencePortModel or None."
            )
        if (
            zero_sequence_port_model is not None
            and zero_sequence_port_model.base != pairwise_impedances.base
        ):
            raise ValueError(
                "Zero-sequence port model must use the pairwise transformer reference base."
            )
        if not isinstance(terminals, tuple):
            raise TypeError("terminals must be an immutable tuple.")
        if len(terminals) != 3:
            raise ValueError("Three-winding transformer requires exactly three terminals.")
        expected = (
            WindingDesignation.HIGH_VOLTAGE,
            WindingDesignation.MEDIUM_VOLTAGE,
            WindingDesignation.LOW_VOLTAGE,
        )
        if tuple(w.designation for w in windings) != expected:
            raise ValueError("Three-winding transformer order must be (HV, MV, LV).")
        if hv_mv_vector_group.reference_connection is not windings[0].connection:
            raise ValueError("HV-MV vector-group reference must match HV winding.")
        if hv_mv_vector_group.secondary_connection is not windings[1].connection:
            raise ValueError("HV-MV vector-group secondary must match MV winding.")
        if hv_lv_vector_group.reference_connection is not windings[0].connection:
            raise ValueError("HV-LV vector-group reference must match HV winding.")
        if hv_lv_vector_group.secondary_connection is not windings[2].connection:
            raise ValueError("HV-LV vector-group secondary must match LV winding.")
        tolerance = max(1e-9, windings[0].rated_voltage_kv * 1e-9)
        if abs(pairwise_impedances.base.base_voltage_kv - windings[0].rated_voltage_kv) > tolerance:
            raise ValueError("Pairwise impedance base voltage must match the HV winding.")
        super().__init__(
            id=id,
            name=name,
            terminals=terminals,
            windings=windings,
            frequency=frequency,
        )
        self._hv_mv_vector_group = hv_mv_vector_group
        self._hv_lv_vector_group = hv_lv_vector_group
        self._pairwise_impedances = pairwise_impedances
        self._zero_sequence_port_model = zero_sequence_port_model

    @property
    def hv_mv_vector_group(self) -> VectorGroup:
        return self._hv_mv_vector_group

    @property
    def hv_lv_vector_group(self) -> VectorGroup:
        return self._hv_lv_vector_group

    @property
    def pairwise_impedances(self) -> PairwiseTransformerImpedances:
        return self._pairwise_impedances

    @property
    def hv_mv_vector_group_notation(self) -> str:
        hv, mv, _ = self.windings
        return self.hv_mv_vector_group.notation_with_neutrals(
            hv.neutral_terminal_available, mv.neutral_terminal_available
        )

    @property
    def hv_lv_vector_group_notation(self) -> str:
        hv, _, lv = self.windings
        return self.hv_lv_vector_group.notation_with_neutrals(
            hv.neutral_terminal_available, lv.neutral_terminal_available
        )

    @property
    def zero_sequence_port_model(self) -> ThreeWindingZeroSequencePortModel | None:
        return self._zero_sequence_port_model

    def build_star_equivalent(self, sequence: SequenceType) -> ThreeWindingStarEquivalent:
        return self.pairwise_impedances.to_star_equivalent(sequence)
