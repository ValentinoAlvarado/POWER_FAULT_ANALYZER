from dataclasses import FrozenInstanceError

import pytest

from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.tap_changer import TapChanger
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PairwiseTransformerImpedances,
    PerUnitImpedance,
    SequencePerUnitImpedance,
    TransformerImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup


def sequence_data(base: TransformerImpedanceBase, scale: float = 1.0):
    return SequencePerUnitImpedance(
        base=base,
        positive=PerUnitImpedance(0.01 * scale, 0.08 * scale),
        negative=PerUnitImpedance(0.012 * scale, 0.082 * scale),
        zero=PerUnitImpedance(0.015 * scale, 0.09 * scale),
    )


def test_impedance_base_uses_three_phase_ll_base():
    base = TransformerImpedanceBase(100.0, 115.0)
    assert base.base_impedance_ohm == pytest.approx(132.25)


def test_per_unit_impedance_converts_to_ohms():
    base = TransformerImpedanceBase(100.0, 115.0)
    impedance = PerUnitImpedance(0.01, 0.08)
    assert impedance.to_ohm(base) == pytest.approx(1.3225 + 10.58j)


def test_per_unit_impedance_changes_base_correctly():
    old = TransformerImpedanceBase(100.0, 115.0)
    new = TransformerImpedanceBase(50.0, 115.0)
    converted = PerUnitImpedance(0.01, 0.08).convert_base(old, new)
    assert converted.value_pu == pytest.approx(0.005 + 0.04j)


def test_sequence_impedance_changes_all_sequences_to_new_base():
    old = TransformerImpedanceBase(100.0, 115.0)
    new = TransformerImpedanceBase(50.0, 115.0)
    converted = sequence_data(old).convert_base(new)
    assert converted.base == new
    assert converted.positive.value_pu == pytest.approx(0.005 + 0.04j)
    assert converted.negative.value_pu == pytest.approx(0.006 + 0.041j)
    assert converted.zero.value_pu == pytest.approx(0.0075 + 0.045j)


def test_sequence_data_preserves_distinct_negative_sequence():
    values = sequence_data(TransformerImpedanceBase(100.0, 115.0))
    assert values.positive != values.negative


def test_neutral_grounding_impedance_is_multiplied_by_three_for_zero_sequence():
    grounding = NeutralGrounding.through_impedance(0.2, 0.3)
    assert grounding.zero_sequence_neutral_impedance_ohm == pytest.approx(0.6 + 0.9j)


def test_solid_grounding_has_zero_neutral_impedance():
    grounding = NeutralGrounding.solid()
    assert grounding.mode is GroundingMode.SOLID
    assert grounding.zero_sequence_neutral_impedance_ohm == 0j


def test_ungrounded_grounding_has_open_neutral_path():
    grounding = NeutralGrounding.ungrounded()
    assert grounding.zero_sequence_neutral_impedance_ohm is None


def test_impedance_grounding_must_not_be_zero():
    with pytest.raises(ValueError, match="non-zero impedance"):
        NeutralGrounding.through_impedance(0.0, 0.0)


def test_solid_grounding_rejects_nonzero_impedance():
    with pytest.raises(ValueError, match="Only impedance grounding"):
        NeutralGrounding(GroundingMode.SOLID, resistance_ohm=0.1)


def test_delta_winding_rejects_neutral_grounding():
    with pytest.raises(ValueError, match="Delta windings"):
        TransformerWinding(
            WindingDesignation.LOW_VOLTAGE,
            13.8,
            40.0,
            WindingConnection.DELTA,
            NeutralGrounding.ungrounded(),
        )


def test_star_winding_requires_explicit_neutral_configuration():
    with pytest.raises(ValueError, match="require an explicit"):
        TransformerWinding(
            WindingDesignation.HIGH_VOLTAGE,
            115.0,
            40.0,
            WindingConnection.STAR,
            None,
        )


def test_winding_ratings_must_be_positive():
    with pytest.raises(ValueError, match="rated_voltage_kv"):
        TransformerWinding(
            WindingDesignation.HIGH_VOLTAGE,
            0.0,
            40.0,
            WindingConnection.STAR,
            NeutralGrounding.ungrounded(),
        )


def test_tap_changer_effective_voltage_factor():
    tap = TapChanger(-8, 8, 0, 2, 1.25)
    assert tap.voltage_factor == pytest.approx(1.025)


def test_tap_changer_position_update_is_immutable():
    tap = TapChanger(-8, 8, 0, 2, 1.25)
    updated = tap.with_position(-1)
    assert tap.current_position == 2
    assert updated.current_position == -1
    with pytest.raises(FrozenInstanceError):
        tap.current_position = 3


def test_tap_changer_rejects_position_outside_limits():
    with pytest.raises(ValueError, match="within tap limits"):
        TapChanger(-8, 8, 0, 9, 1.25)


def test_vector_group_clock_number_and_notation():
    group = VectorGroup(WindingConnection.STAR, WindingConnection.DELTA, 11)
    assert group.notation == "Yd11"
    assert group.phase_displacement_degrees == 330


def test_vector_group_rejects_clock_number_outside_range():
    with pytest.raises(ValueError, match="between 0 and 11"):
        VectorGroup(WindingConnection.STAR, WindingConnection.DELTA, 12)


def test_pairwise_three_winding_impedances_convert_to_star_arms():
    base = TransformerImpedanceBase(100.0, 115.0)
    hm = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(0.12, 0.36),
        PerUnitImpedance(0.12, 0.36),
        PerUnitImpedance(0.15, 0.45),
    )
    hl = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(0.16, 0.48),
        PerUnitImpedance(0.16, 0.48),
        PerUnitImpedance(0.18, 0.54),
    )
    ml = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(0.10, 0.30),
        PerUnitImpedance(0.10, 0.30),
        PerUnitImpedance(0.12, 0.36),
    )
    pairwise = PairwiseTransformerImpedances(hm, hl, ml)
    equivalent = pairwise.to_star_equivalent(SequenceType.POSITIVE)
    assert equivalent.high_voltage.value_pu == pytest.approx(0.09 + 0.27j)
    assert equivalent.medium_voltage.value_pu == pytest.approx(0.03 + 0.09j)
    assert equivalent.low_voltage.value_pu == pytest.approx(0.07 + 0.21j)


def test_pairwise_values_must_use_same_base():
    base_a = TransformerImpedanceBase(100.0, 115.0)
    base_b = TransformerImpedanceBase(100.0, 13.8)
    with pytest.raises(ValueError, match="same reference base"):
        PairwiseTransformerImpedances(
            sequence_data(base_a), sequence_data(base_b), sequence_data(base_a)
        )


def test_pairwise_test_resistance_cannot_be_negative():
    base = TransformerImpedanceBase(100.0, 115.0)
    invalid = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(-0.01, 0.1),
        PerUnitImpedance(0.01, 0.1),
        PerUnitImpedance(0.01, 0.1),
    )
    valid = sequence_data(base)
    with pytest.raises(ValueError, match="resistance cannot be negative"):
        PairwiseTransformerImpedances(invalid, valid, valid)


def test_star_equivalent_can_represent_signed_equivalent_arm():
    base = TransformerImpedanceBase(100.0, 115.0)
    hm = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(0.02, 0.1),
        PerUnitImpedance(0.02, 0.1),
        PerUnitImpedance(0.02, 0.1),
    )
    hl = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(0.02, 0.1),
        PerUnitImpedance(0.02, 0.1),
        PerUnitImpedance(0.02, 0.1),
    )
    ml = SequencePerUnitImpedance(
        base,
        PerUnitImpedance(0.10, 0.3),
        PerUnitImpedance(0.10, 0.3),
        PerUnitImpedance(0.10, 0.3),
    )
    star = PairwiseTransformerImpedances(hm, hl, ml).to_star_equivalent(SequenceType.POSITIVE)
    assert star.high_voltage.resistance_pu < 0.0


def test_grounded_wye_requires_accessible_neutral_terminal():
    with pytest.raises(ValueError, match="must be available"):
        TransformerWinding(
            WindingDesignation.HIGH_VOLTAGE,
            115.0,
            40.0,
            WindingConnection.STAR,
            NeutralGrounding.solid(),
            neutral_terminal_available=False,
        )


def test_ungrounded_wye_can_have_accessible_or_unavailable_neutral():
    accessible = TransformerWinding(
        WindingDesignation.HIGH_VOLTAGE,
        115.0,
        40.0,
        WindingConnection.STAR,
        NeutralGrounding.ungrounded(),
        neutral_terminal_available=True,
    )
    unavailable = TransformerWinding(
        WindingDesignation.HIGH_VOLTAGE,
        115.0,
        40.0,
        WindingConnection.STAR,
        NeutralGrounding.ungrounded(),
        neutral_terminal_available=False,
    )
    assert accessible.neutral_terminal_available is True
    assert unavailable.neutral_terminal_available is False
