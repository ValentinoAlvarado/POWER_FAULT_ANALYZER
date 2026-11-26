"""Immutable source-model value objects used by power-system studies."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.impedance import Impedance
from power_fault_analyzer.domain.value_objects.per_unit_impedance import (
    PerUnitImpedance,
    SequencePerUnitImpedance,
)


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def _finite_complex(value: complex, name: str) -> complex:
    if isinstance(value, bool) or not isinstance(value, (Real, complex)):
        raise TypeError(f"{name} must be a real or complex number, not bool.")
    result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"{name} must have finite real and imaginary components.")
    return result


def _validate_passive_impedance(value: PerUnitImpedance, name: str) -> None:
    if not isinstance(value, PerUnitImpedance):
        raise TypeError(f"{name} must be a PerUnitImpedance value.")
    if value.resistance_pu < 0.0 or value.reactance_pu < 0.0:
        raise ValueError(f"{name} must have non-negative resistance and reactance.")


@dataclass(frozen=True, slots=True)
class SynchronousMachineSequenceImpedances:
    """Per-unit synchronous-machine impedances on the declared machine base.

    Positive-sequence impedance is supplied for subtransient, transient and
    synchronous regimes. Negative- and zero-sequence impedances are independent
    of that regime in this initial steady sequence-domain model.
    """

    base: ElectricalImpedanceBase
    positive_subtransient: PerUnitImpedance
    positive_transient: PerUnitImpedance
    positive_synchronous: PerUnitImpedance
    negative: PerUnitImpedance
    zero: PerUnitImpedance

    def __post_init__(self) -> None:
        if not isinstance(self.base, ElectricalImpedanceBase):
            raise TypeError("base must be an ElectricalImpedanceBase value.")
        for field_name in (
            "positive_subtransient",
            "positive_transient",
            "positive_synchronous",
            "negative",
            "zero",
        ):
            _validate_passive_impedance(getattr(self, field_name), field_name)

    def positive_for_regime(self, regime: SourceOperatingRegime) -> PerUnitImpedance:
        if not isinstance(regime, SourceOperatingRegime):
            raise TypeError("regime must be a SourceOperatingRegime value.")
        return {
            SourceOperatingRegime.SUBTRANSIENT: self.positive_subtransient,
            SourceOperatingRegime.TRANSIENT: self.positive_transient,
            SourceOperatingRegime.SYNCHRONOUS: self.positive_synchronous,
        }[regime]

    def convert_base(
        self, new_base: ElectricalImpedanceBase
    ) -> SynchronousMachineSequenceImpedances:
        return SynchronousMachineSequenceImpedances(
            base=new_base,
            positive_subtransient=self.positive_subtransient.convert_base(self.base, new_base),
            positive_transient=self.positive_transient.convert_base(self.base, new_base),
            positive_synchronous=self.positive_synchronous.convert_base(self.base, new_base),
            negative=self.negative.convert_base(self.base, new_base),
            zero=self.zero.convert_base(self.base, new_base),
        )


@dataclass(frozen=True, slots=True)
class SourceSequenceEquivalent:
    """Equivalent impedance and optional internal source for one sequence."""

    sequence: SequenceType
    status: SourceSequenceStatus
    impedance: PerUnitImpedance | None = None
    internal_voltage_pu: complex | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        if not isinstance(self.status, SourceSequenceStatus):
            raise TypeError("status must be a SourceSequenceStatus value.")
        if self.status is SourceSequenceStatus.AVAILABLE:
            if self.impedance is None:
                raise ValueError("An available sequence model requires an impedance.")
            _validate_passive_impedance(self.impedance, "impedance")
        elif self.impedance is not None:
            raise ValueError("Blocked or unspecified sequence models cannot carry impedance.")
        if self.sequence is not SequenceType.POSITIVE and self.internal_voltage_pu is not None:
            raise ValueError("Independent internal voltage is only defined for positive sequence.")
        if self.internal_voltage_pu is not None:
            voltage = _finite_complex(self.internal_voltage_pu, "internal_voltage_pu")
            object.__setattr__(self, "internal_voltage_pu", voltage)
        if (
            self.sequence is SequenceType.POSITIVE
            and self.status is SourceSequenceStatus.AVAILABLE
            and self.internal_voltage_pu is None
        ):
            raise ValueError("An available positive-sequence source requires internal voltage.")

    @classmethod
    def blocked(cls, sequence: SequenceType) -> SourceSequenceEquivalent:
        return cls(sequence=sequence, status=SourceSequenceStatus.BLOCKED)

    @classmethod
    def unspecified(cls, sequence: SequenceType) -> SourceSequenceEquivalent:
        return cls(sequence=sequence, status=SourceSequenceStatus.UNSPECIFIED)


@dataclass(frozen=True, slots=True)
class SourceEquivalentSet:
    """Complete, explicitly-statused 0/1/2 sequence equivalent for one base."""

    base: ElectricalImpedanceBase
    positive: SourceSequenceEquivalent
    negative: SourceSequenceEquivalent
    zero: SourceSequenceEquivalent

    def __post_init__(self) -> None:
        if not isinstance(self.base, ElectricalImpedanceBase):
            raise TypeError("base must be an ElectricalImpedanceBase value.")
        expected = (
            ("positive", self.positive, SequenceType.POSITIVE),
            ("negative", self.negative, SequenceType.NEGATIVE),
            ("zero", self.zero, SequenceType.ZERO),
        )
        for name, model, sequence in expected:
            if not isinstance(model, SourceSequenceEquivalent):
                raise TypeError(f"{name} must be a SourceSequenceEquivalent value.")
            if model.sequence is not sequence:
                raise ValueError(f"{name} model must represent {sequence.value} sequence.")
        if self.positive.status is not SourceSequenceStatus.AVAILABLE:
            raise ValueError(
                "A source equivalent must provide an available positive-sequence model."
            )

    def for_sequence(self, sequence: SequenceType) -> SourceSequenceEquivalent:
        if not isinstance(sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        return {
            SequenceType.POSITIVE: self.positive,
            SequenceType.NEGATIVE: self.negative,
            SequenceType.ZERO: self.zero,
        }[sequence]

    def convert_base(self, new_base: ElectricalImpedanceBase) -> SourceEquivalentSet:
        if not isinstance(new_base, ElectricalImpedanceBase):
            raise TypeError("new_base must be an ElectricalImpedanceBase value.")

        voltage_base_factor = self.base.base_voltage_kv / new_base.base_voltage_kv

        def convert(item: SourceSequenceEquivalent) -> SourceSequenceEquivalent:
            if item.status is not SourceSequenceStatus.AVAILABLE:
                return item
            assert item.impedance is not None
            return SourceSequenceEquivalent(
                sequence=item.sequence,
                status=item.status,
                impedance=item.impedance.convert_base(self.base, new_base),
                internal_voltage_pu=(
                    item.internal_voltage_pu * voltage_base_factor
                    if item.internal_voltage_pu is not None
                    else None
                ),
            )

        return SourceEquivalentSet(
            base=new_base,
            positive=convert(self.positive),
            negative=convert(self.negative),
            zero=convert(self.zero),
        )


@dataclass(frozen=True, slots=True)
class ExternalGridShortCircuitData:
    """External-grid short-circuit strength and sequence data.

    The positive-sequence impedance magnitude is derived from U_LL² / S_sc.
    ``rx_ratio`` means R/X. Negative- and zero-sequence impedances are
    deliberately optional: absence means UNSPECIFIED, not equal-to-positive
    and not an open circuit.
    """

    short_circuit_power_mva: float
    rx_ratio: float
    negative_sequence_impedance_ohm: Impedance | None = None
    zero_sequence_impedance_ohm: Impedance | None = None
    prefault_voltage_pu: complex = 1.0 + 0.0j

    def __post_init__(self) -> None:
        power = _finite_real(self.short_circuit_power_mva, "short_circuit_power_mva")
        ratio = _finite_real(self.rx_ratio, "rx_ratio")
        if power <= 0.0:
            raise ValueError("short_circuit_power_mva must be greater than zero.")
        if ratio < 0.0:
            raise ValueError("rx_ratio (R/X) cannot be negative.")
        for name in ("negative_sequence_impedance_ohm", "zero_sequence_impedance_ohm"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Impedance):
                raise TypeError(f"{name} must be Impedance or None.")
            if value is not None and value.reactance_ohm < 0.0:
                raise ValueError(f"{name} must have non-negative inductive reactance.")
        object.__setattr__(self, "short_circuit_power_mva", power)
        object.__setattr__(self, "rx_ratio", ratio)
        object.__setattr__(
            self,
            "prefault_voltage_pu",
            _finite_complex(self.prefault_voltage_pu, "prefault_voltage_pu"),
        )

    def positive_sequence_impedance(self, nominal_voltage_kv: float) -> Impedance:
        voltage = _finite_real(nominal_voltage_kv, "nominal_voltage_kv")
        if voltage <= 0.0:
            raise ValueError("nominal_voltage_kv must be greater than zero.")
        magnitude = voltage**2 / self.short_circuit_power_mva
        reactance = magnitude / math.sqrt(1.0 + self.rx_ratio**2)
        resistance = self.rx_ratio * reactance
        return Impedance(resistance, reactance)


@dataclass(frozen=True, slots=True)
class InductionGeneratorParameters:
    """Initial symmetrical short-circuit equivalent for an induction generator.

    The sequence impedances are explicit test/vendor/model inputs. The decay
    time constant is retained as model metadata; this value object does not
    claim to calculate the time-domain decay waveform.
    """

    rated_power_mva: float
    sequence_impedances: SequencePerUnitImpedance
    decay_time_constant_s: float
    prefault_voltage_pu: complex = 1.0 + 0.0j

    def __post_init__(self) -> None:
        power = _finite_real(self.rated_power_mva, "rated_power_mva")
        tau = _finite_real(self.decay_time_constant_s, "decay_time_constant_s")
        if power <= 0.0 or tau <= 0.0:
            raise ValueError("rated_power_mva and decay_time_constant_s must be positive.")
        if not isinstance(self.sequence_impedances, SequencePerUnitImpedance):
            raise TypeError("sequence_impedances must be a SequencePerUnitImpedance value.")
        for sequence in SequenceType:
            _validate_passive_impedance(
                self.sequence_impedances.for_sequence(sequence),
                f"{sequence.value}_sequence_impedance",
            )
        object.__setattr__(self, "rated_power_mva", power)
        object.__setattr__(self, "decay_time_constant_s", tau)
        object.__setattr__(
            self,
            "prefault_voltage_pu",
            _finite_complex(self.prefault_voltage_pu, "prefault_voltage_pu"),
        )

    @property
    def base(self) -> ElectricalImpedanceBase:
        return self.sequence_impedances.base


@dataclass(frozen=True, slots=True)
class ConverterFaultCurrentCapability:
    """Declared per-unit sequence-current limits on an explicit current base.

    Missing negative- or zero-sequence limits mean UNSPECIFIED, not zero
    current. A downstream fault solver must also enforce the overall current
    limit using its selected control model.
    """

    base: ElectricalImpedanceBase
    overall_current_limit_pu: float
    positive_sequence_limit_pu: float
    negative_sequence_limit_pu: float | None = None
    zero_sequence_limit_pu: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.base, ElectricalImpedanceBase):
            raise TypeError("base must be an ElectricalImpedanceBase value.")
        overall = _finite_real(self.overall_current_limit_pu, "overall_current_limit_pu")
        positive = _finite_real(self.positive_sequence_limit_pu, "positive_sequence_limit_pu")
        if overall <= 0.0 or positive <= 0.0:
            raise ValueError("Overall and positive-sequence current limits must be positive.")
        if positive > overall:
            raise ValueError("Positive-sequence limit cannot exceed the overall current limit.")
        for name in ("negative_sequence_limit_pu", "zero_sequence_limit_pu"):
            value = getattr(self, name)
            if value is not None:
                limit = _finite_real(value, name)
                if limit < 0.0 or limit > overall:
                    raise ValueError(f"{name} must be between zero and the overall limit.")
                object.__setattr__(self, name, limit)
        object.__setattr__(self, "overall_current_limit_pu", overall)
        object.__setattr__(self, "positive_sequence_limit_pu", positive)

    def convert_base(self, new_base: ElectricalImpedanceBase) -> ConverterFaultCurrentCapability:
        """Convert per-unit current limits using Ibase_old / Ibase_new."""
        if not isinstance(new_base, ElectricalImpedanceBase):
            raise TypeError("new_base must be an ElectricalImpedanceBase value.")
        factor = self.base.base_current_ka / new_base.base_current_ka
        return ConverterFaultCurrentCapability(
            base=new_base,
            overall_current_limit_pu=self.overall_current_limit_pu * factor,
            positive_sequence_limit_pu=self.positive_sequence_limit_pu * factor,
            negative_sequence_limit_pu=(
                self.negative_sequence_limit_pu * factor
                if self.negative_sequence_limit_pu is not None
                else None
            ),
            zero_sequence_limit_pu=(
                self.zero_sequence_limit_pu * factor
                if self.zero_sequence_limit_pu is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class InductionMotorParameters:
    """Initial sequence equivalent and traceable data for an induction motor.

    The sequence impedances are explicit manufacturer/test/model inputs on the
    declared machine base. This contract supports the initial equivalent only;
    it does not infer IEC breaking-current or steady-state parameters.
    """

    rated_power_mva: float
    sequence_impedances: SequencePerUnitImpedance
    decay_time_constant_s: float
    data_reference: str
    prefault_voltage_pu: complex = 1.0 + 0.0j

    def __post_init__(self) -> None:
        power = _finite_real(self.rated_power_mva, "rated_power_mva")
        tau = _finite_real(self.decay_time_constant_s, "decay_time_constant_s")
        if power <= 0.0 or tau <= 0.0:
            raise ValueError("rated_power_mva and decay_time_constant_s must be positive.")
        if not isinstance(self.sequence_impedances, SequencePerUnitImpedance):
            raise TypeError("sequence_impedances must be a SequencePerUnitImpedance value.")
        base_power_tolerance = max(1e-9, power * 1e-9)
        if abs(self.sequence_impedances.base.base_power_mva - power) > base_power_tolerance:
            raise ValueError(
                "Sequence-impedance base power must match the induction-motor rated power."
            )
        for sequence in SequenceType:
            _validate_passive_impedance(
                self.sequence_impedances.for_sequence(sequence),
                f"{sequence.value}_sequence_impedance",
            )
        if not isinstance(self.data_reference, str) or not self.data_reference.strip():
            raise ValueError(
                "data_reference must identify the manufacturer, test or validated model."
            )
        object.__setattr__(self, "rated_power_mva", power)
        object.__setattr__(self, "decay_time_constant_s", tau)
        object.__setattr__(self, "data_reference", self.data_reference.strip())
        object.__setattr__(
            self,
            "prefault_voltage_pu",
            _finite_complex(self.prefault_voltage_pu, "prefault_voltage_pu"),
        )

    @property
    def base(self) -> ElectricalImpedanceBase:
        return self.sequence_impedances.base
