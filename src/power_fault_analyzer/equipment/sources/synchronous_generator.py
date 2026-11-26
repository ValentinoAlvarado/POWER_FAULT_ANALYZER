"""Synchronous-generator source model using explicit sequence reactances."""

from __future__ import annotations

import math
from numbers import Real
from uuid import UUID

from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.per_unit_impedance import PerUnitImpedance
from power_fault_analyzer.domain.value_objects.source_models import (
    SourceEquivalentSet,
    SourceSequenceEquivalent,
    SynchronousMachineSequenceImpedances,
)
from power_fault_analyzer.equipment.sources.source_base import SourceEquipmentBase


def _finite_complex(value: complex, name: str) -> complex:
    if isinstance(value, bool) or not isinstance(value, (Real, complex)):
        raise TypeError(f"{name} must be a real or complex number, not bool.")
    result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"{name} must be finite.")
    return result


class SynchronousGenerator(SourceEquipmentBase):
    """Synchronous generator with subtransient/transient/synchronous models.

    The positive-sequence internal voltage is a study input. The zero-sequence
    path is available only for a star/zigzag stator with a grounded neutral.
    Delta and ungrounded stators are represented as externally blocked.
    """

    __slots__ = (
        "_neutral_grounding",
        "_prefault_voltage_pu",
        "_sequence_impedances",
        "_stator_connection",
    )

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminal: Terminal,
        frequency: Frequency,
        sequence_impedances: SynchronousMachineSequenceImpedances,
        neutral_grounding: NeutralGrounding,
        stator_connection: WindingConnection = WindingConnection.STAR,
        prefault_voltage_pu: complex = 1.0 + 0.0j,
    ) -> None:
        if not isinstance(terminal, Terminal):
            raise TypeError("terminal must be a Terminal entity.")
        if not isinstance(frequency, Frequency):
            raise TypeError("frequency must be a Frequency value.")
        if not isinstance(sequence_impedances, SynchronousMachineSequenceImpedances):
            raise TypeError("sequence_impedances must be SynchronousMachineSequenceImpedances.")
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
        if (
            abs(sequence_impedances.base.base_voltage_kv - terminal.rated_voltage.value_kv)
            > tolerance
        ):
            raise ValueError("Machine impedance base voltage must match terminal rated voltage.")
        emf = _finite_complex(prefault_voltage_pu, "prefault_voltage_pu")
        super().__init__(
            id=id,
            name=name,
            terminal=terminal,
            frequency=frequency,
            family=EquipmentFamily.SOURCE,
        )
        self._sequence_impedances = sequence_impedances
        self._neutral_grounding = neutral_grounding
        self._stator_connection = stator_connection
        self._prefault_voltage_pu = emf

    @property
    def sequence_impedances(self) -> SynchronousMachineSequenceImpedances:
        return self._sequence_impedances

    @property
    def rated_power_mva(self) -> float:
        return self.sequence_impedances.base.base_power_mva

    @property
    def neutral_grounding(self) -> NeutralGrounding:
        return self._neutral_grounding

    @property
    def stator_connection(self) -> WindingConnection:
        return self._stator_connection

    @property
    def prefault_voltage_pu(self) -> complex:
        return self._prefault_voltage_pu

    @property
    def supported_regimes(self) -> frozenset[SourceOperatingRegime]:
        return frozenset(SourceOperatingRegime)

    def build_source_equivalent(
        self,
        base: ElectricalImpedanceBase,
        regime: SourceOperatingRegime,
    ) -> SourceEquivalentSet:
        if not isinstance(base, ElectricalImpedanceBase):
            raise TypeError("base must be an ElectricalImpedanceBase value.")
        if not isinstance(regime, SourceOperatingRegime):
            raise TypeError("regime must be a SourceOperatingRegime value.")

        converted = self.sequence_impedances.convert_base(base)
        positive = converted.positive_for_regime(regime)
        negative = converted.negative
        positive_model = SourceSequenceEquivalent(
            sequence=SequenceType.POSITIVE,
            status=SourceSequenceStatus.AVAILABLE,
            impedance=positive,
            internal_voltage_pu=(
                self.prefault_voltage_pu
                * self.sequence_impedances.base.base_voltage_kv
                / base.base_voltage_kv
            ),
        )
        negative_model = SourceSequenceEquivalent(
            sequence=SequenceType.NEGATIVE,
            status=SourceSequenceStatus.AVAILABLE,
            impedance=negative,
        )

        grounded_path = self.neutral_grounding.zero_sequence_neutral_impedance_ohm
        if self.stator_connection is WindingConnection.DELTA or grounded_path is None:
            zero_model = SourceSequenceEquivalent.blocked(SequenceType.ZERO)
        else:
            zero_machine_ohm = self.sequence_impedances.zero.to_ohm(self.sequence_impedances.base)
            zero_total_pu = (zero_machine_ohm + grounded_path) / base.base_impedance_ohm
            zero_model = SourceSequenceEquivalent(
                sequence=SequenceType.ZERO,
                status=SourceSequenceStatus.AVAILABLE,
                impedance=PerUnitImpedance(zero_total_pu.real, zero_total_pu.imag),
            )

        return SourceEquivalentSet(
            base=base,
            positive=positive_model,
            negative=negative_model,
            zero=zero_model,
        )
