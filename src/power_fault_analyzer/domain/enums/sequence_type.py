"""Symmetrical-component sequence identifiers."""

from enum import StrEnum


class SequenceType(StrEnum):
    """Sequence networks used by the balanced three-phase fault model."""

    ZERO = "zero"
    POSITIVE = "positive"
    NEGATIVE = "negative"
