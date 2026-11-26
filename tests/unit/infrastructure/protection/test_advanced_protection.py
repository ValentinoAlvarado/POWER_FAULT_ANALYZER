import math
from uuid import uuid4

import pytest

from power_fault_analyzer.domain.enums.advanced_protection import (
    DifferentialProtectionKind,
    DirectionalSense,
    DistanceCharacteristic,
    DistanceLoop,
)
from power_fault_analyzer.domain.enums.protection import (
    IECInverseCurveType,
    ProtectionAssessmentStatus,
    ProtectionFunction,
)
from power_fault_analyzer.domain.value_objects.advanced_protection import (
    CTExcitationPoint,
    CurrentTransformerPerformanceModel,
    DifferentialMeasurement,
    DifferentialProtectionSettings,
    DifferentialSideSettings,
    DirectionalMeasurement,
    DirectionalOvercurrentSettings,
    DistanceMeasurement,
    DistanceProtectionSettings,
    DistanceZoneSettings,
    VoltageTransformerRatio,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CurrentTransformerRatio,
    OvercurrentRelay,
)
from power_fault_analyzer.infrastructure.protection.advanced import (
    CurrentTransformerSaturationEvaluator,
    DifferentialProtectionEvaluator,
    DirectionalOvercurrentEvaluator,
    DistanceProtectionEvaluator,
)


def make_differential(*, harmonic_block=0.15, high_set=None):
    ratio = CurrentTransformerRatio(600.0, 5.0)
    sides = (
        DifferentialSideSettings("FROM", 1000.0, ratio),
        DifferentialSideSettings("TO", 1000.0, ratio),
    )
    return DifferentialProtectionSettings(
        name="87L-LINE-01",
        kind=DifferentialProtectionKind.LINE,
        sides=sides,
        minimum_pickup_pu=0.2,
        low_slope=0.3,
        breakpoint_restraint_pu=2.0,
        high_slope=0.5,
        unrestrained_pickup_pu=high_set,
        second_harmonic_block_ratio=harmonic_block,
    )


def test_differential_relay_restrains_balanced_through_current():
    settings = make_differential()
    measurement = DifferentialMeasurement(
        side_currents_primary_a={
            "FROM": (1000 + 0j, -500 - 500 * math.sqrt(3) * 1j, -500 + 500 * math.sqrt(3) * 1j),
            "TO": (-1000 + 0j, 500 + 500 * math.sqrt(3) * 1j, 500 - 500 * math.sqrt(3) * 1j),
        }
    )
    result = DifferentialProtectionEvaluator().evaluate(settings, measurement)
    assert not result.operated
    assert all(item.differential_current_pu == pytest.approx(0.0) for item in result.phases)
    assert all(item.restraint_current_pu == pytest.approx(1.0) for item in result.phases)


def test_differential_relay_operates_for_internal_fault_current():
    settings = make_differential()
    measurement = DifferentialMeasurement(
        side_currents_primary_a={"FROM": (1000 + 0j, 0j, 0j), "TO": (0j, 0j, 0j)}
    )
    result = DifferentialProtectionEvaluator().evaluate(settings, measurement)
    assert result.operated
    assert result.phases[0].differential_current_pu == pytest.approx(1.0)
    assert result.phases[0].operated


def test_differential_second_harmonic_restraint_blocks_phase():
    settings = make_differential()
    measurement = DifferentialMeasurement(
        side_currents_primary_a={"FROM": (1000 + 0j, 0j, 0j), "TO": (0j, 0j, 0j)},
        second_harmonic_ratio_by_phase=(0.2, 0.0, 0.0),
    )
    result = DifferentialProtectionEvaluator().evaluate(settings, measurement)
    assert not result.phases[0].operated
    assert result.phases[0].blocked_by_harmonic


def test_differential_unrestrained_high_set_overrides_harmonic_block():
    settings = make_differential(high_set=0.8)
    measurement = DifferentialMeasurement(
        side_currents_primary_a={"FROM": (1000 + 0j, 0j, 0j), "TO": (0j, 0j, 0j)},
        second_harmonic_ratio_by_phase=(0.3, 0.0, 0.0),
    )
    result = DifferentialProtectionEvaluator().evaluate(settings, measurement)
    assert result.operated
    assert result.phases[0].operated
    assert not result.phases[0].blocked_by_harmonic


def test_differential_rejects_missing_or_unknown_sides():
    settings = make_differential()
    measurement = DifferentialMeasurement(
        side_currents_primary_a={"FROM": (1j, 0j, 0j), "OTHER": (0j, 0j, 0j)}
    )
    with pytest.raises(ValueError, match="exactly match"):
        DifferentialProtectionEvaluator().evaluate(settings, measurement)


def make_directional_settings(sense=DirectionalSense.FORWARD):
    relay = OvercurrentRelay(
        id=uuid4(),
        name="67-PHASE",
        current_transformer=CurrentTransformerRatio(600.0, 5.0),
        function=ProtectionFunction.PHASE,
        pickup_secondary_a=1.0,
        curve_type=IECInverseCurveType.STANDARD_INVERSE,
        time_multiplier=0.1,
    )
    return DirectionalOvercurrentSettings(
        relay=relay,
        maximum_torque_angle_deg=0.0,
        minimum_polarizing_voltage_v=10.0,
        sense=sense,
    )


def test_directional_overcurrent_allows_forward_fault():
    settings = make_directional_settings()
    measurement = DirectionalMeasurement(1000 + 0j, 100 + 0j)
    result = DirectionalOvercurrentEvaluator().evaluate(settings, measurement)
    assert result.overcurrent_picked_up
    assert result.directional_decision is DirectionalSense.FORWARD
    assert result.operated
    assert result.operating_time_s is not None


def test_directional_overcurrent_restrains_reverse_fault():
    settings = make_directional_settings()
    measurement = DirectionalMeasurement(-1000 + 0j, 100 + 0j)
    result = DirectionalOvercurrentEvaluator().evaluate(settings, measurement)
    assert result.overcurrent_picked_up
    assert result.directional_decision is DirectionalSense.REVERSE
    assert not result.operated
    assert result.operating_time_s is None


def test_directional_overcurrent_does_not_guess_when_polarizing_voltage_is_low():
    settings = make_directional_settings()
    result = DirectionalOvercurrentEvaluator().evaluate(
        settings, DirectionalMeasurement(1000 + 0j, 1 + 0j)
    )
    assert result.overcurrent_picked_up
    assert result.directional_decision is None
    assert not result.operated
    assert "below" in result.reason


def test_directional_overcurrent_does_not_operate_without_current_pickup():
    settings = make_directional_settings()
    result = DirectionalOvercurrentEvaluator().evaluate(
        settings, DirectionalMeasurement(10 + 0j, 100 + 0j)
    )
    assert not result.overcurrent_picked_up
    assert result.directional_decision is None
    assert not result.operated


def make_distance_settings(characteristic=DistanceCharacteristic.MHO):
    ratio = CurrentTransformerRatio(600.0, 5.0)
    vt = VoltageTransformerRatio(13_800.0 / math.sqrt(3.0), 110.0 / math.sqrt(3.0))
    if characteristic is DistanceCharacteristic.MHO:
        zones = (
            DistanceZoneSettings(1, characteristic, 0.1, reach_impedance_secondary_ohm=12 + 24j),
            DistanceZoneSettings(2, characteristic, 0.4, reach_impedance_secondary_ohm=24 + 48j),
        )
    else:
        zones = (
            DistanceZoneSettings(
                1,
                characteristic,
                0.1,
                resistance_min_ohm=-1.0,
                resistance_max_ohm=8.0,
                reactance_min_ohm=1.0,
                reactance_max_ohm=20.0,
            ),
        )
    return DistanceProtectionSettings(
        name="21-LINE-01",
        current_transformer=ratio,
        voltage_transformer=vt,
        zones=zones,
        ground_compensation_factor=0j,
    ), vt


def make_distance_measurement(vt, impedance_secondary=5 + 10j):
    current_primary = 1200 + 0j
    voltage_secondary = impedance_secondary * (current_primary / 120.0)
    voltage_primary = voltage_secondary * vt.ratio
    return DistanceMeasurement(
        phase_voltages_primary_v=(voltage_primary, 0j, 0j),
        phase_currents_primary_a=(current_primary, 0j, 0j),
    )


def test_distance_mho_zone_identifies_nearest_operating_zone():
    settings, vt = make_distance_settings()
    result = DistanceProtectionEvaluator().evaluate(settings, make_distance_measurement(vt))
    assert result.operated
    assert result.fastest_zone_number == 1
    assert result.operating_time_s == pytest.approx(0.1)
    ag = next(item for item in result.loops if item.loop is DistanceLoop.AG)
    assert ag.apparent_impedance_secondary_ohm == pytest.approx(5 + 10j)
    assert ag.reached_zone_number == 1


def test_distance_relay_restrains_impedance_outside_all_zones():
    settings, vt = make_distance_settings()
    result = DistanceProtectionEvaluator().evaluate(
        settings, make_distance_measurement(vt, 40 + 80j)
    )
    assert not result.operated
    assert result.fastest_zone_number is None


def test_distance_quadrilateral_characteristic_checks_r_and_x_bounds():
    settings, vt = make_distance_settings(DistanceCharacteristic.QUADRILATERAL)
    result = DistanceProtectionEvaluator().evaluate(settings, make_distance_measurement(vt))
    assert result.operated
    assert result.fastest_zone_number == 1


def test_distance_loop_is_not_evaluated_when_current_is_too_small():
    settings, _vt = make_distance_settings()
    measurement = DistanceMeasurement((100 + 0j, 0j, 0j), (0j, 0j, 0j))
    result = DistanceProtectionEvaluator().evaluate(settings, measurement)
    assert not result.operated
    assert all(not item.evaluated for item in result.loops)


def make_ct_model():
    return CurrentTransformerPerformanceModel(
        name="CT-PX-600-5",
        current_transformer=CurrentTransformerRatio(600.0, 5.0),
        secondary_winding_resistance_ohm=0.2,
        burden_impedance_ohm=0.5 + 0.1j,
        knee_point_voltage_v=100.0,
        excitation_curve=(
            CTExcitationPoint(1.0, 0.01),
            CTExcitationPoint(10.0, 0.05),
            CTExcitationPoint(100.0, 1.0),
            CTExcitationPoint(110.0, 2.0),
        ),
        rated_frequency_hz=60.0,
    )


def test_ct_steady_state_screen_passes_with_voltage_below_knee_point():
    result = CurrentTransformerSaturationEvaluator().evaluate(
        make_ct_model(), 1000.0, system_frequency_hz=60.0
    )
    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.required_secondary_voltage_v < result.knee_point_voltage_v
    assert result.exciting_current_a is not None
    assert result.transient_status is ProtectionAssessmentStatus.NOT_EVALUATED


def test_ct_steady_state_screen_fails_above_knee_point():
    result = CurrentTransformerSaturationEvaluator().evaluate(
        make_ct_model(), 20_000.0, system_frequency_hz=60.0
    )
    assert result.status is ProtectionAssessmentStatus.FAIL
    assert result.voltage_margin_v < 0.0


def test_ct_screen_does_not_run_at_wrong_system_frequency():
    result = CurrentTransformerSaturationEvaluator().evaluate(
        make_ct_model(), 1000.0, system_frequency_hz=50.0
    )
    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED
    assert result.exciting_current_a is None
    assert any("frequency" in item for item in result.diagnostics)


def test_ct_screen_does_not_extrapolate_excitation_curve():
    model = make_ct_model()
    result = CurrentTransformerSaturationEvaluator().evaluate(
        model, 20_000.0, system_frequency_hz=60.0
    )
    assert result.exciting_current_a is None
    assert any("not extrapolated" in item for item in result.diagnostics)


def test_ct_model_requires_monotonic_excitation_curve():
    with pytest.raises(ValueError, match="strictly increasing"):
        CurrentTransformerPerformanceModel(
            name="CT-BAD",
            current_transformer=CurrentTransformerRatio(600.0),
            secondary_winding_resistance_ohm=0.2,
            burden_impedance_ohm=0.5 + 0j,
            knee_point_voltage_v=100.0,
            excitation_curve=(CTExcitationPoint(10, 0.1), CTExcitationPoint(5, 0.2)),
            rated_frequency_hz=60.0,
        )
