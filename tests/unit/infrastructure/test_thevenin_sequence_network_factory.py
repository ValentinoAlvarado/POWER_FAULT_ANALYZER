from __future__ import annotations

from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.projects.models import TheveninStudySettings
from power_fault_analyzer.infrastructure.adapters.thevenin_sequence_network_factory_adapter import (
    TheveninSequenceNetworkFactoryAdapter,
)


def test_factory_builds_one_shared_bus_in_three_sequence_networks() -> None:
    settings = TheveninStudySettings()
    bus_id, networks = TheveninSequenceNetworkFactoryAdapter().build(settings)

    assert networks.positive.nodes[0].id == bus_id
    assert networks.negative.nodes[0].id == bus_id
    assert networks.zero.nodes[0].id == bus_id
    assert networks.positive.network_id == networks.negative.network_id == networks.zero.network_id
    positive_shunt = networks.positive.shunts[0]
    assert positive_shunt.source_kind is SequenceSourceKind.EXPLICIT_THEVENIN
    assert positive_shunt.source_voltage_pu == settings.prefault_positive_voltage_pu
    assert positive_shunt.admittance_pu == 1.0 / settings.positive_sequence_impedance_pu
    assert networks.negative.shunts[0].source_voltage_pu == 0.0j
    assert networks.zero.shunts[0].source_voltage_pu == 0.0j
    assert networks.for_sequence(SequenceType.POSITIVE) is networks.positive
