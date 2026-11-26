"""Generic per-unit impedance value objects for electrical network equipment."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real numeric value, not bool.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


@dataclass(frozen=True, slots=True)
class PerUnitImpedance:
    """Complex per-unit impedance; signed components are allowed for equivalents."""

    resistance_pu: float
    reactance_pu: float

    def __post_init__(self) -> None:
        resistance = _finite_real(self.resistance_pu, "resistance_pu")
        reactance = _finite_real(self.reactance_pu, "reactance_pu")
        object.__setattr__(self, "resistance_pu", resistance)
        object.__setattr__(self, "reactance_pu", reactance)

    @property
    def value_pu(self) -> complex:
        return complex(self.resistance_pu, self.reactance_pu)

    def to_ohm(self, base: ElectricalImpedanceBase) -> complex:
        if not isinstance(base, ElectricalImpedanceBase):
            raise TypeError("base must be a ElectricalImpedanceBase value.")
        return self.value_pu * base.base_impedance_ohm

    def convert_base(
        self, old_base: ElectricalImpedanceBase, new_base: ElectricalImpedanceBase
    ) -> PerUnitImpedance:
        """Convert a per-unit impedance between declared voltage/power bases."""
        if not isinstance(old_base, ElectricalImpedanceBase):
            raise TypeError("old_base must be a ElectricalImpedanceBase value.")
        if not isinstance(new_base, ElectricalImpedanceBase):
            raise TypeError("new_base must be a ElectricalImpedanceBase value.")
        factor = (
            new_base.base_power_mva
            / old_base.base_power_mva
            * (old_base.base_voltage_kv / new_base.base_voltage_kv) ** 2
        )
        return self.scaled(factor)

    def scaled(self, factor: Real) -> PerUnitImpedance:
        scale = _finite_real(factor, "factor")
        return PerUnitImpedance(
            resistance_pu=self.resistance_pu * scale,
            reactance_pu=self.reactance_pu * scale,
        )


@dataclass(frozen=True, slots=True)
class SequencePerUnitImpedance:
    """Positive-, negative- and zero-sequence impedances on one declared base."""

    base: ElectricalImpedanceBase
    positive: PerUnitImpedance
    negative: PerUnitImpedance
    zero: PerUnitImpedance

    def __post_init__(self) -> None:
        if not isinstance(self.base, ElectricalImpedanceBase):
            raise TypeError("base must be a ElectricalImpedanceBase value.")
        for field_name in ("positive", "negative", "zero"):
            if not isinstance(getattr(self, field_name), PerUnitImpedance):
                raise TypeError(f"{field_name} must be a PerUnitImpedance value.")

    def convert_base(self, new_base: ElectricalImpedanceBase) -> SequencePerUnitImpedance:
        return SequencePerUnitImpedance(
            base=new_base,
            positive=self.positive.convert_base(self.base, new_base),
            negative=self.negative.convert_base(self.base, new_base),
            zero=self.zero.convert_base(self.base, new_base),
        )

    def for_sequence(self, sequence: SequenceType) -> PerUnitImpedance:
        if not isinstance(sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        return {
            SequenceType.POSITIVE: self.positive,
            SequenceType.NEGATIVE: self.negative,
            SequenceType.ZERO: self.zero,
        }[sequence]
