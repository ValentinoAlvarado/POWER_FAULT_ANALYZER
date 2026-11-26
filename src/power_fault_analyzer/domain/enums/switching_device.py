"""Switchgear kind and steady-state position values."""

from enum import StrEnum


class SwitchingDeviceKind(StrEnum):
    CIRCUIT_BREAKER = "circuit_breaker"
    DISCONNECTOR = "disconnector"
    EARTHING_SWITCH = "earthing_switch"


class SwitchPosition(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
