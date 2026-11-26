"""Short-circuit fault classifications supported by the bus-fault solver."""

from enum import StrEnum


class FaultType(StrEnum):
    """Canonical symmetrical-component fault types.

    The canonical phase references are A-G for a single-line-to-ground fault,
    B-C for a line-to-line fault, and B-C-G for a double-line-to-ground fault.
    """

    THREE_PHASE = "three_phase"
    SINGLE_LINE_TO_GROUND = "single_line_to_ground"
    LINE_TO_LINE = "line_to_line"
    DOUBLE_LINE_TO_GROUND = "double_line_to_ground"
