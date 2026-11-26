"""Structural domain contracts."""

from power_fault_analyzer.domain.interfaces.branch_model_contracts import (
    SequenceBranchModelProvider,
)
from power_fault_analyzer.domain.interfaces.source_model_contracts import (
    FaultCurrentCapabilityProvider,
    SourceModelProvider,
)
from power_fault_analyzer.domain.interfaces.transformer_model_contracts import (
    ThreeWindingTransformerModelProvider,
    TransformerModelProvider,
    TwoWindingTransformerModelProvider,
)

__all__ = [
    "FaultCurrentCapabilityProvider",
    "SequenceBranchModelProvider",
    "SourceModelProvider",
    "ThreeWindingTransformerModelProvider",
    "TransformerModelProvider",
    "TwoWindingTransformerModelProvider",
]
