"""Output port used by application use cases to execute bus-fault studies."""

from __future__ import annotations

from typing import Protocol

from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceNetworkSet,
    SystemBaseSet,
)


class ShortCircuitSolverPort(Protocol):
    def solve(
        self,
        networks: SequenceNetworkSet,
        fault: FaultSpecification,
        system_base: SystemBaseSet,
    ) -> ShortCircuitResult: ...
