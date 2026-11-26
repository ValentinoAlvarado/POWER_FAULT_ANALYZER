"""Electrical terminal entity belonging to one equipment instance."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from power_fault_analyzer.domain.entities._validation import validate_non_empty_name
from power_fault_analyzer.domain.value_objects.voltage import (
    Voltage,
    VoltageReference,
)


@dataclass(frozen=True, slots=True)
class Terminal:
    """A physical/electrical connection point exposed by equipment.

    ``equipment_id`` identifies the owning equipment. ``rated_voltage`` is
    line-to-line in the initial balanced three-phase model.
    """

    equipment_id: UUID
    designation: str
    rated_voltage: Voltage
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.equipment_id, UUID):
            raise TypeError("equipment_id must be a UUID.")
        validate_non_empty_name(self.designation, "designation")
        if not isinstance(self.rated_voltage, Voltage):
            raise TypeError("rated_voltage must be a Voltage value object.")
        if self.rated_voltage.reference is not VoltageReference.LINE_TO_LINE:
            raise ValueError(
                "Terminal rated_voltage must use line-to-line reference "
                "in the balanced three-phase model."
            )
        object.__setattr__(self, "designation", self.designation.strip())
