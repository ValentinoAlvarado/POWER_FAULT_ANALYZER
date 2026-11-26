"""Structural contracts for transformer domain models."""

from typing import Protocol, runtime_checkable

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PairwiseTransformerImpedances,
    PerUnitImpedance,
    SequencePerUnitImpedance,
    ThreeWindingStarEquivalent,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup


@runtime_checkable
class TransformerModelProvider(Protocol):
    """Common read-only structural contract for transformer equipment."""

    @property
    def windings(self) -> tuple[TransformerWinding, ...]: ...

    @property
    def frequency(self) -> Frequency: ...


@runtime_checkable
class TwoWindingTransformerModelProvider(TransformerModelProvider, Protocol):
    @property
    def vector_group(self) -> VectorGroup: ...

    @property
    def sequence_impedances(self) -> SequencePerUnitImpedance: ...

    def get_sequence_impedance_pu(self, sequence: SequenceType) -> PerUnitImpedance: ...


@runtime_checkable
class ThreeWindingTransformerModelProvider(TransformerModelProvider, Protocol):
    @property
    def hv_mv_vector_group(self) -> VectorGroup: ...

    @property
    def hv_lv_vector_group(self) -> VectorGroup: ...

    @property
    def pairwise_impedances(self) -> PairwiseTransformerImpedances: ...

    def build_star_equivalent(self, sequence: SequenceType) -> ThreeWindingStarEquivalent: ...
