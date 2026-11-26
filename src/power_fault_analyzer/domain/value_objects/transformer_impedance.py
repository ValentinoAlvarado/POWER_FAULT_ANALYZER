"""Transformer-specific pairwise impedance equivalents and compatibility exports."""

from __future__ import annotations

from dataclasses import dataclass

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.per_unit_impedance import (
    PerUnitImpedance,
    SequencePerUnitImpedance,
)

# Backwards-compatible public name retained for existing transformer APIs.
TransformerImpedanceBase = ElectricalImpedanceBase


@dataclass(frozen=True, slots=True)
class ThreeWindingStarEquivalent:
    """Star-arm sequence impedances referred to a common transformer base."""

    base: ElectricalImpedanceBase
    high_voltage: PerUnitImpedance
    medium_voltage: PerUnitImpedance
    low_voltage: PerUnitImpedance

    def __post_init__(self) -> None:
        if not isinstance(self.base, ElectricalImpedanceBase):
            raise TypeError("base must be a ElectricalImpedanceBase value.")
        for field_name in ("high_voltage", "medium_voltage", "low_voltage"):
            if not isinstance(getattr(self, field_name), PerUnitImpedance):
                raise TypeError(f"{field_name} must be a PerUnitImpedance value.")

    def for_designation(self, designation: str) -> PerUnitImpedance:
        values = {
            "HV": self.high_voltage,
            "MV": self.medium_voltage,
            "LV": self.low_voltage,
        }
        try:
            return values[designation]
        except KeyError as exc:
            raise ValueError(f"Unsupported winding designation: {designation!r}.") from exc


@dataclass(frozen=True, slots=True)
class PairwiseTransformerImpedances:
    """Three-winding pairwise impedances referred to exactly one common base.

    The values correspond to HV-MV, HV-LV and MV-LV short-circuit tests. Each
    sequence is transformed independently into a star-equivalent arm set.
    The resulting star arms may have signed components; they are mathematical
    equivalents and must not be interpreted as independent physical devices.
    """

    high_medium: SequencePerUnitImpedance
    high_low: SequencePerUnitImpedance
    medium_low: SequencePerUnitImpedance

    def __post_init__(self) -> None:
        values = (self.high_medium, self.high_low, self.medium_low)
        if any(not isinstance(item, SequencePerUnitImpedance) for item in values):
            raise TypeError("All pairwise values must be SequencePerUnitImpedance.")
        if not (values[0].base == values[1].base == values[2].base):
            raise ValueError("All pairwise impedances must use the same reference base.")
        for pair_name, item in zip(("high_medium", "high_low", "medium_low"), values):
            for sequence in SequenceType:
                impedance = item.for_sequence(sequence)
                if impedance.resistance_pu < 0.0:
                    raise ValueError(
                        f"{pair_name} {sequence.value}-sequence resistance cannot be negative."
                    )

    @property
    def base(self) -> TransformerImpedanceBase:
        return self.high_medium.base

    def to_star_equivalent(self, sequence: SequenceType) -> ThreeWindingStarEquivalent:
        z_hm = self.high_medium.for_sequence(sequence).value_pu
        z_hl = self.high_low.for_sequence(sequence).value_pu
        z_ml = self.medium_low.for_sequence(sequence).value_pu

        z_h = (z_hm + z_hl - z_ml) / 2.0
        z_m = (z_hm + z_ml - z_hl) / 2.0
        z_l = (z_hl + z_ml - z_hm) / 2.0

        return ThreeWindingStarEquivalent(
            base=self.base,
            high_voltage=PerUnitImpedance(z_h.real, z_h.imag),
            medium_voltage=PerUnitImpedance(z_m.real, z_m.imag),
            low_voltage=PerUnitImpedance(z_l.real, z_l.imag),
        )
