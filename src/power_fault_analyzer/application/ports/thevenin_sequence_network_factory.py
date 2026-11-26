"""Port for mapping an explicit Thevenin definition to sequence-network models."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from power_fault_analyzer.domain.projects.models import TheveninStudySettings
from power_fault_analyzer.network.sequence_networks.models import SequenceNetworkSet


class TheveninSequenceNetworkFactoryPort(Protocol):
    def build(
        self,
        settings: TheveninStudySettings,
    ) -> tuple[UUID, SequenceNetworkSet]: ...
