from uuid import uuid4

import numpy as np
import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.sequence_equipment_kind import SequenceEquipmentKind
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.value_objects.converter_current_command import (
    ConverterSequenceCurrentCommand,
)
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.per_unit_impedance import (
    PerUnitImpedance,
    SequencePerUnitImpedance,
)
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    AdmittancePerLength,
    ImpedancePerLength,
    SequenceAdmittancePerLengthSet,
    SequenceImpedancePerLengthSet,
)
from power_fault_analyzer.domain.value_objects.source_models import (
    ConverterFaultCurrentCapability,
)
from power_fault_analyzer.domain.value_objects.three_winding_zero_sequence import (
    ThreeWindingZeroSequencePortModel,
)
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PairwiseTransformerImpedances,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.transformers.three_winding_transformer import (
    ThreeWindingTransformer,
)
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters
from power_fault_analyzer.infrastructure.numerical.source_contributions import (
    ConverterCurrentInjectionSolver,
    SourceVoltageContributionCalculator,
)
from power_fault_analyzer.infrastructure.numerical.ybus import SparseYBusAssembler
from power_fault_analyzer.network.sequence_networks.builder import SequenceNetworkBuilder
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceBranch,
    SequenceMultiportElement,
    SequenceMutualCoupling,
    SequenceNetwork,
    SequenceNetworkSet,
    SequenceNode,
    SequenceShunt,
    SystemBaseSet,
)


def _three_winding_transformer(*, zero_model=None):
    equipment_id = uuid4()
    windings = (
        TransformerWinding(
            WindingDesignation.HIGH_VOLTAGE,
            220.0,
            100.0,
            WindingConnection.STAR,
            NeutralGrounding.solid(),
            True,
        ),
        TransformerWinding(
            WindingDesignation.MEDIUM_VOLTAGE,
            66.0,
            60.0,
            WindingConnection.STAR,
            NeutralGrounding.solid(),
            True,
        ),
        TransformerWinding(
            WindingDesignation.LOW_VOLTAGE,
            13.8,
            40.0,
            WindingConnection.DELTA,
            None,
        ),
    )
    base = ElectricalImpedanceBase(50.0, 220.0)

    def sequence_values(r, x):
        return SequencePerUnitImpedance(
            base,
            PerUnitImpedance(r, x),
            PerUnitImpedance(r * 1.05, x * 1.02),
            PerUnitImpedance(r * 1.2, x * 1.1),
        )

    terminals = (
        Terminal(equipment_id, "HV", Voltage.from_kv(220.0)),
        Terminal(equipment_id, "MV", Voltage.from_kv(66.0)),
        Terminal(equipment_id, "LV", Voltage.from_kv(13.8)),
    )
    transformer = ThreeWindingTransformer(
        id=equipment_id,
        name="TR3-EXPLICIT-Z0",
        terminals=terminals,
        windings=windings,
        frequency=Frequency(60.0),
        hv_mv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 0),
        hv_lv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.DELTA, 0),
        pairwise_impedances=PairwiseTransformerImpedances(
            sequence_values(0.01, 0.08),
            sequence_values(0.012, 0.09),
            sequence_values(0.013, 0.10),
        ),
        zero_sequence_port_model=zero_model,
    )
    return transformer


def _connect_three_winding(network, transformer):
    buses = (
        Bus("BUS-HV", Voltage.from_kv(220.0)),
        Bus("BUS-MV", Voltage.from_kv(66.0)),
        Bus("BUS-LV", Voltage.from_kv(13.8)),
    )
    for bus in buses:
        network.add_bus(bus)
    network.add_equipment(transformer)
    for terminal, bus in zip(transformer.terminals, buses, strict=True):
        network.connect(terminal.id, bus.id)
    return buses


def test_three_winding_transformer_stamps_explicit_zero_sequence_multiport():
    model_base = ElectricalImpedanceBase(50.0, 220.0)
    port_model = ThreeWindingZeroSequencePortModel(
        base=model_base,
        impedance_matrix_pu=(
            (0.12 + 0.35j, 0.015 + 0.04j, 0.01 + 0.025j),
            (0.015 + 0.04j, 0.16 + 0.42j, 0.012 + 0.03j),
            (0.01 + 0.025j, 0.012 + 0.03j, 0.2 + 0.5j),
        ),
        reference="Manufacturer zero-sequence three-port test report TR3-2026-04",
    )
    network = Network("explicit three-winding zero-sequence model")
    transformer = _three_winding_transformer(zero_model=port_model)
    buses = _connect_three_winding(network, transformer)
    system_base = SystemBaseSet.from_network(network, 100.0)

    sequence_network = SequenceNetworkBuilder(system_base).build(network, SequenceType.ZERO)

    assert sequence_network.is_complete
    assert len(sequence_network.multiport_elements) == 1
    assert not any(
        diagnostic.code == "SEQ-COMPONENT-UNREFERENCED"
        for diagnostic in sequence_network.diagnostics
    )
    assert not sequence_network.branches
    result = SparseYBusAssembler().assemble(sequence_network)
    expected_z = np.asarray(port_model.impedance_matrix_pu) * 2.0
    expected_y = np.linalg.inv(expected_z)
    indices = [result.node_index[bus.id] for bus in buses]
    actual = result.to_dense()[np.ix_(indices, indices)]
    assert actual == pytest.approx(expected_y)


def test_three_winding_zero_sequence_model_requires_reciprocal_nonsingular_matrix():
    base = ElectricalImpedanceBase(100.0, 220.0)
    with pytest.raises(ValueError, match="reciprocal/symmetric"):
        ThreeWindingZeroSequencePortModel(
            base,
            ((0.1 + 0.2j, 0.01j, 0j), (0.02j, 0.1 + 0.3j, 0j), (0j, 0j, 0.2 + 0.4j)),
            "test report",
        )
    with pytest.raises(ValueError, match="nonsingular"):
        ThreeWindingZeroSequencePortModel(
            base,
            ((0.1 + 0.2j, 0.1 + 0.2j, 0.1 + 0.2j),) * 3,
            "test report",
        )


def test_mutual_zero_sequence_coupling_is_stamped_as_coupled_series_branches():
    node_a, node_b = uuid4(), uuid4()
    first_id, second_id = uuid4(), uuid4()
    branches = (
        SequenceBranch(
            first_id,
            "LINE-1",
            node_a,
            node_b,
            0.1 + 0.4j,
            equipment_kind=SequenceEquipmentKind.LINE,
        ),
        SequenceBranch(
            second_id,
            "LINE-2",
            node_a,
            node_b,
            0.12 + 0.42j,
            equipment_kind=SequenceEquipmentKind.LINE,
        ),
    )
    network = SequenceNetwork(
        network_id=uuid4(),
        sequence=SequenceType.ZERO,
        nodes=(SequenceNode(node_a, "A"), SequenceNode(node_b, "B")),
        branches=branches,
        shunts=(),
        mutual_couplings=(
            SequenceMutualCoupling(SequenceType.ZERO, first_id, second_id, 0.03 + 0.1j),
        ),
    )
    result = SparseYBusAssembler().assemble(network)
    impedance = np.asarray([[0.1 + 0.4j, 0.03 + 0.1j], [0.03 + 0.1j, 0.12 + 0.42j]])
    expected_series_y = np.sum(np.linalg.inv(impedance))
    actual = result.to_dense()
    assert actual[0, 0] == pytest.approx(expected_series_y)
    assert actual[0, 1] == pytest.approx(-expected_series_y)
    assert actual[1, 0] == pytest.approx(-expected_series_y)
    assert actual[1, 1] == pytest.approx(expected_series_y)


def test_mutual_coupling_rejects_non_line_branches():
    node_a, node_b = uuid4(), uuid4()
    branch_a, branch_b = uuid4(), uuid4()
    with pytest.raises(ValueError, match="only between line branches"):
        SequenceNetwork(
            network_id=uuid4(),
            sequence=SequenceType.ZERO,
            nodes=(SequenceNode(node_a, "A"), SequenceNode(node_b, "B")),
            branches=(
                SequenceBranch(branch_a, "A", node_a, node_b, 0.1 + 0.2j),
                SequenceBranch(branch_b, "B", node_a, node_b, 0.2 + 0.3j),
            ),
            shunts=(),
            mutual_couplings=(
                SequenceMutualCoupling(SequenceType.ZERO, branch_a, branch_b, 0.01 + 0.02j),
            ),
        )


def test_multiple_thevenin_sources_are_decomposed_by_superposition():
    bus_id = uuid4()
    first_id, second_id = uuid4(), uuid4()
    network = SequenceNetwork(
        network_id=uuid4(),
        sequence=SequenceType.POSITIVE,
        nodes=(SequenceNode(bus_id, "BUS-1"),),
        branches=(),
        shunts=(
            SequenceShunt(
                first_id,
                "GRID-A",
                bus_id,
                2.0 + 0j,
                1.0 + 0j,
                SequenceSourceKind.NETWORK_FEEDER,
            ),
            SequenceShunt(
                second_id,
                "GRID-B",
                bus_id,
                3.0 + 0j,
                0.9 + 0j,
                SequenceSourceKind.NETWORK_FEEDER,
            ),
        ),
    )
    ybus = SparseYBusAssembler().assemble(network)
    result = SourceVoltageContributionCalculator().calculate(ybus, bus_id)
    assert result.contributions_pu[first_id] == pytest.approx(0.4 + 0j)
    assert result.contributions_pu[second_id] == pytest.approx(0.54 + 0j)
    assert result.total_voltage_pu == pytest.approx(0.94 + 0j)
    assert result.reconstructed_voltage_pu == pytest.approx(result.total_voltage_pu)
    assert result.residual_pu < 1e-12


def test_converter_sequence_current_commands_are_solved_on_all_sequence_networks():
    source_id, bus_id = uuid4(), uuid4()
    base = ElectricalImpedanceBase(100.0, 13.8)
    capability = ConverterFaultCurrentCapability(
        base,
        overall_current_limit_pu=1.2,
        positive_sequence_limit_pu=1.0,
        negative_sequence_limit_pu=0.2,
        zero_sequence_limit_pu=0.1,
    )
    network_id = uuid4()

    def make_network(sequence):
        return SequenceNetwork(
            network_id,
            sequence,
            (SequenceNode(bus_id, "CONVERTER-BUS"),),
            (),
            (SequenceShunt(uuid4(), "GRID-REFERENCE", bus_id, 10.0 + 0j),),
            nonlinear_source_ids=(source_id,),
            converter_capabilities={source_id: capability},
            converter_bus_ids={source_id: bus_id},
        )

    sequence_set = SequenceNetworkSet(
        positive=make_network(SequenceType.POSITIVE),
        negative=make_network(SequenceType.NEGATIVE),
        zero=make_network(SequenceType.ZERO),
    )
    command = ConverterSequenceCurrentCommand(
        source_id,
        bus_id,
        capability,
        {
            SequenceType.POSITIVE: 0.5 + 0j,
            SequenceType.NEGATIVE: 0.1 + 0j,
            SequenceType.ZERO: 0.05 + 0j,
        },
    )
    results = ConverterCurrentInjectionSolver().solve_all(
        sequence_set, SystemBaseSet(100.0, {bus_id: 13.8}), (command,)
    )
    assert results[SequenceType.POSITIVE].node_voltages_pu[bus_id] == pytest.approx(0.05 + 0j)
    assert results[SequenceType.NEGATIVE].node_voltages_pu[bus_id] == pytest.approx(0.01 + 0j)
    assert results[SequenceType.ZERO].node_voltages_pu[bus_id] == pytest.approx(0.005 + 0j)
    assert all(result.residual_norm < 1e-12 for result in results.values())


def test_converter_nonzero_sequence_without_declared_limit_is_rejected():
    source_id, bus_id = uuid4(), uuid4()
    capability = ConverterFaultCurrentCapability(
        ElectricalImpedanceBase(100.0, 13.8), 1.0, 0.8, None, None
    )
    command = ConverterSequenceCurrentCommand(
        source_id,
        bus_id,
        capability,
        {
            SequenceType.POSITIVE: 0.5 + 0j,
            SequenceType.NEGATIVE: 0.1 + 0j,
            SequenceType.ZERO: 0j,
        },
    )
    with pytest.raises(ValueError, match="negative-sequence.*unspecified"):
        command.validate_limits(SystemBaseSet(100.0, {bus_id: 13.8}))


def test_builder_attaches_declared_mutual_coupling_only_to_requested_sequence():
    network = Network("parallel coupled circuits")
    bus_a = Bus("BUS-A", Voltage.from_kv(115.0))
    bus_b = Bus("BUS-B", Voltage.from_kv(115.0))
    network.add_bus(bus_a)
    network.add_bus(bus_b)
    line_parameters = LineParameters(
        SequenceImpedancePerLengthSet(
            ImpedancePerLength(0.08, 0.32),
            ImpedancePerLength(0.09, 0.34),
            ImpedancePerLength(0.25, 0.95),
        ),
        SequenceAdmittancePerLengthSet(
            AdmittancePerLength(0.0, 0.0),
            AdmittancePerLength(0.0, 0.0),
            AdmittancePerLength(0.0, 0.0),
        ),
        Frequency(60.0),
    )
    line_ids = []
    for suffix in ("1", "2"):
        equipment_id = uuid4()
        terminals = (
            Terminal(equipment_id, f"FROM-{suffix}", Voltage.from_kv(115.0)),
            Terminal(equipment_id, f"TO-{suffix}", Voltage.from_kv(115.0)),
        )
        line = Line(
            id=equipment_id,
            name=f"LINE-{suffix}",
            terminals=terminals,
            length_km=10.0,
            parameters=line_parameters,
        )
        network.add_equipment(line)
        network.connect(terminals[0].id, bus_a.id)
        network.connect(terminals[1].id, bus_b.id)
        line_ids.append(equipment_id)
    coupling = SequenceMutualCoupling(SequenceType.ZERO, line_ids[0], line_ids[1], 0.015 + 0.06j)
    builder = SequenceNetworkBuilder(
        SystemBaseSet.from_network(network, 100.0), mutual_couplings=(coupling,)
    )
    positive = builder.build(network, SequenceType.POSITIVE)
    zero = builder.build(network, SequenceType.ZERO)
    assert not positive.mutual_couplings
    assert zero.mutual_couplings == (coupling,)
    assert SparseYBusAssembler().assemble(zero).matrix.shape == (2, 2)


def test_sequence_network_requires_converter_bus_and_capability_registration_together():
    source_id, bus_id = uuid4(), uuid4()
    capability = ConverterFaultCurrentCapability(
        ElectricalImpedanceBase(100.0, 13.8), 1.0, 0.8, 0.2, 0.1
    )
    with pytest.raises(ValueError, match="same source IDs"):
        SequenceNetwork(
            uuid4(),
            SequenceType.POSITIVE,
            (SequenceNode(bus_id, "BUS-1"),),
            (),
            (),
            nonlinear_source_ids=(source_id,),
            converter_capabilities={source_id: capability},
        )


def test_sequence_network_rejects_converter_bus_outside_network_nodes():
    source_id, bus_id, unknown_bus_id = uuid4(), uuid4(), uuid4()
    capability = ConverterFaultCurrentCapability(
        ElectricalImpedanceBase(100.0, 13.8), 1.0, 0.8, 0.2, 0.1
    )
    with pytest.raises(ValueError, match="must reference nodes"):
        SequenceNetwork(
            uuid4(),
            SequenceType.POSITIVE,
            (SequenceNode(bus_id, "BUS-1"),),
            (),
            (),
            nonlinear_source_ids=(source_id,),
            converter_capabilities={source_id: capability},
            converter_bus_ids={source_id: unknown_bus_id},
        )


def test_zero_sequence_multiport_accepts_lossless_scaled_matrix_and_rejects_active_resistance():
    port_ids = (uuid4(), uuid4(), uuid4())
    base = ElectricalImpedanceBase(100.0, 220.0)
    lossless_matrix = (
        (1.0e-6j, 0.1e-6j, 0.05e-6j),
        (0.1e-6j, 1.5e-6j, 0.08e-6j),
        (0.05e-6j, 0.08e-6j, 2.0e-6j),
    )

    port_model = ThreeWindingZeroSequencePortModel(
        base,
        lossless_matrix,
        "Validated lossless three-port numerical fixture",
    )
    element = SequenceMultiportElement(
        uuid4(),
        "LOSSLESS-PORTS",
        port_ids,
        lossless_matrix,
    )

    assert port_model.impedance_matrix_pu == lossless_matrix
    assert element.impedance_matrix_pu == lossless_matrix

    non_passive_matrix = (
        (-1.0e-6 + 1.0e-3j, 0j, 0j),
        (0j, 2.0e-6 + 1.5e-3j, 0j),
        (0j, 0j, 3.0e-6 + 2.0e-3j),
    )
    with pytest.raises(ValueError, match="passive"):
        ThreeWindingZeroSequencePortModel(
            base,
            non_passive_matrix,
            "Invalid active three-port fixture",
        )
