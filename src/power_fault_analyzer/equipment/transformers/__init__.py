"""Two- and three-winding transformer domain entities."""

from power_fault_analyzer.equipment.transformers.three_winding_transformer import (
    ThreeWindingTransformer,
)
from power_fault_analyzer.equipment.transformers.transformer_base import (
    TransformerEquipmentBase,
)
from power_fault_analyzer.equipment.transformers.two_winding_transformer import (
    TwoWindingTransformer,
)

__all__ = [
    "ThreeWindingTransformer",
    "TransformerEquipmentBase",
    "TwoWindingTransformer",
]
