"""Selectors used by the topology-integrated protection study."""

from enum import StrEnum


class ProtectionRole(StrEnum):
    PRIMARY = "primary"
    BACKUP = "backup"


class ProtectionFaultLocationKind(StrEnum):
    BUS = "bus"
    LINE = "line"
