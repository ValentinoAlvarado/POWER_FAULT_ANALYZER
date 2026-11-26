"""Kinds of external equipment interfaces whose nameplate data is unresolved."""

from enum import StrEnum


class EquipmentInterfaceKind(StrEnum):
    TRANSMISSION_LINE = "transmission_line"
    POWER_TRANSFORMER = "power_transformer"


class ParameterEvidenceStatus(StrEnum):
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    USER_CONFIRMED = "USER_CONFIRMED"
    DERIVED = "DERIVED"
    UNRESOLVED = "UNRESOLVED"
    CONFLICTING = "CONFLICTING"
