"""Normalized, immutable IEC 60909 study scenario contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID, uuid4

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.iec60909_study import IEC60909StudySpecification
from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet
from power_fault_analyzer.standards.iec60909.models import IEC60909SourceDescriptor


class IEC60909TopologyClass(str, Enum):
    """Topology classes used to select an applicable IEC calculation procedure."""

    RADIAL = "radial"
    MESHED = "meshed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class IEC60909StudyScenario:
    """Complete normalized input envelope for one IEC short-circuit study.

    This is a data contract, not a solver. The caller must explicitly supply the
    topology classification and all in-service source identities; they are never
    inferred from incomplete input.
    """

    network_id: UUID
    fault: FaultSpecification
    system_base: SystemBaseSet
    study: IEC60909StudySpecification
    topology_class: IEC60909TopologyClass
    sources: tuple[IEC60909SourceDescriptor, ...] = ()
    active_equipment_ids: tuple[UUID, ...] = ()
    assumptions: tuple[str, ...] = ()
    scenario_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.network_id, UUID) or not isinstance(self.scenario_id, UUID):
            raise TypeError("network_id and scenario_id must be UUID values.")
        if not isinstance(self.fault, FaultSpecification):
            raise TypeError("fault must be a FaultSpecification value.")
        if not isinstance(self.system_base, SystemBaseSet):
            raise TypeError("system_base must be a SystemBaseSet value.")
        if not isinstance(self.study, IEC60909StudySpecification):
            raise TypeError("study must be an IEC60909StudySpecification value.")
        if not isinstance(self.topology_class, IEC60909TopologyClass):
            raise TypeError("topology_class must be an IEC60909TopologyClass value.")
        if self.fault.bus_id not in self.system_base.bus_voltage_bases_kv:
            raise ValueError("The faulted bus must have a configured system voltage base.")
        if not isinstance(self.sources, tuple) or any(
            not isinstance(item, IEC60909SourceDescriptor) for item in self.sources
        ):
            raise TypeError("sources must be a tuple of IEC60909SourceDescriptor values.")
        source_ids = tuple(item.source_id for item in self.sources)
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("A study scenario cannot repeat a source ID.")
        if not isinstance(self.active_equipment_ids, tuple) or any(
            not isinstance(identifier, UUID) for identifier in self.active_equipment_ids
        ):
            raise TypeError("active_equipment_ids must be a tuple of UUID values.")
        if len(set(self.active_equipment_ids)) != len(self.active_equipment_ids):
            raise ValueError("active_equipment_ids cannot contain duplicates.")
        if not isinstance(self.assumptions, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.assumptions
        ):
            raise TypeError("assumptions must be a tuple of non-empty strings.")
        object.__setattr__(self, "assumptions", tuple(item.strip() for item in self.assumptions))

    @property
    def current_case(self) -> IEC60909CurrentCase:
        """Expose the normalized maximum/minimum case without duplicating study data."""
        return self.study.current_case

    @property
    def required_sequences(self) -> frozenset[SequenceType]:
        """Sequence networks required by the declared fault connection.

        This is intentionally distinct from each source descriptor's
        ``active_sequences``: a source can induce a fault-current contribution
        in a sequence in which it has no independent internal source voltage.
        """
        if self.fault.fault_type is FaultType.THREE_PHASE:
            return frozenset({SequenceType.POSITIVE})
        if self.fault.fault_type is FaultType.LINE_TO_LINE:
            return frozenset({SequenceType.POSITIVE, SequenceType.NEGATIVE})
        return frozenset(SequenceType)
