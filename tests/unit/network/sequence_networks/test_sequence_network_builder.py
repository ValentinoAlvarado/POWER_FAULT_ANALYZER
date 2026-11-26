from uuid import uuid4

import numpy as np
import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode
from power_fault_analyzer.domain.enums.sequence_equipment_kind import SequenceEquipmentKind
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.impedance import Impedance
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
from power_fault_analyzer.domain.value_objects.source_models import ExternalGridShortCircuitData
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PairwiseTransformerImpedances,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.sources.external_grid import ExternalGrid
from power_fault_analyzer.equipment.transformers.three_winding_transformer import (
    ThreeWindingTransformer,
)
from power_fault_analyzer.equipment.transformers.two_winding_transformer import (
    TwoWindingTransformer,
)
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters
from power_fault_analyzer.network.sequence_networks.builder import SequenceNetworkBuilder
from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet


def make_line_parameters():
    return LineParameters(
        series_impedance_per_km=SequenceImpedancePerLengthSet(
            positive=ImpedancePerLength(0.1, 0.4),
            negative=ImpedancePerLength(0.12, 0.42),
            zero=ImpedancePerLength(0.3, 1.2),
        ),
        shunt_admittance_per_km=SequenceAdmittancePerLengthSet(
            positive=AdmittancePerLength(1e-6, 4e-6),
            negative=AdmittancePerLength(1.2e-6, 4.2e-6),
            zero=AdmittancePerLength(0.5e-6, 2e-6),
        ),
        reference_frequency=Frequency(60.0),
    )


def make_two_bus_line_network(voltage_kv=13.8):
    network = Network("ND005 line network")
    buses = (Bus("BUS-A", Voltage.from_kv(voltage_kv)), Bus("BUS-B", Voltage.from_kv(voltage_kv)))
    for bus in buses:
        network.add_bus(bus)
    equipment_id = uuid4()
    terminals = (
        Terminal(equipment_id, "FROM", Voltage.from_kv(voltage_kv)),
        Terminal(equipment_id, "TO", Voltage.from_kv(voltage_kv)),
    )
    line = Line(
        id=equipment_id,
        name="LINE-AB",
        terminals=terminals,
        length_km=1.0,
        parameters=make_line_parameters(),
    )
    network.add_equipment(line)
    network.connect(terminals[0].id, buses[0].id)
    network.connect(terminals[1].id, buses[1].id)
    base = SystemBaseSet.from_network(network, 100.0)
    return network, buses, line, base


def make_external_grid(bus, *, include_all_sequences=True):
    equipment_id = uuid4()
    terminal = Terminal(equipment_id, "GRID", bus.nominal_voltage)
    data = ExternalGridShortCircuitData(
        short_circuit_power_mva=5000.0,
        rx_ratio=0.1,
        negative_sequence_impedance_ohm=Impedance(0.002, 0.02) if include_all_sequences else None,
        zero_sequence_impedance_ohm=Impedance(0.004, 0.04) if include_all_sequences else None,
        prefault_voltage_pu=0.98 + 0.02j,
    )
    return ExternalGrid(
        id=equipment_id,
        name="GRID-01",
        terminal=terminal,
        frequency=Frequency(60.0),
        short_circuit_data=data,
    )


def make_two_winding_transformer(
    *,
    hv_connection=WindingConnection.STAR,
    lv_connection=WindingConnection.DELTA,
    hv_grounding=None,
    lv_grounding=None,
    clock=11,
):
    equipment_id = uuid4()
    if hv_connection is WindingConnection.DELTA:
        hv_grounding = None
    elif hv_grounding is None:
        hv_grounding = NeutralGrounding.solid()
    if lv_connection is WindingConnection.DELTA:
        lv_grounding = None
    elif lv_grounding is None:
        lv_grounding = NeutralGrounding.solid()
    hv = TransformerWinding(
        WindingDesignation.HIGH_VOLTAGE,
        115.0,
        40.0,
        hv_connection,
        hv_grounding,
        neutral_terminal_available=(
            hv_grounding is not None and hv_grounding.mode is not GroundingMode.UNGROUNDED
        ),
    )
    lv = TransformerWinding(
        WindingDesignation.LOW_VOLTAGE,
        13.8,
        40.0,
        lv_connection,
        lv_grounding,
        neutral_terminal_available=(
            lv_grounding is not None and lv_grounding.mode is not GroundingMode.UNGROUNDED
        ),
    )
    terminals = (
        Terminal(equipment_id, "HV", Voltage.from_kv(115.0)),
        Terminal(equipment_id, "LV", Voltage.from_kv(13.8)),
    )
    base = ElectricalImpedanceBase(40.0, 115.0)
    impedances = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(0.01, 0.08),
        PerUnitImpedance(0.012, 0.082),
        PerUnitImpedance(0.015, 0.09),
    )
    return TwoWindingTransformer(
        id=equipment_id,
        name="TR-2W",
        terminals=terminals,
        windings=(hv, lv),
        frequency=Frequency(60.0),
        vector_group=VectorGroup(hv_connection, lv_connection, clock),
        sequence_impedances=impedances,
    )


def connect_transformer(network, transformer, voltages):
    buses = tuple(Bus(f"BUS-{i}", Voltage.from_kv(v)) for i, v in enumerate(voltages))
    for bus in buses:
        network.add_bus(bus)
    network.add_equipment(transformer)
    for terminal, bus in zip(transformer.terminals, buses, strict=True):
        network.connect(terminal.id, bus.id)
    return buses


def test_system_base_uses_common_mva_and_voltage_base_per_bus():
    network, buses, _, base = make_two_bus_line_network()
    assert base.base_power_mva == 100.0
    assert base.for_bus(buses[0].id) == ElectricalImpedanceBase(100.0, 13.8)
    base.validate_network(network)


def test_system_base_rejects_voltage_base_that_disagrees_with_bus_nominal():
    network, buses, _, _ = make_two_bus_line_network()
    bad = SystemBaseSet(100.0, {buses[0].id: 11.0, buses[1].id: 13.8})
    with pytest.raises(ValueError, match="does not match its nominal voltage"):
        SequenceNetworkBuilder(bad).build(network, SequenceType.POSITIVE)


def test_builder_converts_line_impedance_and_shunt_to_pu():
    network, buses, line, base = make_two_bus_line_network()
    model = SequenceNetworkBuilder(base).build(network, SequenceType.POSITIVE)
    branch = next(item for item in model.branches if item.id == line.id)
    z_base = 13.8**2 / 100.0
    assert branch.series_impedance_pu == pytest.approx((0.1 + 0.4j) / z_base)
    assert branch.shunt_admittance_from_pu == pytest.approx((0.5e-6 + 2e-6j) * z_base)
    assert branch.from_node_id == buses[0].id
    assert branch.to_node_id == buses[1].id


def test_builder_preserves_distinct_sequence_line_models():
    network, _, _, base = make_two_bus_line_network()
    builder = SequenceNetworkBuilder(base)
    positive = builder.build(network, SequenceType.POSITIVE).branches[0]
    negative = builder.build(network, SequenceType.NEGATIVE).branches[0]
    zero = builder.build(network, SequenceType.ZERO).branches[0]
    assert positive.series_impedance_pu != negative.series_impedance_pu
    assert negative.series_impedance_pu != zero.series_impedance_pu


def test_builder_reports_unconnected_line_terminal_as_error():
    network, _buses, line, base = make_two_bus_line_network()
    network.disconnect(line.terminals[1].id)
    model = SequenceNetworkBuilder(base).build(network, SequenceType.POSITIVE)
    assert not model.is_complete
    assert any(item.code == "SEQ-EQUIPMENT-BUILD-FAILED" for item in model.diagnostics)


def test_builder_rejects_a_line_across_different_voltage_bases():
    network = Network("invalid cross-voltage line")
    bus_a, bus_b = Bus("A", Voltage.from_kv(13.8)), Bus("B", Voltage.from_kv(6.6))
    network.add_bus(bus_a)
    network.add_bus(bus_b)
    equipment_id = uuid4()
    terms = (
        Terminal(equipment_id, "FROM", bus_a.nominal_voltage),
        Terminal(equipment_id, "TO", bus_b.nominal_voltage),
    )
    line = Line(
        id=equipment_id,
        name="BAD-LINE",
        terminals=terms,
        length_km=1.0,
        parameters=make_line_parameters(),
    )
    network.add_equipment(line)
    network.connect(terms[0].id, bus_a.id)
    network.connect(terms[1].id, bus_b.id)
    base = SystemBaseSet.from_network(network, 100.0)
    model = SequenceNetworkBuilder(base).build(network, SequenceType.POSITIVE)
    assert not model.is_complete
    assert any("equal voltage bases" in item.message for item in model.diagnostics)


def test_external_grid_is_stamped_as_thevenin_shunt_and_norton_injection():
    network = Network("source network")
    bus = Bus("GRID-BUS", Voltage.from_kv(13.8))
    network.add_bus(bus)
    source = make_external_grid(bus)
    network.add_equipment(source)
    network.connect(source.terminal.id, bus.id)
    base = SystemBaseSet.from_network(network, 100.0)
    model = SequenceNetworkBuilder(base).build(network, SequenceType.POSITIVE)
    assert len(model.shunts) == 1
    shunt = model.shunts[0]
    assert shunt.node_id == bus.id
    assert shunt.source_voltage_pu == pytest.approx(0.98 + 0.02j)
    assert shunt.admittance_pu != 0j
    assert shunt.source_kind is SequenceSourceKind.NETWORK_FEEDER


def test_external_grid_unspecified_sequence_is_not_silently_treated_as_open():
    network = Network("unspecified grid sequence")
    bus = Bus("GRID-BUS", Voltage.from_kv(13.8))
    network.add_bus(bus)
    source = make_external_grid(bus, include_all_sequences=False)
    network.add_equipment(source)
    network.connect(source.terminal.id, bus.id)
    model = SequenceNetworkBuilder(SystemBaseSet.from_network(network, 100.0)).build(
        network, SequenceType.ZERO
    )
    assert not model.is_complete
    assert not model.shunts
    assert any(item.code == "SEQ-SOURCE-SEQUENCE-UNSPECIFIED" for item in model.diagnostics)


def test_two_winding_transformer_positive_and_negative_taps_are_conjugates():
    network = Network("two winding transformer")
    transformer = make_two_winding_transformer()
    buses = connect_transformer(network, transformer, (115.0, 13.8))
    base = SystemBaseSet.from_network(network, 100.0)
    builder = SequenceNetworkBuilder(base)
    positive = builder.build(network, SequenceType.POSITIVE).branches[0]
    negative = builder.build(network, SequenceType.NEGATIVE).branches[0]
    expected = np.exp(1j * np.deg2rad(330.0))
    assert positive.tap_from == pytest.approx(expected)
    assert negative.tap_from == pytest.approx(expected.conjugate())
    assert positive.from_node_id == buses[0].id
    assert positive.to_node_id == buses[1].id
    assert positive.equipment_kind is SequenceEquipmentKind.TWO_WINDING_TRANSFORMER
    assert positive.transformer_reactance_pu == pytest.approx(
        transformer.get_sequence_impedance_pu(SequenceType.POSITIVE).value_pu.imag
    )
    assert positive.transformer_correction_voltage_kv == pytest.approx(13.8)


def test_yn_delta_transformer_zero_sequence_is_grounded_side_shunt():
    network = Network("YNd zero sequence")
    transformer = make_two_winding_transformer()
    buses = connect_transformer(network, transformer, (115.0, 13.8))
    model = SequenceNetworkBuilder(SystemBaseSet.from_network(network, 100.0)).build(
        network, SequenceType.ZERO
    )
    assert not model.branches
    assert len(model.shunts) == 1
    assert model.shunts[0].node_id == buses[0].id
    assert model.shunts[0].name.endswith("ZERO-SEQUENCE-GROUND-PATH")
    assert model.shunts[0].equipment_kind is SequenceEquipmentKind.TWO_WINDING_TRANSFORMER
    assert model.shunts[0].transformer_correction_voltage_kv == pytest.approx(13.8)


def test_two_grounded_star_windings_connect_zero_sequence_through_transformer():
    network = Network("YNyn zero sequence")
    transformer = make_two_winding_transformer(
        hv_connection=WindingConnection.STAR,
        lv_connection=WindingConnection.STAR,
        clock=0,
    )
    buses = connect_transformer(network, transformer, (115.0, 13.8))
    model = SequenceNetworkBuilder(SystemBaseSet.from_network(network, 100.0)).build(
        network, SequenceType.ZERO
    )
    assert len(model.branches) == 1
    assert model.branches[0].from_node_id == buses[0].id
    assert model.branches[0].to_node_id == buses[1].id
    assert not model.shunts


def test_two_winding_transformer_with_ungrounded_winding_blocks_zero_sequence_path():
    network = Network("one ungrounded winding")
    transformer = make_two_winding_transformer(
        hv_connection=WindingConnection.STAR,
        lv_connection=WindingConnection.STAR,
        hv_grounding=NeutralGrounding.solid(),
        lv_grounding=NeutralGrounding.ungrounded(),
        clock=0,
    )
    connect_transformer(network, transformer, (115.0, 13.8))
    model = SequenceNetworkBuilder(SystemBaseSet.from_network(network, 100.0)).build(
        network, SequenceType.ZERO
    )
    assert not model.branches
    assert not model.shunts
    assert any(item.code == "SEQ-TRANSFORMER-ZERO-BLOCKED" for item in model.diagnostics)


def test_three_winding_transformer_builds_auxiliary_star_node_for_positive_sequence():
    network = Network("three winding transformer")
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
            WindingConnection.STAR,
            NeutralGrounding.solid(),
            True,
        ),
    )
    terminals = (
        Terminal(equipment_id, "HV", Voltage.from_kv(220.0)),
        Terminal(equipment_id, "MV", Voltage.from_kv(66.0)),
        Terminal(equipment_id, "LV", Voltage.from_kv(13.8)),
    )
    base = ElectricalImpedanceBase(100.0, 220.0)

    def pair(z):
        return SequencePerUnitImpedance(
            base,
            PerUnitImpedance(z.real, z.imag),
            PerUnitImpedance(z.real * 1.1, z.imag * 1.05),
            PerUnitImpedance(z.real * 1.2, z.imag * 1.1),
        )

    transformer = ThreeWindingTransformer(
        id=equipment_id,
        name="TR-3W-ALL-GROUNDED",
        terminals=terminals,
        windings=windings,
        frequency=Frequency(50.0),
        hv_mv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 11),
        hv_lv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 0),
        pairwise_impedances=PairwiseTransformerImpedances(
            pair(0.12 + 0.36j), pair(0.16 + 0.48j), pair(0.10 + 0.30j)
        ),
    )
    buses = connect_transformer(network, transformer, (220.0, 66.0, 13.8))
    builder = SequenceNetworkBuilder(SystemBaseSet.from_network(network, 100.0))
    positive = builder.build(network, SequenceType.POSITIVE)
    assert len(positive.branches) == 3
    assert sum(node.is_internal for node in positive.nodes) == 1
    mv_branch = next(branch for branch in positive.branches if branch.name.endswith(":MV"))
    assert mv_branch.from_node_id == buses[1].id
    assert mv_branch.tap_from == pytest.approx(np.exp(1j * np.deg2rad(330.0)))


def test_three_winding_zero_sequence_requires_explicit_external_equivalent():
    network = Network("three winding zero sequence")
    equipment_id = uuid4()
    windings = tuple(
        TransformerWinding(
            designation, voltage, power, WindingConnection.STAR, NeutralGrounding.solid(), True
        )
        for designation, voltage, power in (
            (WindingDesignation.HIGH_VOLTAGE, 220.0, 100.0),
            (WindingDesignation.MEDIUM_VOLTAGE, 66.0, 60.0),
            (WindingDesignation.LOW_VOLTAGE, 13.8, 40.0),
        )
    )
    terminals = tuple(
        Terminal(equipment_id, designation.value, Voltage.from_kv(voltage))
        for designation, voltage in (
            (WindingDesignation.HIGH_VOLTAGE, 220.0),
            (WindingDesignation.MEDIUM_VOLTAGE, 66.0),
            (WindingDesignation.LOW_VOLTAGE, 13.8),
        )
    )
    base = ElectricalImpedanceBase(100.0, 220.0)

    def pair(z):
        return SequencePerUnitImpedance(
            base,
            PerUnitImpedance(z.real, z.imag),
            PerUnitImpedance(z.real, z.imag),
            PerUnitImpedance(z.real * 1.2, z.imag * 1.1),
        )

    transformer = ThreeWindingTransformer(
        id=equipment_id,
        name="TR3-Z0",
        terminals=terminals,
        windings=windings,
        frequency=Frequency(50.0),
        hv_mv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 0),
        hv_lv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 0),
        pairwise_impedances=PairwiseTransformerImpedances(
            pair(0.1 + 0.3j), pair(0.15 + 0.45j), pair(0.08 + 0.24j)
        ),
    )
    connect_transformer(network, transformer, (220.0, 66.0, 13.8))
    model = SequenceNetworkBuilder(SystemBaseSet.from_network(network, 100.0)).build(
        network, SequenceType.ZERO
    )
    assert not model.branches
    assert not model.is_complete
    assert any(
        item.code == "SEQ-3W-TRANSFORMER-ZERO-REQUIRES-EXPLICIT-MODEL" for item in model.diagnostics
    )


def test_three_winding_mixed_delta_and_ungrounded_configuration_is_not_guessed():
    network = Network("three winding mixed zero")
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
            WindingConnection.DELTA,
            None,
        ),
        TransformerWinding(
            WindingDesignation.LOW_VOLTAGE,
            13.8,
            40.0,
            WindingConnection.STAR,
            NeutralGrounding.ungrounded(),
        ),
    )
    terminals = (
        Terminal(equipment_id, "HV", Voltage.from_kv(220.0)),
        Terminal(equipment_id, "MV", Voltage.from_kv(66.0)),
        Terminal(equipment_id, "LV", Voltage.from_kv(13.8)),
    )
    base = ElectricalImpedanceBase(100.0, 220.0)

    def pair(z):
        value = PerUnitImpedance(z.real, z.imag)
        return SequencePerUnitImpedance(base, value, value, value)

    transformer = ThreeWindingTransformer(
        id=equipment_id,
        name="TR3-MIXED",
        terminals=terminals,
        windings=windings,
        frequency=Frequency(50.0),
        hv_mv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.DELTA, 11),
        hv_lv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 0),
        pairwise_impedances=PairwiseTransformerImpedances(
            pair(0.1 + 0.3j), pair(0.15 + 0.45j), pair(0.08 + 0.24j)
        ),
    )
    connect_transformer(network, transformer, (220.0, 66.0, 13.8))
    model = SequenceNetworkBuilder(SystemBaseSet.from_network(network, 100.0)).build(
        network, SequenceType.ZERO
    )
    assert not model.is_complete
    assert any(
        item.code == "SEQ-3W-TRANSFORMER-ZERO-REQUIRES-EXPLICIT-MODEL" for item in model.diagnostics
    )


def test_builder_marks_empty_network_incomplete():
    network = Network("empty sequence network")
    model = SequenceNetworkBuilder(SystemBaseSet(100.0, {})).build(network, SequenceType.POSITIVE)
    assert not model.is_complete
    assert any(item.code == "SEQ-NETWORK-EMPTY" for item in model.diagnostics)


def test_builder_rejects_mixed_line_and_transformer_reference_frequencies():
    network, buses, _, _ = make_two_bus_line_network()
    equipment_id = uuid4()
    winding_hv = TransformerWinding(
        WindingDesignation.HIGH_VOLTAGE,
        13.8,
        40.0,
        WindingConnection.STAR,
        NeutralGrounding.solid(),
        True,
    )
    winding_lv = TransformerWinding(
        WindingDesignation.LOW_VOLTAGE,
        13.8,
        40.0,
        WindingConnection.STAR,
        NeutralGrounding.solid(),
        True,
    )
    terminals = (
        Terminal(equipment_id, "HV", Voltage.from_kv(13.8)),
        Terminal(equipment_id, "LV", Voltage.from_kv(13.8)),
    )
    base = ElectricalImpedanceBase(40.0, 13.8)
    sequence_impedances = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(0.01, 0.08),
        PerUnitImpedance(0.012, 0.082),
        PerUnitImpedance(0.015, 0.09),
    )
    transformer = TwoWindingTransformer(
        id=equipment_id,
        name="TR-50HZ",
        terminals=terminals,
        windings=(winding_hv, winding_lv),
        frequency=Frequency(50.0),
        vector_group=VectorGroup(
            WindingConnection.STAR,
            WindingConnection.STAR,
            0,
        ),
        sequence_impedances=sequence_impedances,
    )
    network.add_equipment(transformer)
    network.connect(terminals[0].id, buses[0].id)
    network.connect(terminals[1].id, buses[1].id)

    model = SequenceNetworkBuilder(SystemBaseSet.from_network(network, 100.0)).build(
        network, SequenceType.POSITIVE
    )

    assert not model.is_complete
    assert any(item.code == "SEQ-FREQUENCY-MISMATCH" for item in model.diagnostics)


def test_sequence_builder_preserves_physical_line_length_for_interior_faults():
    network, _, line, base = make_two_bus_line_network()
    builder = SequenceNetworkBuilder(base)

    models = builder.build_all(network)

    for sequence in (SequenceType.POSITIVE, SequenceType.NEGATIVE, SequenceType.ZERO):
        branch = next(item for item in models.for_sequence(sequence).branches if item.id == line.id)
        assert branch.length_km == pytest.approx(line.length_km)
