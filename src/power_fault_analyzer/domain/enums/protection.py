"""Protection-function, curve and assessment selectors."""

from enum import Enum


class IECInverseCurveType(str, Enum):
    STANDARD_INVERSE = "standard_inverse"
    VERY_INVERSE = "very_inverse"
    EXTREMELY_INVERSE = "extremely_inverse"
    LONG_TIME_INVERSE = "long_time_inverse"


class ProtectionFunction(str, Enum):
    PHASE = "phase"
    EARTH = "earth"


class ProtectionStage(str, Enum):
    INSTANTANEOUS_50 = "50_instantaneous"
    TIME_INVERSE_51 = "51_time_inverse"


class ProtectionAssessmentStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUATED = "not_evaluated"


class CircuitBreakerStandard(str, Enum):
    IEC_60947_2 = "iec_60947_2"
    IEC_62271_100 = "iec_62271_100"
