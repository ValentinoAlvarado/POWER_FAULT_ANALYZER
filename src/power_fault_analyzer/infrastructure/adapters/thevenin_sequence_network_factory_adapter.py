"""Infrastructure mapping for a one-bus, three-sequence Thevenin equivalent."""

from __future__ import annotations

from uuid import UUID, uuid4

from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.projects.models import TheveninStudySettings
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceNetwork,
    SequenceNetworkSet,
    SequenceNode,
    SequenceShunt,
)


class TheveninSequenceNetworkFactoryAdapter:
    """Convert complex sequence impedances into Norton sequence-network shunts."""

    def build(
        self,
        settings: TheveninStudySettings,
    ) -> tuple[UUID, SequenceNetworkSet]:
        if not isinstance(settings, TheveninStudySettings):
            raise TypeError("settings must be a TheveninStudySettings.")

        bus_id = uuid4()
        network_id = uuid4()
        node = SequenceNode(bus_id, settings.bus_name)
        sequence_impedances = {
            SequenceType.ZERO: settings.zero_sequence_impedance_pu,
            SequenceType.POSITIVE: settings.positive_sequence_impedance_pu,
            SequenceType.NEGATIVE: settings.negative_sequence_impedance_pu,
        }
        networks: dict[SequenceType, SequenceNetwork] = {}
        for sequence in (SequenceType.ZERO, SequenceType.POSITIVE, SequenceType.NEGATIVE):
            networks[sequence] = SequenceNetwork(
                network_id=network_id,
                sequence=sequence,
                nodes=(node,),
                branches=(),
                shunts=(
                    SequenceShunt(
                        id=uuid4(),
                        name=f"{settings.bus_name}-{sequence.value.upper()}-THEVENIN",
                        node_id=bus_id,
                        admittance_pu=1.0 / sequence_impedances[sequence],
                        source_voltage_pu=(
                            settings.prefault_positive_voltage_pu
                            if sequence is SequenceType.POSITIVE
                            else 0.0j
                        ),
                        source_kind=SequenceSourceKind.EXPLICIT_THEVENIN,
                    ),
                ),
            )
        return (
            bus_id,
            SequenceNetworkSet(
                positive=networks[SequenceType.POSITIVE],
                negative=networks[SequenceType.NEGATIVE],
                zero=networks[SequenceType.ZERO],
            ),
        )
