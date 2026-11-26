"""Electrical node presentation classes; these never alter connectivity."""

from enum import StrEnum


class BusKind(StrEnum):
    """Distinguish physical busbars from internal connection nodes."""

    BUSBAR = "busbar"
    CONNECTION_NODE = "connection_node"
