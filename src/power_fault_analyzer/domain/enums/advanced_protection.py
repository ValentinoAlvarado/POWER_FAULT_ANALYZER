"""Advanced protection-function selectors."""

from enum import StrEnum


class DifferentialProtectionKind(StrEnum):
    LINE = "line_differential_87l"
    TRANSFORMER = "transformer_differential_87t"


class DirectionalSense(StrEnum):
    FORWARD = "forward"
    REVERSE = "reverse"


class DistanceCharacteristic(StrEnum):
    MHO = "mho"
    QUADRILATERAL = "quadrilateral"


class DistanceLoop(StrEnum):
    AG = "a_ground"
    BG = "b_ground"
    CG = "c_ground"
    AB = "a_b"
    BC = "b_c"
    CA = "c_a"
