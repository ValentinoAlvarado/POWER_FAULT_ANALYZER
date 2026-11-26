"""Equivalent-circuit regime used for source short-circuit modelling."""

from enum import StrEnum


class SourceOperatingRegime(StrEnum):
    SUBTRANSIENT = "subtransient"
    TRANSIENT = "transient"
    SYNCHRONOUS = "synchronous"
