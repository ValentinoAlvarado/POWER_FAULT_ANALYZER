"""Build a source inventory from the physical network and sequence models."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.network.sequence_networks.models import SequenceNetworkSet
from power_fault_analyzer.standards.iec60909.models import (
    IEC60909SourceDescriptor,
    IEC60909SourceFamily,
    IEC60909SourceMode,
)

_SOURCE_FAMILIES = {
    SequenceSourceKind.NETWORK_FEEDER: IEC60909SourceFamily.NETWORK_FEEDER,
    SequenceSourceKind.SYNCHRONOUS_MACHINE: IEC60909SourceFamily.SYNCHRONOUS_MACHINE,
    SequenceSourceKind.ASYNCHRONOUS_MACHINE: IEC60909SourceFamily.ASYNCHRONOUS_MACHINE,
    SequenceSourceKind.EXPLICIT_THEVENIN: IEC60909SourceFamily.OTHER,
}


@dataclass(slots=True)
class _SourceRecord:
    """Mutable accumulator used only while constructing immutable descriptors."""

    name: str
    family: IEC60909SourceFamily
    mode: IEC60909SourceMode
    model_reference: str
    active_sequences: set[SequenceType] = field(default_factory=set)


class IEC60909SourceInventoryBuilder:
    """Create source descriptors from source models actually stamped.

    The physical network has no independent in-service switch state in the current
    domain model. Consequently, a source represented in the supplied sequence
    networks is treated as in service. Out-of-service switching scenarios must be
    reflected in the network model before this builder is called.
    """

    def build(
        self,
        network: NetworkAggregate,
        networks: SequenceNetworkSet,
    ) -> tuple[IEC60909SourceDescriptor, ...]:
        if not isinstance(networks, SequenceNetworkSet):
            raise TypeError("networks must be a SequenceNetworkSet value.")
        if not hasattr(network, "id") or not callable(getattr(network, "get_equipment", None)):
            raise TypeError("network must implement the NetworkAggregate contract.")
        if network.id != networks.network_id:
            raise ValueError("Physical network ID does not match the sequence-network set.")

        records: dict[UUID, _SourceRecord] = {}
        for sequence in SequenceType:
            sequence_network = networks.for_sequence(sequence)
            for shunt in sequence_network.shunts:
                if shunt.source_kind is SequenceSourceKind.PASSIVE:
                    if abs(shunt.source_voltage_pu) > 1e-12:
                        raise ValueError(
                            f"Passive shunt '{shunt.name}' contains a non-zero source voltage."
                        )
                    continue
                family = _SOURCE_FAMILIES[shunt.source_kind]
                self._add_record(
                    records,
                    network,
                    source_id=shunt.id,
                    name=shunt.name,
                    family=family,
                    mode=IEC60909SourceMode.VOLTAGE_SOURCE,
                    sequence=sequence,
                    model_reference=f"sequence-thevenin:{shunt.source_kind.value}",
                )

            for source_id in sequence_network.nonlinear_source_ids:
                equipment = network.get_equipment(source_id)
                if equipment.family is not EquipmentFamily.CONVERTER:
                    raise ValueError(
                        f"Nonlinear source '{equipment.name}' is not converter equipment."
                    )
                self._add_record(
                    records,
                    network,
                    source_id=source_id,
                    name=equipment.name,
                    family=IEC60909SourceFamily.CONVERTER,
                    mode=IEC60909SourceMode.CURRENT_SOURCE,
                    sequence=sequence,
                    model_reference="explicit-sequence-current-command",
                )

        descriptors = tuple(
            IEC60909SourceDescriptor(
                source_id=source_id,
                name=record.name,
                family=record.family,
                mode=record.mode,
                active_sequences=frozenset(record.active_sequences),
                model_reference=record.model_reference,
                in_service=True,
            )
            for source_id, record in records.items()
            if record.active_sequences
        )
        return tuple(
            sorted(descriptors, key=lambda item: (item.name.casefold(), str(item.source_id)))
        )

    @staticmethod
    def _add_record(
        records: dict[UUID, _SourceRecord],
        network: NetworkAggregate,
        *,
        source_id: UUID,
        name: str,
        family: IEC60909SourceFamily,
        mode: IEC60909SourceMode,
        sequence: SequenceType,
        model_reference: str,
    ) -> None:
        equipment = network.get_equipment(source_id)
        if equipment.name != name:
            raise ValueError(
                f"Source name mismatch for '{source_id}': sequence model has '{name}', "
                f"physical network has '{equipment.name}'."
            )
        record = records.get(source_id)
        if record is None:
            records[source_id] = _SourceRecord(
                name=name,
                family=family,
                mode=mode,
                model_reference=model_reference,
                active_sequences={sequence},
            )
            return
        if (
            record.name != name
            or record.family is not family
            or record.mode is not mode
            or record.model_reference != model_reference
        ):
            raise ValueError(f"Source '{name}' has inconsistent models across sequence networks.")
        record.active_sequences.add(sequence)
