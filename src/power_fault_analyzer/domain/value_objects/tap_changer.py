"""Immutable tap-changer settings for transformer windings."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real


def _finite_number(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real numeric value, not bool.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


@dataclass(frozen=True, slots=True)
class TapChanger:
    """Tap position and step data.

    Positive position increments increase the effective rated voltage of the
    winding. This sign convention is explicit and must be respected by ratio
    and admittance model builders.
    """

    minimum_position: int
    maximum_position: int
    neutral_position: int
    current_position: int
    step_percent: float

    def __post_init__(self) -> None:
        positions = (
            self.minimum_position,
            self.maximum_position,
            self.neutral_position,
            self.current_position,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in positions):
            raise TypeError("Tap positions must be integers, not bool.")
        if self.minimum_position > self.maximum_position:
            raise ValueError("minimum_position cannot exceed maximum_position.")
        if not self.minimum_position <= self.neutral_position <= self.maximum_position:
            raise ValueError("neutral_position must lie within tap limits.")
        if not self.minimum_position <= self.current_position <= self.maximum_position:
            raise ValueError("current_position must lie within tap limits.")
        step = _finite_number(self.step_percent, "step_percent")
        if step <= 0.0:
            raise ValueError("step_percent must be greater than zero.")
        factor = 1.0 + (self.current_position - self.neutral_position) * step / 100.0
        if factor <= 0.0:
            raise ValueError("Current tap position produces a non-positive voltage factor.")
        object.__setattr__(self, "step_percent", step)

    @property
    def voltage_factor(self) -> float:
        return 1.0 + (self.current_position - self.neutral_position) * self.step_percent / 100.0

    def with_position(self, position: int) -> TapChanger:
        return TapChanger(
            minimum_position=self.minimum_position,
            maximum_position=self.maximum_position,
            neutral_position=self.neutral_position,
            current_position=position,
            step_percent=self.step_percent,
        )
