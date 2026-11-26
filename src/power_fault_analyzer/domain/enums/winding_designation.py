"""Canonical winding designations for two- and three-winding transformers."""

from enum import StrEnum


class WindingDesignation(StrEnum):
    HIGH_VOLTAGE = "HV"
    MEDIUM_VOLTAGE = "MV"
    LOW_VOLTAGE = "LV"
