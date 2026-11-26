from __future__ import annotations

from uuid import uuid4

import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.converter_control_mode import (
    ConverterControlMode,
    ConverterCurrentPriority,
)
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.line_model_kind import LineModelKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.value_objects.converter_current_command import (
    ConverterSequenceCurrentCommand,
)
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.iec60909_study import IEC60909StudySpecification
from power_fault_analyzer.domain.value_objects.impedance import Impedance
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.per_unit_impedance import PerUnitImpedance
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    AdmittancePerLength,
    ImpedancePerLength,
    SequenceAdmittancePerLengthSet,
    SequenceImpedancePerLengthSet,
)
from power_fault_analyzer.domain.value_objects.source_models import (
    ConverterFaultCurrentCapability,
    ExternalGridShortCircuitData,
    InductionGeneratorParameters,
    SynchronousMachineSequenceImpedances,
)
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    SequencePerUnitImpedance,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.sources import (
    ConverterBasedGenerator,
    ExternalGrid,
    InductionGenerator,
    SynchronousGenerator,
)
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters
from power_fault_analyzer.infrastructure.numerical.iec60909_source_contributions import (
    IEC60909SourceContributionAnalyzer,
)
from power_fault_analyzer.network.sequence_networks.builder import SequenceNetworkBuilder
from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet
from power_fault_analyzer.standards.iec60909 import (
    IEC60909SourceFamily,
    IEC60909SourceInventoryBuilder,
    IEC60909SourceMode,
    IEC60909StudyScenario,
    IEC60909TopologyClass,
)


def _add_source(network: Network, bus: Bus, source) -> None:
    network.add_equipment(source)
    network.connect(source.terminals[0].id, bus.id)


def _build_multi_source_network(*, grounded_synchronous: bool = False):
    network = Network("ND-014.2 source contribution network")
    bus = Bus("BUS-13K8", Voltage.from_kv(13.8))
    network.add_bus(bus)

    grid_id = uuid4()
    grid_terminal = Terminal(grid_id, "GRID", bus.nominal_voltage)
    grid = ExternalGrid(
        id=grid_id,
        name="GRID-A",
        terminal=grid_terminal,
        frequency=Frequency(60.0),
        short_circuit_data=ExternalGridShortCircuitData(
            short_circuit_power_mva=2500.0,
            rx_ratio=0.10,
            negative_sequence_impedance_ohm=Impedance(0.004, 0.035),
            zero_sequence_impedance_ohm=Impedance(0.009, 0.075),
            prefault_voltage_pu=0.99 + 0.01j,
        ),
    )
    _add_source(network, bus, grid)

    synchronous_id = uuid4()
    synchronous_terminal = Terminal(synchronous_id, "GEN", bus.nominal_voltage)
    synchronous = SynchronousGenerator(
        id=synchronous_id,
        name="GEN-SYNC-01",
        terminal=synchronous_terminal,
        frequency=Frequency(60.0),
        sequence_impedances=SynchronousMachineSequenceImpedances(
            base=ElectricalImpedanceBase(80.0, 13.8),
            positive_subtransient=PerUnitImpedance(0.015, 0.22),
            positive_transient=PerUnitImpedance(0.025, 0.31),
            positive_synchronous=PerUnitImpedance(0.04, 1.3),
            negative=PerUnitImpedance(0.02, 0.19),
            zero=PerUnitImpedance(0.03, 0.12),
        ),
        neutral_grounding=(
            NeutralGrounding.solid() if grounded_synchronous else NeutralGrounding.ungrounded()
        ),
        stator_connection=(
            WindingConnection.STAR if grounded_synchronous else WindingConnection.DELTA
        ),
        prefault_voltage_pu=1.02 - 0.015j,
    )
    _add_source(network, bus, synchronous)

    induction_id = uuid4()
    induction_terminal = Terminal(induction_id, "MOTOR-GEN", bus.nominal_voltage)
    induction = InductionGenerator(
        id=induction_id,
        name="GEN-ASYNC-01",
        terminal=induction_terminal,
        frequency=Frequency(60.0),
        parameters=InductionGeneratorParameters(
            rated_power_mva=25.0,
            sequence_impedances=SequencePerUnitImpedance(
                base=ElectricalImpedanceBase(25.0, 13.8),
                positive=PerUnitImpedance(0.025, 0.24),
                negative=PerUnitImpedance(0.035, 0.27),
                zero=PerUnitImpedance(0.05, 0.14),
            ),
            decay_time_constant_s=0.09,
            prefault_voltage_pu=0.98 + 0.005j,
        ),
        neutral_grounding=NeutralGrounding.solid(),
        stator_connection=WindingConnection.STAR,
    )
    _add_source(network, bus, induction)

    system_base = SystemBaseSet.from_network(network, 100.0)
    sequence_networks = SequenceNetworkBuilder(system_base).build_all(network)
    return network, bus, system_base, sequence_networks, (grid, synchronous, induction)


def _scenario(network, bus, system_base, sequence_networks, fault_type):
    sources = IEC60909SourceInventoryBuilder().build(network, sequence_networks)
    fault = FaultSpecification(fault_type, bus.id)
    study = IEC60909StudySpecification(
        current_case=IEC60909CurrentCase.MAXIMUM,
        fault_duration_s=1.0,
        frequency_hz=60.0,
    )
    scenario = IEC60909StudyScenario(
        network_id=network.id,
        fault=fault,
        system_base=system_base,
        study=study,
        topology_class=IEC60909TopologyClass.RADIAL,
        sources=sources,
    )
    return scenario


def test_inventory_classifies_network_feeder_and_rotating_machines():
    network, _bus, _base, sequence_networks, source_equipment = _build_multi_source_network()
    descriptors = IEC60909SourceInventoryBuilder().build(network, sequence_networks)
    by_id = {item.source_id: item for item in descriptors}

    assert len(descriptors) == 3
    assert by_id[source_equipment[0].id].family is IEC60909SourceFamily.NETWORK_FEEDER
    assert by_id[source_equipment[1].id].family is IEC60909SourceFamily.SYNCHRONOUS_MACHINE
    assert by_id[source_equipment[2].id].family is IEC60909SourceFamily.ASYNCHRONOUS_MACHINE
    assert all(item.mode is IEC60909SourceMode.VOLTAGE_SOURCE for item in descriptors)
    assert all(item.in_service for item in descriptors)


def test_source_contributions_reconstruct_total_for_all_fault_types():
    network, bus, base, sequence_networks, equipment = _build_multi_source_network(
        grounded_synchronous=False
    )
    analyzer = IEC60909SourceContributionAnalyzer()

    for fault_type in FaultType:
        scenario = _scenario(network, bus, base, sequence_networks, fault_type)
        analysis = analyzer.analyze(network, sequence_networks, scenario)
        assert {item.source_id for item in analysis.source_contributions} == {
            item.id for item in equipment
        }
        assert max(analysis.sequence_balance_residual_ka.values(), default=0.0) < 1e-8
        assert max(analysis.phase_balance_residual_ka.values()) < 1e-8
        assert analysis.trace.source_contributions == analysis.source_contributions
        assert any("correction factors" in item for item in analysis.trace.assumptions)

        # The delta-connected synchronous machine has no zero-sequence source path,
        # but its independently attributed fault contribution still has the
        # sequence components induced by the unbalanced fault boundary.
        if fault_type is FaultType.SINGLE_LINE_TO_GROUND:
            sync = next(
                item for item in analysis.source_contributions if item.source_id == equipment[1].id
            )
            assert SequenceType.ZERO in sync.sequence_currents_ka


def test_remote_rotating_machines_contribute_through_network_branches():
    network, fault_bus, _base, _sequence_networks, equipment = _build_multi_source_network()
    remote_bus = Bus("REMOTE-BUS-13K8", Voltage.from_kv(13.8))
    network.add_bus(remote_bus)
    for source in equipment[1:]:
        network.disconnect(source.terminals[0].id)
        network.connect(source.terminals[0].id, remote_bus.id)

    line_id = uuid4()
    line_terminals = (
        Terminal(line_id, "FROM", fault_bus.nominal_voltage),
        Terminal(line_id, "TO", remote_bus.nominal_voltage),
    )
    line_parameters = LineParameters(
        series_impedance_per_km=SequenceImpedancePerLengthSet(
            positive=ImpedancePerLength(0.08, 0.30),
            negative=ImpedancePerLength(0.09, 0.32),
            zero=ImpedancePerLength(0.25, 0.90),
        ),
        shunt_admittance_per_km=SequenceAdmittancePerLengthSet(
            positive=AdmittancePerLength(),
            negative=AdmittancePerLength(),
            zero=AdmittancePerLength(),
        ),
        reference_frequency=Frequency(60.0),
    )
    line = Line(
        id=line_id,
        name="GRID-TO-GENERATION-LINE",
        terminals=line_terminals,
        length_km=8.0,
        parameters=line_parameters,
        model_kind=LineModelKind.SERIES_ONLY,
    )
    network.add_equipment(line)
    network.connect(line_terminals[0].id, fault_bus.id)
    network.connect(line_terminals[1].id, remote_bus.id)

    system_base = SystemBaseSet.from_network(network, 100.0)
    sequence_networks = SequenceNetworkBuilder(system_base).build_all(network)
    scenario = _scenario(
        network,
        fault_bus,
        system_base,
        sequence_networks,
        FaultType.SINGLE_LINE_TO_GROUND,
    )
    analysis = IEC60909SourceContributionAnalyzer().analyze(
        network,
        sequence_networks,
        scenario,
    )

    assert len(analysis.source_contributions) == 3
    assert analysis.total_result.maximum_phase_current_ka > 0.0
    assert max(analysis.sequence_balance_residual_ka.values()) < 1e-8
    assert max(analysis.phase_balance_residual_ka.values()) < 1e-8


def test_converter_fixed_phasor_is_attributed_as_a_current_source():
    network, bus, base, _sequence_networks, _equipment = _build_multi_source_network()
    converter_id = uuid4()
    converter_capability = ConverterFaultCurrentCapability(
        base=ElectricalImpedanceBase(20.0, 13.8),
        overall_current_limit_pu=1.2,
        positive_sequence_limit_pu=1.0,
        negative_sequence_limit_pu=0.2,
        zero_sequence_limit_pu=0.1,
    )
    converter_terminal = Terminal(converter_id, "CONVERTER", bus.nominal_voltage)
    converter = ConverterBasedGenerator(
        id=converter_id,
        name="CONVERTER-01",
        terminal=converter_terminal,
        frequency=Frequency(60.0),
        control_mode=ConverterControlMode.GRID_FOLLOWING,
        current_priority=ConverterCurrentPriority.REACTIVE,
        fault_current_capability=converter_capability,
    )
    _add_source(network, bus, converter)
    sequence_networks = SequenceNetworkBuilder(base).build_all(network)
    scenario = _scenario(
        network,
        bus,
        base,
        sequence_networks,
        FaultType.SINGLE_LINE_TO_GROUND,
    )
    command = ConverterSequenceCurrentCommand(
        source_id=converter_id,
        bus_id=bus.id,
        capability=converter_capability,
        sequence_currents_pu={
            SequenceType.POSITIVE: 0.2 + 0.0j,
            SequenceType.NEGATIVE: 0.0j,
            SequenceType.ZERO: 0.0j,
        },
    )

    analysis = IEC60909SourceContributionAnalyzer().analyze(
        network,
        sequence_networks,
        scenario,
        converter_current_commands=(command,),
    )

    converter_contribution = next(
        item for item in analysis.source_contributions if item.source_id == converter_id
    )
    assert converter_contribution.source_family is IEC60909SourceFamily.CONVERTER
    assert converter_contribution.source_mode is IEC60909SourceMode.CURRENT_SOURCE
    assert abs(converter_contribution.sequence_currents_ka[SequenceType.POSITIVE]) > 0.0
    assert max(analysis.sequence_balance_residual_ka.values()) < 1e-8
    assert max(analysis.phase_balance_residual_ka.values()) < 1e-8
    assert any("fixed externally supplied" in item for item in analysis.trace.assumptions)


def test_analyzer_rejects_missing_or_invented_source_descriptors():
    network, bus, base, sequence_networks, _equipment = _build_multi_source_network()
    scenario = _scenario(network, bus, base, sequence_networks, FaultType.THREE_PHASE)
    invalid = scenario.__class__(
        network_id=scenario.network_id,
        fault=scenario.fault,
        system_base=scenario.system_base,
        study=scenario.study,
        topology_class=scenario.topology_class,
        sources=scenario.sources[:-1],
    )
    with pytest.raises(ValueError, match="match the sources stamped"):
        IEC60909SourceContributionAnalyzer().analyze(network, sequence_networks, invalid)


def test_analyzer_rejects_out_of_service_descriptor_that_remains_stamped():
    network, bus, base, sequence_networks, _equipment = _build_multi_source_network()
    scenario = _scenario(network, bus, base, sequence_networks, FaultType.THREE_PHASE)
    first = scenario.sources[0]
    changed = first.__class__(
        source_id=first.source_id,
        name=first.name,
        family=first.family,
        mode=first.mode,
        active_sequences=first.active_sequences,
        model_reference=first.model_reference,
        in_service=False,
    )
    invalid = scenario.__class__(
        network_id=scenario.network_id,
        fault=scenario.fault,
        system_base=scenario.system_base,
        study=scenario.study,
        topology_class=scenario.topology_class,
        sources=(changed, *scenario.sources[1:]),
    )
    with pytest.raises(ValueError, match="marked out of service"):
        IEC60909SourceContributionAnalyzer().analyze(network, sequence_networks, invalid)
