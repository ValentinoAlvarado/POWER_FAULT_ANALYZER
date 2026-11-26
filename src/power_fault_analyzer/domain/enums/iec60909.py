"""IEC 60909 study-case selectors."""

from enum import Enum


class IEC60909CurrentCase(str, Enum):
    MAXIMUM = "maximum"
    MINIMUM = "minimum"


class IEC60909LowVoltageTolerance(str, Enum):
    PERCENT_6 = "6_percent"
    PERCENT_10 = "10_percent"
