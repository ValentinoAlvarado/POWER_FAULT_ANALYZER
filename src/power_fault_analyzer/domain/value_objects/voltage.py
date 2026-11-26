"""Voltage value object with an explicit voltage reference convention."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class VoltageReference(str, Enum):
    """Reference convention used to express a voltage magnitude."""

    LINE_TO_LINE = "line_to_line"
    PHASE_TO_NEUTRAL = "phase_to_neutral"


@dataclass(frozen=True, slots=True)
class Voltage:
    """Positive finite voltage magnitude stored internally in volts.

    The reference convention is explicit because a three-phase model must not
    silently confuse line-to-line and phase-to-neutral quantities.
    """

    value_v: float
    reference: VoltageReference = VoltageReference.LINE_TO_LINE

    def __post_init__(self) -> None:
        if isinstance(self.value_v, bool) or not isinstance(self.value_v, (int, float)):
            raise TypeError("value_v must be a real numeric value, not bool.")
        if not math.isfinite(self.value_v) or self.value_v <= 0:
            raise ValueError("value_v must be finite and greater than zero.")
        if not isinstance(self.reference, VoltageReference):
            raise TypeError("reference must be a VoltageReference.")
        object.__setattr__(self, "value_v", float(self.value_v))

    @classmethod
    def from_kv(
        cls,
        value_kv: float,
        reference: VoltageReference = VoltageReference.LINE_TO_LINE,
    ) -> Voltage:
        if isinstance(value_kv, bool) or not isinstance(value_kv, (int, float)):
            raise TypeError("value_kv must be a real numeric value, not bool.")
        return cls(value_v=float(value_kv) * 1_000.0, reference=reference)

    @property
    def value_kv(self) -> float:
        """Return the voltage magnitude in kilovolts."""
        return self.value_v / 1_000.0
