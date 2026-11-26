"""Structural contracts for sequence-domain branch model providers."""

from typing import Protocol, runtime_checkable

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.branch_equivalent import (
    BranchEquivalentModel,
)


@runtime_checkable
class SequenceBranchModelProvider(Protocol):
    """Equipment capable of producing a two-terminal sequence equivalent."""

    def build_sequence_equivalent(self, sequence: SequenceType) -> BranchEquivalentModel: ...
