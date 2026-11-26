"""High-level equipment families used by the electrical domain."""

from enum import StrEnum


class EquipmentFamily(StrEnum):
    """Broad equipment classifications; detailed models belong to subdomains."""

    GENERIC = "generic"
    SOURCE = "source"
    TRANSFORMER = "transformer"
    TRANSMISSION = "transmission"
    MOTOR = "motor"
    LOAD = "load"
    CONVERTER = "converter"
    SWITCHING = "switching"
    GROUNDING = "grounding"
    COMPENSATION = "compensation"
