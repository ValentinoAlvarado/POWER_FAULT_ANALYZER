"""Induction-generator initial short-circuit equivalent."""

from __future__ import annotations

from uuid import UUID

from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.exceptions.source_exceptions import (
    UnsupportedSourceOperatingRegimeError,
)
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.per_unit_impedance import PerUnitImpedance
from power_fault_analyzer.domain.value_objects.source_models import (
    InductionGeneratorParameters,
    SourceEquivalentSet,
    SourceSequenceEquivalent,
)
from power_fault_analyzer.equipment.sources.source_base import SourceEquipmentBase


class InductionGenerator(SourceEquipmentBase):
    """Induction generator represented by supplied initial sequence impedances.

    Only the initial/subtransient-like contribution is exposed at this stage.
    The decay time constant is metadata for a later time-dependent model;
    transient and synchronous regimes are explicitly unsupported.
    """

    __slots__ = ("_neutral_grounding", "_parameters", "_stator_connection")

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminal: Terminal,
        frequency: Frequency,
        parameters: InductionGeneratorParameters,
        neutral_grounding: NeutralGrounding,
        stator_connection: WindingConnection = WindingConnection.STAR,
    ) -> None:
        if not isinstance(terminal, Terminal):
            raise TypeError("terminal must be a Terminal entity.")
        if not isinstance(frequency, Frequency):
            raise TypeError("frequency must be a Frequency value.")
        if not isinstance(parameters, InductionGeneratorParameters):
            raise TypeError("parameters must be InductionGeneratorParameters.")
        if not isinstance(neutral_grounding, NeutralGrounding):
            raise TypeError("neutral_grounding must be a NeutralGrounding value.")
        if not isinstance(stator_connection, WindingConnection):
            raise TypeError("stator_connection must be a WindingConnection value.")
        if (
            stator_connection is WindingConnection.DELTA
            and neutral_grounding.zero_sequence_neutral_impedance_ohm is not None
        ):
            raise ValueError("A delta stator cannot expose a grounded neutral terminal.")
        tolerance = max(1e-9, terminal.rated_voltage.value_kv * 1e-9)
        if abs(parameters.base.base_voltage_kv - terminal.rated_voltage.value_kv) > tolerance:
            raise ValueError("Machine parameter base voltage must match terminal rated voltage.")
        super().__init__(
            id=id,
            name=name,
            terminal=terminal,
            frequency=frequency,
            family=EquipmentFamily.SOURCE,
        )
        self._parameters = parameters
        self._neutral_grounding = neutral_grounding
        self._stator_connection = stator_connection

    @property
    def parameters(self) -> InductionGeneratorParameters:
        return self._parameters

    @property
    def neutral_grounding(self) -> NeutralGrounding:
        return self._neutral_grounding

    @property
    def stator_connection(self) -> WindingConnection:
        return self._stator_connection

    @property
    def supported_regimes(self) -> frozenset[SourceOperatingRegime]:
        return frozenset({SourceOperatingRegime.SUBTRANSIENT})

    def build_source_equivalent(
        self,
        base: ElectricalImpedanceBase,
        regime: SourceOperatingRegime,
    ) -> SourceEquivalentSet:
        if not isinstance(base, ElectricalImpedanceBase):
            raise TypeError("base must be an ElectricalImpedanceBase value.")
        if not isinstance(regime, SourceOperatingRegime):
            raise TypeError("regime must be a SourceOperatingRegime value.")
        if regime is not SourceOperatingRegime.SUBTRANSIENT:
            raise UnsupportedSourceOperatingRegimeError(
                "The current induction-generator model supports only the initial "
                "short-circuit contribution; a time-dependent decay model is not implemented."
            )

        converted = self.parameters.sequence_impedances.convert_base(base)
        positive_model = SourceSequenceEquivalent(
            sequence=SequenceType.POSITIVE,
            status=SourceSequenceStatus.AVAILABLE,
            impedance=converted.positive,
            internal_voltage_pu=(
                self.parameters.prefault_voltage_pu
                * self.parameters.base.base_voltage_kv
                / base.base_voltage_kv
            ),
        )
        negative_model = SourceSequenceEquivalent(
            sequence=SequenceType.NEGATIVE,
            status=SourceSequenceStatus.AVAILABLE,
            impedance=converted.negative,
        )
        grounded_path = self.neutral_grounding.zero_sequence_neutral_impedance_ohm
        if self.stator_connection is WindingConnection.DELTA or grounded_path is None:
            zero_model = SourceSequenceEquivalent.blocked(SequenceType.ZERO)
        else:
            z0_machine_ohm = self.parameters.sequence_impedances.zero.to_ohm(
                self.parameters.sequence_impedances.base
            )
            z0_total_pu = (z0_machine_ohm + grounded_path) / base.base_impedance_ohm
            zero_model = SourceSequenceEquivalent(
                sequence=SequenceType.ZERO,
                status=SourceSequenceStatus.AVAILABLE,
                impedance=PerUnitImpedance(z0_total_pu.real, z0_total_pu.imag),
            )
        return SourceEquivalentSet(
            base=base,
            positive=positive_model,
            negative=negative_model,
            zero=zero_model,
        )
