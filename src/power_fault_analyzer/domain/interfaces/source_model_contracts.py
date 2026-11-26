"""Structural contracts for source equivalent and converter fault models."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.source_models import (
    ConverterFaultCurrentCapability,
    SourceEquivalentSet,
)


@runtime_checkable
class SourceModelProvider(Protocol):
    """Equipment that can provide a Thevenin-like sequence source model."""

    @property
    def supported_regimes(self) -> frozenset[SourceOperatingRegime]: ...

    def build_source_equivalent(
        self,
        base: ElectricalImpedanceBase,
        regime: SourceOperatingRegime,
    ) -> SourceEquivalentSet: ...


@runtime_checkable
class FaultCurrentCapabilityProvider(Protocol):
    """Equipment represented by controlled current injection rather than Zth."""

    @property
    def fault_current_capability(self) -> ConverterFaultCurrentCapability: ...
