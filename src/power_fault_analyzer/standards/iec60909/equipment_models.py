"""IEC-specific equipment input contracts and data-completeness checks.

No normative coefficient is embedded here. Current-source sequence phasors must
come from a separately verified IEC procedure or an approved model, while the
three-winding transformer correction equation remains a clause-mapped policy.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from types import MappingProxyType
from uuid import UUID

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.source_models import (
    InductionMotorParameters,
)
from power_fault_analyzer.equipment.motors.induction_motor import InductionMotor
from power_fault_analyzer.equipment.transformers.three_winding_transformer import (
    ThreeWindingTransformer,
)
from power_fault_analyzer.standards.iec60909.models import (
    STANDARD_EDITION,
    IEC60909SourceFamily,
    IEC60909SourceMode,
)
from power_fault_analyzer.standards.iec60909.scenarios import IEC60909StudyScenario


def _positive_finite(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and greater than zero.")
    return result


def _finite_complex(value: complex, name: str) -> complex:
    if isinstance(value, bool) or not isinstance(value, (Real, complex)):
        raise TypeError(f"{name} must be a real or complex number, not bool.")
    result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"{name} must have finite real and imaginary components.")
    return result


@dataclass(frozen=True, slots=True)
class IEC60909CurrentSourceInput:
    """Pre-calculated IEC current-source phasors with source/method provenance.

    This is intentionally not an alias or adapter for
    ``ConverterSequenceCurrentCommand``. The sequence phasors must be produced
    by the declared IEC current-source procedure or a reviewed vendor model.
    All three sequence keys are mandatory. ``None`` means unspecified; ``0j``
    means a zero-current phasor was explicitly established by the source method.
    """

    source_id: UUID
    source_family: IEC60909SourceFamily
    rated_voltage_kv: float
    sequence_currents_ka: Mapping[SequenceType, complex | None]
    data_reference: str
    method_reference: str
    standard_edition: str = STANDARD_EDITION

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, UUID):
            raise TypeError("source_id must be a UUID value.")
        if not isinstance(self.source_family, IEC60909SourceFamily):
            raise TypeError("source_family must be an IEC60909SourceFamily value.")
        if self.source_family not in {
            IEC60909SourceFamily.CONVERTER,
            IEC60909SourceFamily.POWER_STATION_UNIT,
        }:
            raise ValueError(
                "IEC current-source input is restricted to converter or power-station-unit sources."
            )
        object.__setattr__(
            self, "rated_voltage_kv", _positive_finite(self.rated_voltage_kv, "rated_voltage_kv")
        )
        if not isinstance(self.sequence_currents_ka, Mapping):
            raise TypeError("sequence_currents_ka must be a mapping.")
        if set(self.sequence_currents_ka) != set(SequenceType):
            raise ValueError(
                "IEC current-source input must explicitly declare all three sequence keys."
            )
        currents: dict[SequenceType, complex | None] = {}
        for sequence, value in self.sequence_currents_ka.items():
            if not isinstance(sequence, SequenceType):
                raise TypeError("sequence-current keys must be SequenceType values.")
            currents[sequence] = (
                None
                if value is None
                else _finite_complex(value, f"{sequence.value}_sequence_current_ka")
            )
        object.__setattr__(self, "sequence_currents_ka", MappingProxyType(currents))
        for name in ("data_reference", "method_reference", "standard_edition"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
            object.__setattr__(self, name, value.strip())

    def to_per_unit(self, base: ElectricalImpedanceBase) -> Mapping[SequenceType, complex]:
        """Convert kA phasors on an explicit three-phase voltage/current base."""
        if not isinstance(base, ElectricalImpedanceBase):
            raise TypeError("base must be an ElectricalImpedanceBase value.")
        tolerance = max(1e-9, self.rated_voltage_kv * 1e-9)
        if abs(base.base_voltage_kv - self.rated_voltage_kv) > tolerance:
            raise ValueError("Current-source voltage must match the per-unit base voltage.")
        return MappingProxyType(
            {
                sequence: current / base.base_current_ka
                for sequence, current in self.sequence_currents_ka.items()
                if current is not None
            }
        )


@dataclass(frozen=True, slots=True)
class IEC60909InductionMotorInput:
    """Immutable snapshot of the supplied induction-motor initial-equivalent data.

    This input supports only the initial sequence equivalent. Later IEC breaking
    and steady-state quantities require their own data and procedures.
    """

    equipment_id: UUID
    rated_power_mva: float
    rated_voltage_kv: float
    frequency_hz: float
    parameters: InductionMotorParameters
    stator_connection: WindingConnection
    neutral_grounding: NeutralGrounding
    data_reference: str
    standard_edition: str = STANDARD_EDITION

    def __post_init__(self) -> None:
        if not isinstance(self.equipment_id, UUID):
            raise TypeError("equipment_id must be a UUID value.")
        for name in ("rated_power_mva", "rated_voltage_kv", "frequency_hz"):
            object.__setattr__(self, name, _positive_finite(getattr(self, name), name))
        if not isinstance(self.parameters, InductionMotorParameters):
            raise TypeError("parameters must be InductionMotorParameters.")
        if not isinstance(self.stator_connection, WindingConnection):
            raise TypeError("stator_connection must be a WindingConnection value.")
        if not isinstance(self.neutral_grounding, NeutralGrounding):
            raise TypeError("neutral_grounding must be a NeutralGrounding value.")
        if (
            self.stator_connection is WindingConnection.DELTA
            and self.neutral_grounding.zero_sequence_neutral_impedance_ohm is not None
        ):
            raise ValueError("A delta stator cannot expose a grounded neutral terminal.")
        if not isinstance(self.data_reference, str) or not self.data_reference.strip():
            raise ValueError("data_reference must be non-empty.")
        if self.standard_edition != STANDARD_EDITION:
            raise ValueError("Motor input standard edition does not match the project IEC edition.")
        power_tolerance = max(1e-9, self.rated_power_mva * 1e-9)
        voltage_tolerance = max(1e-9, self.rated_voltage_kv * 1e-9)
        if abs(self.parameters.rated_power_mva - self.rated_power_mva) > power_tolerance:
            raise ValueError("Rated power snapshot must match the induction-motor parameter set.")
        if abs(self.parameters.base.base_voltage_kv - self.rated_voltage_kv) > voltage_tolerance:
            raise ValueError("Rated voltage snapshot must match the motor impedance base.")
        if self.data_reference.strip() != self.parameters.data_reference:
            raise ValueError("Motor data reference must match the source-parameter reference.")
        object.__setattr__(self, "data_reference", self.data_reference.strip())
        object.__setattr__(self, "standard_edition", self.standard_edition.strip())

    @classmethod
    def from_equipment(cls, motor: InductionMotor) -> IEC60909InductionMotorInput:
        if not isinstance(motor, InductionMotor):
            raise TypeError("motor must be an InductionMotor entity.")
        return cls(
            equipment_id=motor.id,
            rated_power_mva=motor.parameters.rated_power_mva,
            rated_voltage_kv=motor.parameters.base.base_voltage_kv,
            frequency_hz=motor.frequency.value_hz,
            parameters=motor.parameters,
            stator_connection=motor.stator_connection,
            neutral_grounding=motor.neutral_grounding,
            data_reference=motor.parameters.data_reference,
        )


class IEC60909TransformerReadinessStatus(str, Enum):
    """Whether explicit three-winding data are complete for a later IEC policy."""

    READY_FOR_NORMATIVE_POLICY = "ready_for_normative_policy"
    UNAVAILABLE_MISSING_DATA = "unavailable_missing_data"


@dataclass(frozen=True, slots=True)
class IEC60909ThreeWindingTransformerCorrectionInput:
    """Complete immutable input snapshot for a future clause-mapped transformer policy."""

    equipment_id: UUID
    equipment_name: str
    rated_power_mva_by_winding: tuple[float, float, float]
    rated_voltage_kv_by_winding: tuple[float, float, float]
    test_data_reference: str
    zero_sequence_reference: str
    transformer: ThreeWindingTransformer
    standard_edition: str = STANDARD_EDITION

    def __post_init__(self) -> None:
        if not isinstance(self.equipment_id, UUID):
            raise TypeError("equipment_id must be a UUID value.")
        if not isinstance(self.transformer, ThreeWindingTransformer):
            raise TypeError("transformer must be a ThreeWindingTransformer entity.")
        if self.transformer.id != self.equipment_id or self.transformer.name != self.equipment_name:
            raise ValueError("Transformer snapshot identity does not match its equipment entity.")
        if len(self.rated_power_mva_by_winding) != 3 or len(self.rated_voltage_kv_by_winding) != 3:
            raise ValueError("Three-winding correction input requires three winding ratings.")
        powers = tuple(
            _positive_finite(value, f"rated_power_mva_by_winding[{index}]")
            for index, value in enumerate(self.rated_power_mva_by_winding)
        )
        voltages = tuple(
            _positive_finite(value, f"rated_voltage_kv_by_winding[{index}]")
            for index, value in enumerate(self.rated_voltage_kv_by_winding)
        )
        expected_powers = tuple(winding.rated_power_mva for winding in self.transformer.windings)
        expected_voltages = tuple(winding.rated_voltage_kv for winding in self.transformer.windings)
        if powers != expected_powers or voltages != expected_voltages:
            raise ValueError("Winding rating snapshot must match the transformer nameplate data.")
        for name in (
            "equipment_name",
            "test_data_reference",
            "zero_sequence_reference",
            "standard_edition",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
            object.__setattr__(self, name, value.strip())
        zero_model = self.transformer.zero_sequence_port_model
        if zero_model is None or zero_model.reference != self.zero_sequence_reference:
            raise ValueError("Zero-sequence reference must match the explicit three-port model.")
        if zero_model.base != self.transformer.pairwise_impedances.base:
            raise ValueError(
                "Pairwise tests and zero-sequence model must use the same reference base."
            )
        if self.standard_edition != STANDARD_EDITION:
            raise ValueError(
                "Transformer input standard edition does not match the project IEC edition."
            )
        object.__setattr__(self, "rated_power_mva_by_winding", powers)
        object.__setattr__(self, "rated_voltage_kv_by_winding", voltages)
        object.__setattr__(self, "test_data_reference", self.test_data_reference.strip())
        object.__setattr__(self, "zero_sequence_reference", self.zero_sequence_reference.strip())

    @classmethod
    def from_equipment(
        cls,
        transformer: ThreeWindingTransformer,
        *,
        test_data_reference: str | None,
    ) -> IEC60909ThreeWindingTransformerReadiness:
        if not isinstance(transformer, ThreeWindingTransformer):
            raise TypeError("transformer must be a ThreeWindingTransformer entity.")
        missing: list[str] = []
        if not isinstance(test_data_reference, str) or not test_data_reference.strip():
            missing.append("manufacturer/test reference for all pairwise short-circuit impedances")
        if transformer.zero_sequence_port_model is None:
            missing.append("explicit measured/vendor/validated zero-sequence three-port model")
        if missing:
            return IEC60909ThreeWindingTransformerReadiness(
                equipment_id=transformer.id,
                status=IEC60909TransformerReadinessStatus.UNAVAILABLE_MISSING_DATA,
                missing_requirements=tuple(missing),
                correction_input=None,
            )
        zero_model = transformer.zero_sequence_port_model
        assert zero_model is not None
        correction_input = cls(
            equipment_id=transformer.id,
            equipment_name=transformer.name,
            rated_power_mva_by_winding=tuple(
                winding.rated_power_mva for winding in transformer.windings
            ),
            rated_voltage_kv_by_winding=tuple(
                winding.rated_voltage_kv for winding in transformer.windings
            ),
            test_data_reference=test_data_reference,
            zero_sequence_reference=zero_model.reference,
            transformer=transformer,
        )
        return IEC60909ThreeWindingTransformerReadiness(
            equipment_id=transformer.id,
            status=IEC60909TransformerReadinessStatus.READY_FOR_NORMATIVE_POLICY,
            missing_requirements=(),
            correction_input=correction_input,
        )


@dataclass(frozen=True, slots=True)
class IEC60909ThreeWindingTransformerReadiness:
    """Data-completeness result; readiness does not imply a calculated factor."""

    equipment_id: UUID
    status: IEC60909TransformerReadinessStatus
    missing_requirements: tuple[str, ...]
    correction_input: IEC60909ThreeWindingTransformerCorrectionInput | None

    def __post_init__(self) -> None:
        if not isinstance(self.equipment_id, UUID):
            raise TypeError("equipment_id must be a UUID value.")
        if not isinstance(self.status, IEC60909TransformerReadinessStatus):
            raise TypeError("status must be IEC60909TransformerReadinessStatus.")
        if not isinstance(self.missing_requirements, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.missing_requirements
        ):
            raise TypeError("missing_requirements must be a tuple of non-empty strings.")
        ready = self.status is IEC60909TransformerReadinessStatus.READY_FOR_NORMATIVE_POLICY
        if ready != (self.correction_input is not None) or ready != (not self.missing_requirements):
            raise ValueError(
                "Transformer readiness status, missing data and input snapshot disagree."
            )
        if self.correction_input is not None and not isinstance(
            self.correction_input, IEC60909ThreeWindingTransformerCorrectionInput
        ):
            raise TypeError(
                "correction_input must be an IEC60909ThreeWindingTransformerCorrectionInput."
            )
        if (
            self.correction_input is not None
            and self.correction_input.equipment_id != self.equipment_id
        ):
            raise ValueError("Correction input belongs to a different transformer.")


def validate_iec60909_current_source_input(
    data: IEC60909CurrentSourceInput,
    scenario: IEC60909StudyScenario,
) -> None:
    """Validate current-source data against one normalized IEC scenario."""
    if not isinstance(data, IEC60909CurrentSourceInput):
        raise TypeError("data must be an IEC60909CurrentSourceInput value.")
    if not isinstance(scenario, IEC60909StudyScenario):
        raise TypeError("scenario must be an IEC60909StudyScenario value.")
    matches = [item for item in scenario.sources if item.source_id == data.source_id]
    if len(matches) != 1:
        raise ValueError("Current-source input ID must match exactly one scenario source.")
    descriptor = matches[0]
    if not descriptor.in_service:
        raise ValueError("Current-source input references an out-of-service source.")
    if descriptor.mode is not IEC60909SourceMode.CURRENT_SOURCE:
        raise ValueError(
            "IEC current-source data cannot be assigned to a voltage-source descriptor."
        )
    if descriptor.family is not data.source_family:
        raise ValueError("IEC current-source family does not match the scenario source descriptor.")
    if data.standard_edition != STANDARD_EDITION:
        raise ValueError(
            "Current-source data standard edition does not match the project IEC edition."
        )
    missing = tuple(
        sequence
        for sequence in scenario.required_sequences
        if data.sequence_currents_ka[sequence] is None
    )
    if missing:
        labels = ", ".join(sorted(item.value for item in missing))
        raise ValueError(
            "Current-source input has unspecified fault-required sequence phasors: "
            f"{labels}. Use 0j only when zero current is explicitly established."
        )
