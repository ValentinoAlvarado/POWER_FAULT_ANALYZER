"""Immutable terminal-to-bus connection value object."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Connection:
    """Association between one equipment terminal and one network bus.

    A connection is a value object: its identity is defined by the pair of
    referenced identifiers, rather than by an independent database identity.
    """

    terminal_id: UUID
    bus_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.terminal_id, UUID):
            raise TypeError("terminal_id must be a UUID.")
        if not isinstance(self.bus_id, UUID):
            raise TypeError("bus_id must be a UUID.")
