"""Configurable nominal-voltage compatibility policy."""

from __future__ import annotations

import math
from dataclasses import dataclass

from power_fault_analyzer.domain.value_objects.voltage import Voltage


@dataclass(frozen=True, slots=True)
class NominalVoltageCompatibilityPolicy:
    """Compare terminal and bus nominal voltages using a relative tolerance.

    The default tolerance is deliberately strict. It is a software connection
    policy, not a claim about IEC voltage ranges or equipment operating limits.
    Projects may inject a different policy when their engineering rules require it.
    """

    relative_tolerance: float = 1e-6

    def __post_init__(self) -> None:
        if isinstance(self.relative_tolerance, bool) or not isinstance(
            self.relative_tolerance, (int, float)
        ):
            raise TypeError("relative_tolerance must be numeric.")
        if not math.isfinite(float(self.relative_tolerance)):
            raise ValueError("relative_tolerance must be finite.")
        if self.relative_tolerance < 0:
            raise ValueError("relative_tolerance cannot be negative.")
        object.__setattr__(self, "relative_tolerance", float(self.relative_tolerance))

    def are_compatible(
        self,
        terminal_voltage: Voltage,
        bus_voltage: Voltage,
    ) -> bool:
        if not isinstance(terminal_voltage, Voltage):
            raise TypeError("terminal_voltage must be a Voltage.")
        if not isinstance(bus_voltage, Voltage):
            raise TypeError("bus_voltage must be a Voltage.")
        if terminal_voltage.reference is not bus_voltage.reference:
            return False
        return math.isclose(
            terminal_voltage.value_v,
            bus_voltage.value_v,
            rel_tol=self.relative_tolerance,
            abs_tol=0.0,
        )
