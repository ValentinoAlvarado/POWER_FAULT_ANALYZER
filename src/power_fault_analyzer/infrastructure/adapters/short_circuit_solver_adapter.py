"""Hexagonal adapter around the production sparse short-circuit solver."""

from __future__ import annotations

from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.infrastructure.numerical.short_circuit import ShortCircuitSolver
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceNetworkSet,
    SystemBaseSet,
)


class NumericalShortCircuitSolverAdapter:
    def __init__(self, solver: ShortCircuitSolver | None = None) -> None:
        self._solver = solver or ShortCircuitSolver()

    def solve(
        self,
        networks: SequenceNetworkSet,
        fault: FaultSpecification,
        system_base: SystemBaseSet,
    ) -> ShortCircuitResult:
        return self._solver.solve(networks, fault, system_base)
