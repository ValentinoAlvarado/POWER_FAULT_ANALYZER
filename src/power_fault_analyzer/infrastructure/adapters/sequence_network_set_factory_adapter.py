"""Infrastructure adapter for the production symmetrical-component network builder."""

from __future__ import annotations

from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.network.sequence_networks.builder import SequenceNetworkBuilder
from power_fault_analyzer.network.sequence_networks.models import SequenceNetworkSet, SystemBaseSet


class SequenceNetworkSetFactoryAdapter:
    def build_all(
        self, network: NetworkAggregate, system_base: SystemBaseSet
    ) -> SequenceNetworkSet:
        return SequenceNetworkBuilder(system_base).build_all(network)
