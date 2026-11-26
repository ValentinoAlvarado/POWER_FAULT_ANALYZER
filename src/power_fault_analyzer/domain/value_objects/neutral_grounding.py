"""Explicit neutral-grounding configurations for transformer windings."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode


def _finite_component(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real numeric value, not bool.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


@dataclass(frozen=True, slots=True)
class NeutralGrounding:
    """Neutral connection mode and grounding impedance in ohms.

    For impedance grounding, the represented neutral impedance is multiplied
    by three when inserted into a zero-sequence network, as required by the
    conventional symmetrical-component connection. This value object stores
    the physical neutral impedance itself, not the already-multiplied value.
    """

    mode: GroundingMode
    resistance_ohm: float = 0.0
    reactance_ohm: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.mode, GroundingMode):
            raise TypeError("mode must be a GroundingMode value.")
        resistance = _finite_component(self.resistance_ohm, "resistance_ohm")
        reactance = _finite_component(self.reactance_ohm, "reactance_ohm")
        if resistance < 0.0:
            raise ValueError("Grounding resistance cannot be negative.")
        if self.mode is GroundingMode.IMPEDANCE and resistance == 0.0 and reactance == 0.0:
            raise ValueError("Impedance grounding requires a non-zero impedance.")
        if self.mode is not GroundingMode.IMPEDANCE and (resistance != 0.0 or reactance != 0.0):
            raise ValueError("Only impedance grounding may specify non-zero R or X.")
        object.__setattr__(self, "resistance_ohm", resistance)
        object.__setattr__(self, "reactance_ohm", reactance)

    @classmethod
    def ungrounded(cls) -> NeutralGrounding:
        return cls(GroundingMode.UNGROUNDED)

    @classmethod
    def solid(cls) -> NeutralGrounding:
        return cls(GroundingMode.SOLID)

    @classmethod
    def through_impedance(
        cls, resistance_ohm: float, reactance_ohm: float = 0.0
    ) -> NeutralGrounding:
        return cls(GroundingMode.IMPEDANCE, resistance_ohm, reactance_ohm)

    @property
    def impedance_ohm(self) -> complex:
        return complex(self.resistance_ohm, self.reactance_ohm)

    @property
    def zero_sequence_neutral_impedance_ohm(self) -> complex | None:
        """Return the neutral contribution 3Zn, or ``None`` for an open path.

        An ungrounded neutral is an open zero-sequence return path, not a
        zero-ohm connection. Solid grounding is represented by ``0j``.
        """
        if self.mode is GroundingMode.UNGROUNDED:
            return None
        if self.mode is GroundingMode.IMPEDANCE:
            return 3.0 * self.impedance_ohm
        return 0.0j
