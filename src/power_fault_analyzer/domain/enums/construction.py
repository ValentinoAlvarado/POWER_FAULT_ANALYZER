"""Construction classifications for overhead lines and underground cables."""

from enum import StrEnum


class ConductorMaterial(StrEnum):
    COPPER = "copper"
    ALUMINUM = "aluminum"
    AAC = "aac"
    AAAC = "aaac"
    ACSR = "acsr"
    OTHER = "other"


class InsulationMaterial(StrEnum):
    XLPE = "xlpe"
    EPR = "epr"
    PILC = "pilc"
    PVC = "pvc"
    OTHER = "other"


class ScreenBonding(StrEnum):
    SOLID_BONDED = "solid_bonded"
    SINGLE_POINT_BONDED = "single_point_bonded"
    CROSS_BONDED = "cross_bonded"
    UNBONDED = "unbonded"
    UNKNOWN = "unknown"
