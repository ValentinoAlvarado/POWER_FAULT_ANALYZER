"""Immutable sequence parameter sets for balanced three-phase equipment."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.impedance import Admittance, Impedance


def _finite_non_negative(value: Real, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real numeric value, not bool.")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative.")
    return numeric


@dataclass(frozen=True, slots=True)
class ImpedancePerLength:
    """Series impedance per unit length, in ohms per kilometre."""

    resistance_ohm_per_km: float
    reactance_ohm_per_km: float

    def __post_init__(self) -> None:
        resistance = _finite_non_negative(self.resistance_ohm_per_km, "resistance_ohm_per_km")
        reactance = self.reactance_ohm_per_km
        if isinstance(reactance, bool) or not isinstance(reactance, Real):
            raise TypeError("reactance_ohm_per_km must be a real numeric value.")
        reactance = float(reactance)
        if not math.isfinite(reactance):
            raise ValueError("reactance_ohm_per_km must be finite.")
        object.__setattr__(self, "resistance_ohm_per_km", resistance)
        object.__setattr__(self, "reactance_ohm_per_km", reactance)

    def for_length(self, length_km: float) -> Impedance:
        length = _finite_non_negative(length_km, "length_km")
        return Impedance(
            self.resistance_ohm_per_km * length,
            self.reactance_ohm_per_km * length,
        )


@dataclass(frozen=True, slots=True)
class AdmittancePerLength:
    """Shunt admittance per unit length, in siemens per kilometre."""

    conductance_siemens_per_km: float = 0.0
    susceptance_siemens_per_km: float = 0.0

    def __post_init__(self) -> None:
        conductance = _finite_non_negative(
            self.conductance_siemens_per_km, "conductance_siemens_per_km"
        )
        susceptance = self.susceptance_siemens_per_km
        if isinstance(susceptance, bool) or not isinstance(susceptance, Real):
            raise TypeError("susceptance_siemens_per_km must be a real numeric value.")
        susceptance = float(susceptance)
        if not math.isfinite(susceptance):
            raise ValueError("susceptance_siemens_per_km must be finite.")
        object.__setattr__(self, "conductance_siemens_per_km", conductance)
        object.__setattr__(self, "susceptance_siemens_per_km", susceptance)

    def for_length(self, length_km: float) -> Admittance:
        length = _finite_non_negative(length_km, "length_km")
        return Admittance(
            self.conductance_siemens_per_km * length,
            self.susceptance_siemens_per_km * length,
        )


@dataclass(frozen=True, slots=True)
class SequenceImpedancePerLengthSet:
    """Positive-, negative- and zero-sequence series impedance per kilometre."""

    positive: ImpedancePerLength
    negative: ImpedancePerLength
    zero: ImpedancePerLength

    def __post_init__(self) -> None:
        for name in ("positive", "negative", "zero"):
            if not isinstance(getattr(self, name), ImpedancePerLength):
                raise TypeError(f"{name} must be an ImpedancePerLength value.")

    def for_sequence(self, sequence: SequenceType) -> ImpedancePerLength:
        if not isinstance(sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        return {
            SequenceType.POSITIVE: self.positive,
            SequenceType.NEGATIVE: self.negative,
            SequenceType.ZERO: self.zero,
        }[sequence]


@dataclass(frozen=True, slots=True)
class SequenceAdmittancePerLengthSet:
    """Positive-, negative- and zero-sequence shunt admittance per kilometre."""

    positive: AdmittancePerLength
    negative: AdmittancePerLength
    zero: AdmittancePerLength

    def __post_init__(self) -> None:
        for name in ("positive", "negative", "zero"):
            if not isinstance(getattr(self, name), AdmittancePerLength):
                raise TypeError(f"{name} must be an AdmittancePerLength value.")

    def for_sequence(self, sequence: SequenceType) -> AdmittancePerLength:
        if not isinstance(sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        return {
            SequenceType.POSITIVE: self.positive,
            SequenceType.NEGATIVE: self.negative,
            SequenceType.ZERO: self.zero,
        }[sequence]

    @classmethod
    def all_zero(cls) -> SequenceAdmittancePerLengthSet:
        value = AdmittancePerLength()
        return cls(positive=value, negative=value, zero=value)


@dataclass(frozen=True, slots=True)
class SequenceImpedanceSet:
    """Lumped positive-, negative- and zero-sequence impedances in ohms."""

    positive: Impedance
    negative: Impedance
    zero: Impedance

    def __post_init__(self) -> None:
        for name in ("positive", "negative", "zero"):
            if not isinstance(getattr(self, name), Impedance):
                raise TypeError(f"{name} must be an Impedance value.")

    def for_sequence(self, sequence: SequenceType) -> Impedance:
        if not isinstance(sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        return {
            SequenceType.POSITIVE: self.positive,
            SequenceType.NEGATIVE: self.negative,
            SequenceType.ZERO: self.zero,
        }[sequence]


@dataclass(frozen=True, slots=True)
class SequenceAdmittanceSet:
    """Lumped positive-, negative- and zero-sequence shunt admittances."""

    positive: Admittance
    negative: Admittance
    zero: Admittance

    def __post_init__(self) -> None:
        for name in ("positive", "negative", "zero"):
            if not isinstance(getattr(self, name), Admittance):
                raise TypeError(f"{name} must be an Admittance value.")

    def for_sequence(self, sequence: SequenceType) -> Admittance:
        if not isinstance(sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        return {
            SequenceType.POSITIVE: self.positive,
            SequenceType.NEGATIVE: self.negative,
            SequenceType.ZERO: self.zero,
        }[sequence]

    @classmethod
    def all_zero(cls) -> SequenceAdmittanceSet:
        value = Admittance.zero()
        return cls(positive=value, negative=value, zero=value)
