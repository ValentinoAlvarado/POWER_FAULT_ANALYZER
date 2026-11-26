"""Equipment classification retained by the sequence-network model."""

from enum import Enum


class SequenceEquipmentKind(str, Enum):
    """Physical equipment families relevant to IEC short-circuit corrections."""

    OTHER = "other"
    LINE = "line"
    TWO_WINDING_TRANSFORMER = "two_winding_transformer"
    THREE_WINDING_TRANSFORMER = "three_winding_transformer"
