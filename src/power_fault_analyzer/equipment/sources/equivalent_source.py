"""Explicit sequence Thevenin source entered by the study engineer."""

from __future__ import annotations

from uuid import UUID

from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.source_models import SourceEquivalentSet
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import EngineeringParameter
from power_fault_analyzer.equipment.sources.source_base import SourceEquipmentBase


class EquivalentSource(SourceEquipmentBase):
    """Source with explicit positive/negative/zero sequence equivalents."""

    __slots__ = ("_data_evidence", "_equivalent")

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminal: Terminal,
        frequency: Frequency,
        equivalent: SourceEquivalentSet,
        data_evidence: tuple[EngineeringParameter, ...] = (),
    ) -> None:
        if not isinstance(equivalent, SourceEquivalentSet):
            raise TypeError("equivalent must be a SourceEquivalentSet value.")
        if not isinstance(terminal, Terminal):
            raise TypeError("terminal must be a Terminal entity.")
        if not isinstance(data_evidence, tuple) or any(
            not isinstance(item, EngineeringParameter) for item in data_evidence
        ):
            raise TypeError("data_evidence must be a tuple of EngineeringParameter values.")
        tolerance = max(1e-9, terminal.rated_voltage.value_kv * 1e-9)
        if abs(equivalent.base.base_voltage_kv - terminal.rated_voltage.value_kv) > tolerance:
            raise ValueError("Equivalent-source base voltage must match terminal rated voltage.")
        super().__init__(
            id=id,
            name=name,
            terminal=terminal,
            frequency=frequency,
        )
        self._equivalent = equivalent
        self._data_evidence = data_evidence

    @property
    def data_evidence(self) -> tuple[EngineeringParameter, ...]:
        return self._data_evidence

    @property
    def equivalent(self) -> SourceEquivalentSet:
        return self._equivalent

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
        return self.equivalent.convert_base(base)
