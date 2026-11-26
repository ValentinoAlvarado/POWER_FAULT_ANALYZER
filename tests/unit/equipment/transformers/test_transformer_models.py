from uuid import uuid4

import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.interfaces.transformer_model_contracts import (
    ThreeWindingTransformerModelProvider,
    TransformerModelProvider,
    TwoWindingTransformerModelProvider,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PairwiseTransformerImpedances,
    PerUnitImpedance,
    SequencePerUnitImpedance,
    TransformerImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.transformers import (
    ThreeWindingTransformer,
    TwoWindingTransformer,
)


def make_two_winding_transformer(
    *,
    hv_voltage_kv: float = 115.0,
    lv_voltage_kv: float = 13.8,
    vector_clock: int = 11,
    impedance_base_voltage_kv: float | None = None,
) -> TwoWindingTransformer:
    equipment_id = uuid4()
    windings = (
        TransformerWinding(
            WindingDesignation.HIGH_VOLTAGE,
            hv_voltage_kv,
            40.0,
            WindingConnection.STAR,
            NeutralGrounding.solid(),
            neutral_terminal_available=True,
        ),
        TransformerWinding(
            WindingDesignation.LOW_VOLTAGE,
            lv_voltage_kv,
            40.0,
            WindingConnection.DELTA,
            None,
        ),
    )
    terminals = (
        Terminal(equipment_id, "HV", Voltage.from_kv(hv_voltage_kv)),
        Terminal(equipment_id, "LV", Voltage.from_kv(lv_voltage_kv)),
    )
    base = TransformerImpedanceBase(40.0, impedance_base_voltage_kv or hv_voltage_kv)
    sequence_impedances = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(0.01, 0.08),
        PerUnitImpedance(0.012, 0.082),
        PerUnitImpedance(0.015, 0.09),
    )
    return TwoWindingTransformer(
        id=equipment_id,
        name="TR-2W-01",
        terminals=terminals,
        windings=windings,
        frequency=Frequency(60.0),
        vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.DELTA, vector_clock),
        sequence_impedances=sequence_impedances,
    )


def make_three_winding_transformer() -> ThreeWindingTransformer:
    equipment_id = uuid4()
    windings = (
        TransformerWinding(
            WindingDesignation.HIGH_VOLTAGE,
            220.0,
            100.0,
            WindingConnection.STAR,
            NeutralGrounding.solid(),
            neutral_terminal_available=True,
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
    base = TransformerImpedanceBase(100.0, 220.0)

    def seq(hm: complex, hl: complex, ml: complex) -> PairwiseTransformerImpedances:
        def value(z: complex, multiplier: float) -> SequencePerUnitImpedance:
            positive = PerUnitImpedance(z.real, z.imag)
            negative = PerUnitImpedance(z.real * 1.05, z.imag * 1.02)
            zero = PerUnitImpedance(z.real * multiplier, z.imag * multiplier)
            return SequencePerUnitImpedance(base, positive, negative, zero)

        return PairwiseTransformerImpedances(value(hm, 1.7), value(hl, 1.5), value(ml, 1.9))

    return ThreeWindingTransformer(
        id=equipment_id,
        name="TR-3W-01",
        terminals=terminals,
        windings=windings,
        frequency=Frequency(50.0),
        hv_mv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.DELTA, 11),
        hv_lv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 0),
        pairwise_impedances=seq(0.12 + 0.36j, 0.16 + 0.48j, 0.10 + 0.30j),
    )


def test_two_winding_transformer_has_two_windings_and_correct_group():
    transformer = make_two_winding_transformer()
    assert transformer.winding_count == 2
    assert transformer.vector_group.notation == "Yd11"
    assert transformer.vector_group_notation == "YNd11"
    assert transformer.frequency.value_hz == pytest.approx(60.0)
    assert transformer.get_winding(WindingDesignation.HIGH_VOLTAGE).rated_voltage_kv == 115.0


def test_two_winding_transformer_preserves_distinct_sequence_impedances():
    transformer = make_two_winding_transformer()
    assert transformer.sequence_impedances.positive != transformer.sequence_impedances.negative
    assert transformer.sequence_impedances.zero != transformer.sequence_impedances.positive


def test_two_winding_transformer_rejects_wrong_vector_group_connection():
    transformer = make_two_winding_transformer()
    with pytest.raises(ValueError, match="secondary connection"):
        TwoWindingTransformer(
            id=transformer.id,
            name=transformer.name,
            terminals=transformer.terminals,
            windings=transformer.windings,
            frequency=transformer.frequency,
            vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 11),
            sequence_impedances=transformer.sequence_impedances,
        )


def test_two_winding_transformer_rejects_wrong_impedance_base_voltage():
    with pytest.raises(ValueError, match="base voltage must match"):
        make_two_winding_transformer(impedance_base_voltage_kv=13.8)


def test_two_winding_transformer_rejects_wrong_winding_order():
    transformer = make_two_winding_transformer()
    with pytest.raises(ValueError, match=r"order must be \(HV, LV\)"):
        TwoWindingTransformer(
            id=transformer.id,
            name=transformer.name,
            terminals=transformer.terminals,
            windings=tuple(reversed(transformer.windings)),
            frequency=transformer.frequency,
            vector_group=transformer.vector_group,
            sequence_impedances=transformer.sequence_impedances,
        )


def test_two_winding_transformer_is_accepted_by_network_aggregate():
    transformer = make_two_winding_transformer()
    network = Network("Transformer network")
    hv_bus = Bus("BUS-HV", Voltage.from_kv(115.0))
    lv_bus = Bus("BUS-LV", Voltage.from_kv(13.8))
    network.add_bus(hv_bus)
    network.add_bus(lv_bus)
    network.add_equipment(transformer)
    network.connect(transformer.terminals[0].id, hv_bus.id)
    network.connect(transformer.terminals[1].id, lv_bus.id)
    assert len(network.equipment) == 1
    assert len(network.connections) == 2


def test_three_winding_transformer_has_three_windings_and_pairwise_data():
    transformer = make_three_winding_transformer()
    assert transformer.winding_count == 3
    assert tuple(w.designation for w in transformer.windings) == (
        WindingDesignation.HIGH_VOLTAGE,
        WindingDesignation.MEDIUM_VOLTAGE,
        WindingDesignation.LOW_VOLTAGE,
    )
    assert transformer.hv_mv_vector_group.notation == "Yd11"
    assert transformer.hv_lv_vector_group.notation == "Yy0"
    assert transformer.hv_mv_vector_group_notation == "YNd11"
    assert transformer.hv_lv_vector_group_notation == "YNy0"


def test_three_winding_transformer_builds_positive_sequence_star_equivalent():
    transformer = make_three_winding_transformer()
    equivalent = transformer.build_star_equivalent(SequenceType.POSITIVE)
    assert equivalent.high_voltage.value_pu == pytest.approx(0.09 + 0.27j)
    assert equivalent.medium_voltage.value_pu == pytest.approx(0.03 + 0.09j)
    assert equivalent.low_voltage.value_pu == pytest.approx(0.07 + 0.21j)


def test_three_winding_transformer_rejects_wrong_terminal_count():
    transformer = make_three_winding_transformer()
    with pytest.raises(ValueError, match="exactly three terminals"):
        ThreeWindingTransformer(
            id=transformer.id,
            name=transformer.name,
            terminals=transformer.terminals[:2],
            windings=transformer.windings,
            frequency=transformer.frequency,
            hv_mv_vector_group=transformer.hv_mv_vector_group,
            hv_lv_vector_group=transformer.hv_lv_vector_group,
            pairwise_impedances=transformer.pairwise_impedances,
        )


def test_three_winding_transformer_rejects_inconsistent_hv_mv_group():
    transformer = make_three_winding_transformer()
    with pytest.raises(ValueError, match="secondary must match MV"):
        ThreeWindingTransformer(
            id=transformer.id,
            name=transformer.name,
            terminals=transformer.terminals,
            windings=transformer.windings,
            frequency=transformer.frequency,
            hv_mv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 11),
            hv_lv_vector_group=transformer.hv_lv_vector_group,
            pairwise_impedances=transformer.pairwise_impedances,
        )


def test_three_winding_transformer_is_accepted_by_network_aggregate():
    transformer = make_three_winding_transformer()
    network = Network("Three-winding network")
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
    assert len(network.connections) == 3


def test_three_winding_transformer_zero_sequence_star_equivalent_is_independent():
    transformer = make_three_winding_transformer()
    positive = transformer.build_star_equivalent(SequenceType.POSITIVE)
    zero = transformer.build_star_equivalent(SequenceType.ZERO)
    assert positive.high_voltage != zero.high_voltage


def test_transformer_family_is_classified_correctly():
    transformer = make_two_winding_transformer()
    assert transformer.family.value == "transformer"


def test_delta_winding_can_have_no_neutral_grounding():
    transformer = make_two_winding_transformer()
    lv = transformer.get_winding(WindingDesignation.LOW_VOLTAGE)
    assert lv.connection is WindingConnection.DELTA
    assert lv.neutral_grounding is None


def test_grounded_wye_winding_preserves_neutral_mode():
    transformer = make_two_winding_transformer()
    hv = transformer.get_winding(WindingDesignation.HIGH_VOLTAGE)
    assert hv.neutral_grounding is not None
    assert hv.neutral_grounding.mode is GroundingMode.SOLID


def test_two_winding_transformer_satisfies_structural_model_contracts():
    transformer = make_two_winding_transformer()
    assert isinstance(transformer, TransformerModelProvider)
    assert isinstance(transformer, TwoWindingTransformerModelProvider)
    assert transformer.get_sequence_impedance_pu(SequenceType.POSITIVE) == (
        transformer.sequence_impedances.positive
    )


def test_three_winding_transformer_satisfies_structural_model_contracts():
    transformer = make_three_winding_transformer()
    assert isinstance(transformer, TransformerModelProvider)
    assert isinstance(transformer, ThreeWindingTransformerModelProvider)


def test_transformer_terminals_must_match_winding_rated_voltages():
    transformer = make_two_winding_transformer()
    bad_terminals = (
        Terminal(transformer.id, "HV", Voltage.from_kv(110.0)),
        transformer.terminals[1],
    )
    with pytest.raises(ValueError, match="does not match"):
        TwoWindingTransformer(
            id=transformer.id,
            name=transformer.name,
            terminals=bad_terminals,
            windings=transformer.windings,
            frequency=transformer.frequency,
            vector_group=transformer.vector_group,
            sequence_impedances=transformer.sequence_impedances,
        )
