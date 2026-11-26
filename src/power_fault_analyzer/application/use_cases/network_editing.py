"""Use cases for editing real electrical entities in a physical Network aggregate."""

from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID, uuid4

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.line_model_kind import LineModelKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.switching_device import SwitchPosition
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.per_unit_impedance import PerUnitImpedance
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    ImpedancePerLength,
    SequenceAdmittancePerLengthSet,
    SequenceImpedancePerLengthSet,
)
from power_fault_analyzer.domain.value_objects.source_models import (
    SourceEquivalentSet,
    SourceSequenceEquivalent,
    SynchronousMachineSequenceImpedances,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.sources.synchronous_generator import SynchronousGenerator
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters


@dataclass(frozen=True, slots=True)
class SynchronousGeneratorInput:
    name: str
    bus_id: UUID
    base_power_mva: float
    frequency_hz: float
    positive_subtransient_pu: complex
    positive_transient_pu: complex
    positive_synchronous_pu: complex
    negative_pu: complex
    zero_pu: complex
    prefault_voltage_pu: complex
    neutral_grounding: NeutralGrounding
    stator_connection: WindingConnection = WindingConnection.STAR


@dataclass(frozen=True, slots=True)
class LineInput:
    name: str
    from_bus_id: UUID
    to_bus_id: UUID
    length_km: float
    positive_ohm_per_km: complex
    negative_ohm_per_km: complex
    zero_ohm_per_km: complex
    frequency_hz: float = 60.0


class AddBusToNetwork:
    def execute(self, network: Network, name: str, nominal_voltage_kv: float) -> Bus:
        if not isinstance(network, Network):
            raise TypeError("network must be a Network aggregate.")
        bus = Bus(name=name, nominal_voltage=Voltage.from_kv(nominal_voltage_kv))
        network.add_bus(bus)
        return bus


class RemoveBusFromNetwork:
    def execute(self, network: Network, bus_id: UUID) -> None:
        network.remove_bus(bus_id)


class AddSynchronousGeneratorToNetwork:
    def execute(
        self, network: Network, specification: SynchronousGeneratorInput
    ) -> SynchronousGenerator:
        if not isinstance(network, Network):
            raise TypeError("network must be a Network aggregate.")
        if not isinstance(specification, SynchronousGeneratorInput):
            raise TypeError("specification must be SynchronousGeneratorInput.")
        bus = network.get_bus(specification.bus_id)
        identifier = uuid4()
        terminal = Terminal(
            equipment_id=identifier,
            designation="HV",
            rated_voltage=bus.nominal_voltage,
        )
        base = ElectricalImpedanceBase(specification.base_power_mva, bus.nominal_voltage.value_kv)
        impedances = SynchronousMachineSequenceImpedances(
            base=base,
            positive_subtransient=_to_pu(specification.positive_subtransient_pu),
            positive_transient=_to_pu(specification.positive_transient_pu),
            positive_synchronous=_to_pu(specification.positive_synchronous_pu),
            negative=_to_pu(specification.negative_pu),
            zero=_to_pu(specification.zero_pu),
        )
        generator = SynchronousGenerator(
            id=identifier,
            name=specification.name,
            terminal=terminal,
            frequency=Frequency(specification.frequency_hz),
            sequence_impedances=impedances,
            neutral_grounding=specification.neutral_grounding,
            stator_connection=specification.stator_connection,
            prefault_voltage_pu=specification.prefault_voltage_pu,
        )
        network.add_equipment(generator)
        network.connect(terminal.id, bus.id)
        return generator


class AddLineBetweenBuses:
    """Add a physical series-only line using explicit ohm/km sequence parameters."""

    def execute(self, network: Network, specification: LineInput) -> Line:
        if not isinstance(network, Network):
            raise TypeError("network must be a Network aggregate.")
        if not isinstance(specification, LineInput):
            raise TypeError("specification must be LineInput.")
        from_bus = network.get_bus(specification.from_bus_id)
        to_bus = network.get_bus(specification.to_bus_id)
        if not math.isclose(
            from_bus.nominal_voltage.value_kv,
            to_bus.nominal_voltage.value_kv,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "A series line cannot connect different nominal voltage levels; "
                "model an explicit transformer between voltage zones."
            )
        identifier = uuid4()
        terminals = (
            Terminal(identifier, "From", from_bus.nominal_voltage),
            Terminal(identifier, "To", to_bus.nominal_voltage),
        )
        series = SequenceImpedancePerLengthSet(
            positive=_to_per_length(specification.positive_ohm_per_km),
            negative=_to_per_length(specification.negative_ohm_per_km),
            zero=_to_per_length(specification.zero_ohm_per_km),
        )
        parameters = LineParameters(
            series_impedance_per_km=series,
            shunt_admittance_per_km=SequenceAdmittancePerLengthSet.all_zero(),
            reference_frequency=Frequency(specification.frequency_hz),
        )
        line = Line(
            id=identifier,
            name=specification.name,
            terminals=terminals,
            length_km=specification.length_km,
            parameters=parameters,
            model_kind=LineModelKind.SERIES_ONLY,
        )
        network.add_equipment(line)
        network.connect(terminals[0].id, from_bus.id)
        network.connect(terminals[1].id, to_bus.id)
        return line


class AddTheveninEquivalentSourceToNetwork:
    def execute(
        self,
        network: Network,
        *,
        name: str,
        bus_id: UUID,
        base_power_mva: float,
        positive_sequence_pu: complex,
        negative_sequence_pu: complex,
        zero_sequence_pu: complex,
        prefault_voltage_pu: complex,
        frequency_hz: float = 60.0,
    ) -> EquivalentSource:
        bus = network.get_bus(bus_id)
        identifier = uuid4()
        terminal = Terminal(identifier, "HV", bus.nominal_voltage)
        base = ElectricalImpedanceBase(base_power_mva, bus.nominal_voltage.value_kv)
        positive = SourceSequenceEquivalent(
            SequenceType.POSITIVE,
            _available_status(),
            _to_pu(positive_sequence_pu),
            prefault_voltage_pu,
        )
        negative = SourceSequenceEquivalent(
            SequenceType.NEGATIVE,
            _available_status(),
            _to_pu(negative_sequence_pu),
        )
        zero = SourceSequenceEquivalent(
            SequenceType.ZERO,
            _available_status(),
            _to_pu(zero_sequence_pu),
        )
        source = EquivalentSource(
            id=identifier,
            name=name,
            terminal=terminal,
            frequency=Frequency(frequency_hz),
            equivalent=SourceEquivalentSet(base, positive, negative, zero),
        )
        network.add_equipment(source)
        network.connect(terminal.id, bus.id)
        return source


class RemoveEquipmentFromNetwork:
    def execute(self, network: Network, equipment_id: UUID) -> None:
        network.remove_equipment(equipment_id)


class SetSwitchPosition:
    """Change one explicitly modelled switch state without changing terminal identity."""

    def execute(
        self, network: Network, equipment_id: UUID, position: SwitchPosition
    ) -> SwitchingDevice:
        if not isinstance(network, Network):
            raise TypeError("network must be a Network aggregate.")
        if not isinstance(position, SwitchPosition):
            raise TypeError("position must be a SwitchPosition value.")
        equipment = network.get_equipment(equipment_id)
        if not isinstance(equipment, SwitchingDevice):
            raise TypeError("The selected equipment is not a switching device.")
        updated = equipment.with_position(position)
        network.replace_equipment(updated)
        return updated


class UpdateBusInNetwork:
    """Replace an immutable bus while preserving topology and all equipment IDs."""

    def execute(
        self, network: Network, bus_id: UUID, *, new_name: str, nominal_voltage_kv: float
    ) -> Network:
        if not isinstance(network, Network):
            raise TypeError("network must be a Network aggregate.")
        previous = network.get_bus(bus_id)
        replacement = Bus(
            id=previous.id,
            name=new_name,
            nominal_voltage=Voltage.from_kv(nominal_voltage_kv),
            kind=previous.kind,
        )
        updated = Network(network.name, id=network.id)
        for bus in network.buses:
            updated.add_bus(replacement if bus.id == bus_id else bus)
        for equipment in network.equipment:
            updated.add_equipment(equipment)
        for connection in network.connections:
            updated.connect(connection.terminal_id, connection.bus_id)
        return updated


def _to_pu(value: complex) -> PerUnitImpedance:
    return PerUnitImpedance(complex(value).real, complex(value).imag)


def _to_per_length(value: complex) -> ImpedancePerLength:
    return ImpedancePerLength(complex(value).real, complex(value).imag)


def _available_status():
    from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus

    return SourceSequenceStatus.AVAILABLE
