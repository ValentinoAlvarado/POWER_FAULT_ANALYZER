"""Source-family classification retained in sequence-network Thevenin shunts."""

from enum import Enum


class SequenceSourceKind(str, Enum):
    """Source families with distinct IEC 60909 short-circuit behavior."""

    PASSIVE = "passive"
    NETWORK_FEEDER = "network_feeder"
    EXPLICIT_THEVENIN = "explicit_thevenin"
    SYNCHRONOUS_MACHINE = "synchronous_machine"
    ASYNCHRONOUS_MACHINE = "asynchronous_machine"
