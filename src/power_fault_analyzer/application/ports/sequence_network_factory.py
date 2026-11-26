"""Port for translating a physical network into symmetrical-component networks."""

from __future__ import annotations

from typing import Protocol

from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.network.sequence_networks.models import SequenceNetworkSet, SystemBaseSet


class SequenceNetworkFactoryPort(Protocol):
    def build_all(
        self, network: NetworkAggregate, system_base: SystemBaseSet
    ) -> SequenceNetworkSet: ...
