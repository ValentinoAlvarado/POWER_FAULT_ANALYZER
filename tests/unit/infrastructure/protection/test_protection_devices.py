"""Unit tests for CT, overcurrent relay, fuse and breaker models."""

from math import sqrt
from uuid import uuid4

import pytest

from power_fault_analyzer.domain.enums.protection import (
    CircuitBreakerStandard,
    IECInverseCurveType,
    ProtectionFunction,
    ProtectionStage,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    ConductorThermalLimit,
    CurrentTransformerRatio,
    FuseLink,
    FuseTimeCurrentPoint,
    OvercurrentRelay,
)


def make_relay(
    *,
    name="R-1",
    ct_primary=100.0,
    ct_secondary=5.0,
    pickup_secondary=1.0,
    curve=IECInverseCurveType.STANDARD_INVERSE,
    tms=1.0,
    instantaneous=None,
    instantaneous_delay=0.0,
):
    return OvercurrentRelay(
        id=uuid4(),
        name=name,
        current_transformer=CurrentTransformerRatio(ct_primary, ct_secondary),
        function=ProtectionFunction.PHASE,
        pickup_secondary_a=pickup_secondary,
        curve_type=curve,
        time_multiplier=tms,
        instantaneous_pickup_secondary_a=instantaneous,
        instantaneous_delay_s=instantaneous_delay,
    )


def test_current_transformer_ratio_converts_primary_and_secondary_currents():
    ct = CurrentTransformerRatio(600.0, 5.0)
    assert ct.ratio == pytest.approx(120.0)
    assert ct.to_secondary(1200.0) == pytest.approx(10.0)
    assert ct.to_primary(2.5) == pytest.approx(300.0)


def test_relay_standard_inverse_matches_iec_60255_curve_equation():
    relay = make_relay(ct_primary=100.0, ct_secondary=1.0, pickup_secondary=1.0, tms=0.2)
    point = relay.operate(200.0)
    expected = 0.2 * 0.14 / (2.0**0.02 - 1.0)
    assert point.picked_up
    assert point.stage is ProtectionStage.TIME_INVERSE_51
    assert point.operating_time_s == pytest.approx(expected)


@pytest.mark.parametrize(
    ("curve", "numerator", "exponent"),
    [
        (IECInverseCurveType.STANDARD_INVERSE, 0.14, 0.02),
        (IECInverseCurveType.VERY_INVERSE, 13.5, 1.0),
        (IECInverseCurveType.EXTREMELY_INVERSE, 80.0, 2.0),
        (IECInverseCurveType.LONG_TIME_INVERSE, 120.0, 1.0),
    ],
)
def test_relay_supports_all_four_iec_inverse_curve_families(curve, numerator, exponent):
    relay = make_relay(
        ct_primary=100.0,
        ct_secondary=1.0,
        pickup_secondary=1.0,
        curve=curve,
        tms=0.5,
    )
    expected = 0.5 * numerator / (3.0**exponent - 1.0)
    assert relay.operate(300.0).operating_time_s == pytest.approx(expected)


def test_relay_does_not_pick_up_at_or_below_pickup():
    relay = make_relay(ct_primary=100.0, ct_secondary=1.0, pickup_secondary=1.0)
    assert relay.operate(100.0).picked_up is False
    assert relay.operate(99.0).operating_time_s is None


def test_relay_instantaneous_stage_overrides_inverse_stage():
    relay = make_relay(
        ct_primary=100.0,
        ct_secondary=1.0,
        pickup_secondary=1.0,
        instantaneous=8.0,
        instantaneous_delay=0.015,
    )
    point = relay.operate(1000.0)
    assert point.stage is ProtectionStage.INSTANTANEOUS_50
    assert point.operating_time_s == pytest.approx(0.015)


def test_zero_delay_instantaneous_relay_is_represented_as_zero_seconds():
    relay = make_relay(
        ct_primary=100.0,
        ct_secondary=1.0,
        instantaneous=8.0,
    )
    point = relay.operate(1000.0)
    assert point.operating_time_s == 0.0


def test_relay_requires_instantaneous_pickup_above_51_pickup():
    with pytest.raises(ValueError, match="must exceed"):
        make_relay(instantaneous=1.0)


def make_fuse():
    return FuseLink(
        id=uuid4(),
        name="F-100A",
        rated_current_a=100.0,
        rated_voltage_kv=0.4,
        breaking_capacity_ka=50.0,
        characteristic_points=(
            FuseTimeCurrentPoint(100.0, 10.0, 12.0),
            FuseTimeCurrentPoint(1000.0, 1.0, 1.2),
            FuseTimeCurrentPoint(10000.0, 0.1, 0.12),
        ),
    )


def test_fuse_characteristic_uses_log_log_interpolation():
    fuse = make_fuse()
    midpoint = sqrt(100.0 * 1000.0)
    assert fuse.pre_arcing_time(midpoint) == pytest.approx(sqrt(10.0))
    assert fuse.total_clearing_time(midpoint) == pytest.approx(sqrt(12.0 * 1.2))


def test_fuse_does_not_extrapolate_beyond_manufacturer_curve_range():
    fuse = make_fuse()
    assert fuse.total_clearing_time(50.0) is None
    assert fuse.total_clearing_time(20000.0) is None


def test_fuse_requires_monotonic_current_time_data():
    with pytest.raises(ValueError, match="must not increase"):
        FuseLink(
            id=uuid4(),
            name="BAD-FUSE",
            rated_current_a=100.0,
            rated_voltage_kv=0.4,
            breaking_capacity_ka=50.0,
            characteristic_points=(
                FuseTimeCurrentPoint(100.0, 1.0, 1.2),
                FuseTimeCurrentPoint(1000.0, 2.0, 2.2),
            ),
        )


def test_circuit_breaker_exposes_total_clearing_time():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-1",
        rated_voltage_kv=13.8,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        opening_time_s=0.04,
        arcing_time_s=0.02,
    )
    assert breaker.total_clearing_time_s == pytest.approx(0.06)


def test_circuit_breaker_rejects_ics_above_icu():
    with pytest.raises(ValueError, match="Ics cannot exceed Icu"):
        CircuitBreaker(
            id=uuid4(),
            name="BAD-CB",
            rated_voltage_kv=0.4,
            rated_current_a=630.0,
            standard=CircuitBreakerStandard.IEC_60947_2,
            ultimate_breaking_capacity_ka=20.0,
            service_breaking_capacity_ka=25.0,
        )


def test_circuit_breaker_requires_paired_icw_and_duration():
    with pytest.raises(ValueError, match="provided together"):
        CircuitBreaker(
            id=uuid4(),
            name="BAD-CB",
            rated_voltage_kv=0.4,
            rated_current_a=630.0,
            standard=CircuitBreakerStandard.IEC_60947_2,
            ultimate_breaking_capacity_ka=20.0,
            short_time_withstand_current_ka=20.0,
        )


def test_conductor_thermal_limit_calculates_adiabatic_withstand():
    conductor = ConductorThermalLimit(95.0, 143.0)
    assert conductor.withstand_i2t_a2s == pytest.approx((95.0 * 143.0) ** 2)
