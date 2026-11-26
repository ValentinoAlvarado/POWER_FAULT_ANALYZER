"""Electrical connection types for transformer windings."""

from enum import StrEnum


class WindingConnection(StrEnum):
    """Three-phase winding connection families supported by the domain."""

    STAR = "star"
    DELTA = "delta"
    ZIGZAG = "zigzag"
