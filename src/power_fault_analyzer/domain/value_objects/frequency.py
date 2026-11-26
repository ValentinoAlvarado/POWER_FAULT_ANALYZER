"""Frequency value object stored in hertz."""

import math
from dataclasses import dataclass
from numbers import Real


@dataclass(frozen=True, slots=True)
class Frequency:
    value_hz: float

    def __post_init__(self) -> None:
        if isinstance(self.value_hz, bool) or not isinstance(self.value_hz, Real):
            raise TypeError("value_hz must be a real numeric value, not bool.")
        value = float(self.value_hz)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError("value_hz must be finite and greater than zero.")
        object.__setattr__(self, "value_hz", value)
