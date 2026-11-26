"""Bus entity for a balanced three-phase electrical network."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from power_fault_analyzer.domain.entities._validation import validate_non_empty_name
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.value_objects.voltage import (
    Voltage,
    VoltageReference,
)


@dataclass(frozen=True, slots=True)
class Bus:
    """A busbar or internal node at a nominal three-phase voltage level.

    ``nominal_voltage`` is expressed line-to-line for the balanced-network
    domain. The entity is immutable; changes create a new study revision.
    """

    name: str
    nominal_voltage: Voltage
    id: UUID = field(default_factory=uuid4)
    kind: BusKind = BusKind.BUSBAR

    def __post_init__(self) -> None:
        validate_non_empty_name(self.name)
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.kind, BusKind):
            raise TypeError("kind must be a BusKind value.")
        if not isinstance(self.nominal_voltage, Voltage):
            raise TypeError("nominal_voltage must be a Voltage value object.")
        if self.nominal_voltage.reference is not VoltageReference.LINE_TO_LINE:
            raise ValueError(
                "Bus nominal_voltage must use the line-to-line reference "
                "in the balanced three-phase model."
            )
        object.__setattr__(self, "name", self.name.strip())
