"""Transformer winding value object and nameplate validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.tap_changer import TapChanger


def _positive_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real numeric value, not bool.")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and greater than zero.")
    return result


@dataclass(frozen=True, slots=True)
class TransformerWinding:
    """Nameplate and connection data for one transformer winding.

    Rated voltage is line-to-line in kV; rated power is three-phase MVA.
    Star and zigzag windings require an explicit neutral configuration so
    zero-sequence behavior cannot be inferred from missing data.
    """

    designation: WindingDesignation
    rated_voltage_kv: float
    rated_power_mva: float
    connection: WindingConnection
    neutral_grounding: NeutralGrounding | None
    neutral_terminal_available: bool = False
    tap_changer: TapChanger | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.designation, WindingDesignation):
            raise TypeError("designation must be a WindingDesignation value.")
        if not isinstance(self.connection, WindingConnection):
            raise TypeError("connection must be a WindingConnection value.")
        voltage = _positive_real(self.rated_voltage_kv, "rated_voltage_kv")
        power = _positive_real(self.rated_power_mva, "rated_power_mva")
        grounding = self.neutral_grounding
        if not isinstance(self.neutral_terminal_available, bool):
            raise TypeError("neutral_terminal_available must be bool.")
        if self.connection is WindingConnection.DELTA:
            if grounding is not None:
                raise ValueError("Delta windings cannot declare a neutral grounding.")
            if self.neutral_terminal_available:
                raise ValueError("Delta windings cannot expose a neutral terminal.")
        elif not isinstance(grounding, NeutralGrounding):
            raise ValueError("Star and zigzag windings require an explicit NeutralGrounding value.")
        elif grounding.mode is not GroundingMode.UNGROUNDED and not self.neutral_terminal_available:
            raise ValueError(
                "A grounded star/zigzag neutral must be available at the winding terminal."
            )
        if self.tap_changer is not None and not isinstance(self.tap_changer, TapChanger):
            raise TypeError("tap_changer must be a TapChanger value or None.")
        object.__setattr__(self, "rated_voltage_kv", voltage)
        object.__setattr__(self, "rated_power_mva", power)

    @property
    def effective_rated_voltage_kv(self) -> float:
        factor = self.tap_changer.voltage_factor if self.tap_changer else 1.0
        return self.rated_voltage_kv * factor
