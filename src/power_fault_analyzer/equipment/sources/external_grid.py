"""External-grid source represented by short-circuit power and R/X ratio."""

from __future__ import annotations

from uuid import UUID

from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.source_models import (
    ExternalGridShortCircuitData,
    SourceEquivalentSet,
    SourceSequenceEquivalent,
)
from power_fault_analyzer.domain.value_objects.transformer_impedance import PerUnitImpedance
from power_fault_analyzer.equipment.sources.source_base import SourceEquipmentBase


class ExternalGrid(SourceEquipmentBase):
    """One-terminal utility equivalent; missing Z2/Z0 data remain unspecified."""

    __slots__ = ("_short_circuit_data",)

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminal: Terminal,
        frequency: Frequency,
        short_circuit_data: ExternalGridShortCircuitData,
    ) -> None:
        if not isinstance(short_circuit_data, ExternalGridShortCircuitData):
            raise TypeError("short_circuit_data must be ExternalGridShortCircuitData.")
        super().__init__(
            id=id,
            name=name,
            terminal=terminal,
            frequency=frequency,
        )
        self._short_circuit_data = short_circuit_data

    @property
    def short_circuit_data(self) -> ExternalGridShortCircuitData:
        return self._short_circuit_data

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

        z1_ohm = self.short_circuit_data.positive_sequence_impedance(
            self.terminal.rated_voltage.value_kv
        )
        z1_pu = PerUnitImpedance(
            z1_ohm.resistance_ohm / base.base_impedance_ohm,
            z1_ohm.reactance_ohm / base.base_impedance_ohm,
        )

        def optional_sequence(
            sequence: SequenceType,
            impedance,
        ) -> SourceSequenceEquivalent:
            if impedance is None:
                return SourceSequenceEquivalent(
                    sequence=sequence,
                    status=SourceSequenceStatus.UNSPECIFIED,
                )
            return SourceSequenceEquivalent(
                sequence=sequence,
                status=SourceSequenceStatus.AVAILABLE,
                impedance=PerUnitImpedance(
                    impedance.resistance_ohm / base.base_impedance_ohm,
                    impedance.reactance_ohm / base.base_impedance_ohm,
                ),
            )

        return SourceEquivalentSet(
            base=base,
            positive=SourceSequenceEquivalent(
                sequence=SequenceType.POSITIVE,
                status=SourceSequenceStatus.AVAILABLE,
                impedance=z1_pu,
                internal_voltage_pu=(
                    self.short_circuit_data.prefault_voltage_pu
                    * self.terminal.rated_voltage.value_kv
                    / base.base_voltage_kv
                ),
            ),
            negative=optional_sequence(
                SequenceType.NEGATIVE,
                self.short_circuit_data.negative_sequence_impedance_ohm,
            ),
            zero=optional_sequence(
                SequenceType.ZERO,
                self.short_circuit_data.zero_sequence_impedance_ohm,
            ),
        )
