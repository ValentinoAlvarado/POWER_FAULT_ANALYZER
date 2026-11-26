"""Neutral grounding modes."""

from enum import StrEnum


class GroundingMode(StrEnum):
    UNGROUNDED = "ungrounded"
    SOLID = "solid"
    IMPEDANCE = "impedance"
