"""Unit tests for breaker duty, conductor withstand and relay coordination."""

from uuid import uuid4

import pytest

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.protection import (
    CircuitBreakerStandard,
    IECInverseCurveType,
    ProtectionAssessmentStatus,
    ProtectionFunction,
)
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.iec60909_study import (
    IEC60909StudyResult,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    ConductorThermalLimit,
    CurrentTransformerRatio,
    FuseLink,
    FuseTimeCurrentPoint,
    OvercurrentRelay,
)
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.infrastructure.protection import (
    ProtectionCoordinationAnalyzer,
    ProtectionCoordinationError,
    ProtectionDutyEvaluator,
)


def make_iec_result(
    *,
    initial=10.0,
    peak=25.0,
    breaking=9.0,
    thermal=8.0,
    joule=64.0,
    duration=1.0,
):
    bus_id = uuid4()
    base_result = ShortCircuitResult(
        fault_type=FaultType.THREE_PHASE,
        bus_id=bus_id,
        fault_impedance_pu=0.0j,
        base_power_mva=100.0,
        base_voltage_kv=13.8,
        base_current_ka=4.184,
        prefault_sequence_voltages_pu={SequenceType.POSITIVE: 1.0 + 0.0j},
        driving_point_impedances_pu={SequenceType.POSITIVE: 0.01 + 0.1j},
        sequence_currents_pu={SequenceType.POSITIVE: 2.0 - 20.0j},
        sequence_fault_voltages_pu={SequenceType.POSITIVE: 0.0j},
        phase_currents_pu=(2.0 - 20.0j, 0.0j, 0.0j),
        phase_voltages_pu=(0.0j, 0.0j, 0.0j),
        phase_currents_ka=(initial + 0.0j, 0.0j, 0.0j),
        phase_voltages_kv=(0.0j, 0.0j, 0.0j),
    )
    return IEC60909StudyResult(
        standard_edition="IEC 60909-0:2026",
        base_result=base_result,
        current_case=IEC60909CurrentCase.MAXIMUM,
        voltage_factor=1.1,
        equivalent_voltage_pu=1.1 + 0.0j,
        initial_symmetrical_current_ka=initial,
        peak_current_factor=peak / (initial * 2**0.5),
        peak_current_ka=peak,
        breaking_current_ka=breaking,
        steady_state_current_ka=breaking,
        thermal_factor_dc=1.0,
        thermal_factor_ac=1.0,
        thermal_equivalent_current_ka=thermal,
        joule_integral_ka2s=joule,
        fault_duration_s=duration,
        frequency_hz=50.0,
        applied_transformer_correction_factors={},
    )


def make_relay(
    name,
    *,
    ct_primary=1000.0,
    ct_secondary=5.0,
    pickup=1.0,
    tms=1.0,
    instantaneous=None,
):
    return OvercurrentRelay(
        id=uuid4(),
        name=name,
        current_transformer=CurrentTransformerRatio(ct_primary, ct_secondary),
        function=ProtectionFunction.PHASE,
        pickup_secondary_a=pickup,
        curve_type=IECInverseCurveType.STANDARD_INVERSE,
        time_multiplier=tms,
        instantaneous_pickup_secondary_a=instantaneous,
    )


def make_fuse():
    return FuseLink(
        id=uuid4(),
        name="F-DOWNSTREAM",
        rated_current_a=100.0,
        rated_voltage_kv=0.4,
        breaking_capacity_ka=50.0,
        characteristic_points=(
            FuseTimeCurrentPoint(100.0, 10.0, 12.0),
            FuseTimeCurrentPoint(1000.0, 1.0, 1.2),
            FuseTimeCurrentPoint(10000.0, 0.1, 0.12),
        ),
    )


def test_breaker_duty_passes_when_all_declared_ratings_exceed_duty():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-PASS",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        making_capacity_peak_ka=60.0,
        short_time_withstand_current_ka=15.0,
        short_time_withstand_duration_s=2.0,
    )
    result = ProtectionDutyEvaluator().evaluate_breaker(
        breaker, make_iec_result(), operating_voltage_kv=13.8
    )
    assert result.status is ProtectionAssessmentStatus.PASS
    assert set(result.checks) == {"voltage", "rated_breaking_current", "icm", "icw"}
    assert all(value is ProtectionAssessmentStatus.PASS for value in result.checks.values())


def test_mv_breaker_duty_fails_when_rated_breaking_current_or_icm_is_insufficient():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-FAIL",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=8.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        making_capacity_peak_ka=20.0,
    )
    result = ProtectionDutyEvaluator().evaluate_breaker(
        breaker, make_iec_result(), operating_voltage_kv=13.8
    )
    assert result.status is ProtectionAssessmentStatus.FAIL
    assert result.checks["rated_breaking_current"] is ProtectionAssessmentStatus.FAIL
    assert result.checks["icm"] is ProtectionAssessmentStatus.FAIL


def test_breaker_duty_fails_when_operating_voltage_exceeds_rating():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-UNDERRATED-VOLTAGE",
        rated_voltage_kv=12.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
    )
    result = ProtectionDutyEvaluator().evaluate_breaker(
        breaker, make_iec_result(), operating_voltage_kv=13.8
    )
    assert result.checks["voltage"] is ProtectionAssessmentStatus.FAIL
    assert result.status is ProtectionAssessmentStatus.FAIL


def test_breaker_duty_reports_unavailable_peak_as_not_evaluated():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-NO-PEAK",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        making_capacity_peak_ka=60.0,
    )
    study = make_iec_result()
    study = IEC60909StudyResult(
        standard_edition=study.standard_edition,
        base_result=study.base_result,
        current_case=study.current_case,
        voltage_factor=study.voltage_factor,
        equivalent_voltage_pu=study.equivalent_voltage_pu,
        initial_symmetrical_current_ka=study.initial_symmetrical_current_ka,
        peak_current_factor=None,
        peak_current_ka=None,
        breaking_current_ka=study.breaking_current_ka,
        steady_state_current_ka=study.steady_state_current_ka,
        thermal_factor_dc=None,
        thermal_factor_ac=None,
        thermal_equivalent_current_ka=None,
        joule_integral_ka2s=None,
        fault_duration_s=study.fault_duration_s,
        frequency_hz=study.frequency_hz,
        applied_transformer_correction_factors={},
    )
    result = ProtectionDutyEvaluator().evaluate_breaker(breaker, study, operating_voltage_kv=13.8)
    assert result.checks["rated_breaking_current"] is ProtectionAssessmentStatus.PASS
    assert result.checks["icm"] is ProtectionAssessmentStatus.NOT_EVALUATED
    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED


def test_conductor_thermal_check_uses_k_squared_s_squared():
    result = ProtectionDutyEvaluator().evaluate_conductor(
        ConductorThermalLimit(120.0, 143.0), make_iec_result(joule=100.0)
    )
    assert result.withstand_i2t_a2s == pytest.approx((120.0 * 143.0) ** 2)
    assert result.actual_i2t_a2s == pytest.approx(100.0e6)
    assert result.status is ProtectionAssessmentStatus.PASS


def test_conductor_thermal_check_detects_excessive_joule_integral():
    result = ProtectionDutyEvaluator().evaluate_conductor(
        ConductorThermalLimit(25.0, 115.0), make_iec_result(joule=100.0)
    )
    assert result.status is ProtectionAssessmentStatus.FAIL
    assert result.utilization > 1.0


def test_conductor_thermal_check_rejects_duration_above_five_seconds():
    with pytest.raises(ValueError, match="up to 5 s"):
        ProtectionDutyEvaluator().evaluate_conductor(
            ConductorThermalLimit(120.0, 143.0), make_iec_result(duration=6.0)
        )


def test_relay_sensitivity_uses_primary_pickup_after_ct_conversion():
    relay = make_relay("R-SENSITIVE", ct_primary=600.0, ct_secondary=5.0, pickup=1.0)
    result = ProtectionDutyEvaluator().evaluate_relay_sensitivity(
        relay,
        minimum_fault_current_a=300.0,
        required_sensitivity_ratio=2.0,
    )
    assert result.relay_pickup_current_primary_a == pytest.approx(120.0)
    assert result.sensitivity_ratio == pytest.approx(2.5)
    assert result.status is ProtectionAssessmentStatus.PASS


def test_relay_sensitivity_fails_below_declared_minimum_ratio():
    relay = make_relay("R-INSENSITIVE")
    result = ProtectionDutyEvaluator().evaluate_relay_sensitivity(
        relay,
        minimum_fault_current_a=200.0,
        required_sensitivity_ratio=2.0,
    )
    assert result.status is ProtectionAssessmentStatus.FAIL


def test_relay_pair_coordination_includes_downstream_breaker_clearing_time():
    downstream = make_relay("R-DOWN", ct_primary=1000.0, pickup=1.0, tms=0.1)
    upstream = make_relay("R-UP", ct_primary=1000.0, pickup=0.5, tms=1.0)
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-DOWN",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        opening_time_s=0.04,
        arcing_time_s=0.02,
    )
    result = ProtectionCoordinationAnalyzer().coordinate_relay_pair(
        downstream,
        upstream,
        minimum_current_a=1500.0,
        maximum_current_a=8000.0,
        minimum_coordination_interval_s=0.3,
        downstream_breaker=breaker,
        sample_count=25,
    )
    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.minimum_achieved_margin_s > 0.3
    assert result.samples[0].downstream_clearing_time_s > (
        result.samples[0].downstream_operating_time_s
    )


def test_relay_pair_coordination_detects_insufficient_margin():
    downstream = make_relay("R-DOWN", ct_primary=1000.0, pickup=1.0, tms=0.2)
    upstream = make_relay("R-UP", ct_primary=1000.0, pickup=0.5, tms=0.05)
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-DOWN",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
    )
    result = ProtectionCoordinationAnalyzer().coordinate_relay_pair(
        downstream,
        upstream,
        minimum_current_a=1500.0,
        maximum_current_a=8000.0,
        minimum_coordination_interval_s=0.3,
        downstream_breaker=breaker,
        sample_count=25,
    )
    assert result.status is ProtectionAssessmentStatus.FAIL
    assert result.minimum_achieved_margin_s < 0.3


def test_relay_pair_coordination_detects_upstream_relay_not_sensitive():
    downstream = make_relay("R-DOWN", ct_primary=1000.0, pickup=1.0, tms=0.1)
    upstream = make_relay("R-UP", ct_primary=1000.0, pickup=20.0, tms=1.0)
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-DOWN",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
    )
    result = ProtectionCoordinationAnalyzer().coordinate_relay_pair(
        downstream,
        upstream,
        minimum_current_a=1500.0,
        maximum_current_a=3000.0,
        minimum_coordination_interval_s=0.3,
        downstream_breaker=breaker,
        sample_count=10,
    )
    assert result.status is ProtectionAssessmentStatus.FAIL
    assert any(item.code == "PROTECTION-UPSTREAM-NOT-SENSITIVE" for item in result.diagnostics)


def test_fuse_relay_coordination_uses_total_clearing_curve():
    fuse = make_fuse()
    upstream = make_relay("R-UP", ct_primary=1000.0, pickup=0.5, tms=1.0)
    result = ProtectionCoordinationAnalyzer().coordinate_fuse_relay(
        fuse,
        upstream,
        minimum_current_a=1000.0,
        maximum_current_a=8000.0,
        minimum_coordination_interval_s=0.2,
        sample_count=20,
    )
    assert result.status is ProtectionAssessmentStatus.PASS
    assert len(result.samples) == 20


def test_fuse_relay_coordination_refuses_to_extrapolate_manufacturer_curve():
    fuse = make_fuse()
    upstream = make_relay("R-UP", ct_primary=1000.0, pickup=0.5, tms=1.0)
    with pytest.raises(ProtectionCoordinationError, match="fully covered"):
        ProtectionCoordinationAnalyzer().coordinate_fuse_relay(
            fuse,
            upstream,
            minimum_current_a=50.0,
            maximum_current_a=8000.0,
            minimum_coordination_interval_s=0.2,
        )


def test_coordination_rejects_invalid_current_range():
    downstream = make_relay("R-DOWN")
    upstream = make_relay("R-UP")
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-DOWN",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
    )
    with pytest.raises(ProtectionCoordinationError, match="range"):
        ProtectionCoordinationAnalyzer().coordinate_relay_pair(
            downstream,
            upstream,
            minimum_current_a=5000.0,
            maximum_current_a=1000.0,
            minimum_coordination_interval_s=0.3,
            downstream_breaker=breaker,
        )


def test_fuse_duty_checks_voltage_and_breaking_capacity():
    fuse = make_fuse()
    result = ProtectionDutyEvaluator().evaluate_fuse(
        fuse, make_iec_result(initial=10.0), operating_voltage_kv=0.4
    )
    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.checks["voltage"] is ProtectionAssessmentStatus.PASS
    assert result.checks["breaking_capacity"] is ProtectionAssessmentStatus.PASS


def test_fuse_duty_fails_when_prospective_current_exceeds_breaking_capacity():
    fuse = FuseLink(
        id=uuid4(),
        name="F-LOW-IC",
        rated_current_a=100.0,
        rated_voltage_kv=0.4,
        breaking_capacity_ka=6.0,
        characteristic_points=(
            FuseTimeCurrentPoint(100.0, 10.0, 12.0),
            FuseTimeCurrentPoint(1000.0, 1.0, 1.2),
        ),
    )
    result = ProtectionDutyEvaluator().evaluate_fuse(
        fuse, make_iec_result(initial=10.0), operating_voltage_kv=0.4
    )
    assert result.status is ProtectionAssessmentStatus.FAIL
    assert result.checks["breaking_capacity"] is ProtectionAssessmentStatus.FAIL


def test_breaker_icw_check_compares_joule_energy_to_rated_short_time_energy():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-ICW-LOW",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        short_time_withstand_current_ka=5.0,
        short_time_withstand_duration_s=1.0,
    )
    result = ProtectionDutyEvaluator().evaluate_breaker(
        breaker, make_iec_result(joule=64.0), operating_voltage_kv=13.8
    )
    assert result.checks["icw"] is ProtectionAssessmentStatus.FAIL
    assert result.margins["icw_i2t_ka2s"] == pytest.approx(-39.0)


def test_breaker_icw_is_not_evaluated_without_iec_joule_integral():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-ICW-UNKNOWN",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        short_time_withstand_current_ka=15.0,
        short_time_withstand_duration_s=2.0,
    )
    original = make_iec_result()
    study = IEC60909StudyResult(
        standard_edition=original.standard_edition,
        base_result=original.base_result,
        current_case=original.current_case,
        voltage_factor=original.voltage_factor,
        equivalent_voltage_pu=original.equivalent_voltage_pu,
        initial_symmetrical_current_ka=original.initial_symmetrical_current_ka,
        peak_current_factor=original.peak_current_factor,
        peak_current_ka=original.peak_current_ka,
        breaking_current_ka=original.breaking_current_ka,
        steady_state_current_ka=original.steady_state_current_ka,
        thermal_factor_dc=None,
        thermal_factor_ac=None,
        thermal_equivalent_current_ka=None,
        joule_integral_ka2s=None,
        fault_duration_s=original.fault_duration_s,
        frequency_hz=original.frequency_hz,
        applied_transformer_correction_factors={},
    )
    result = ProtectionDutyEvaluator().evaluate_breaker(breaker, study, operating_voltage_kv=13.8)
    assert result.checks["icw"] is ProtectionAssessmentStatus.NOT_EVALUATED


def test_relay_pair_coordination_rejects_phase_earth_channel_mismatch():
    downstream = make_relay("R-PHASE", tms=0.1)
    upstream = OvercurrentRelay(
        id=uuid4(),
        name="R-EARTH",
        current_transformer=CurrentTransformerRatio(1000.0, 5.0),
        function=ProtectionFunction.EARTH,
        pickup_secondary_a=0.5,
        curve_type=IECInverseCurveType.STANDARD_INVERSE,
        time_multiplier=1.0,
    )
    breaker = CircuitBreaker(
        id=uuid4(),
        name="CB-DOWN",
        rated_voltage_kv=15.0,
        rated_current_a=630.0,
        rated_short_circuit_breaking_current_ka=25.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
    )
    with pytest.raises(ProtectionCoordinationError, match="same phase/earth"):
        ProtectionCoordinationAnalyzer().coordinate_relay_pair(
            downstream,
            upstream,
            minimum_current_a=1500.0,
            maximum_current_a=3000.0,
            minimum_coordination_interval_s=0.3,
            downstream_breaker=breaker,
        )


def test_lv_breaker_duty_checks_icu_and_ics_under_iec_60947_2():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="LV-CB-PASS",
        rated_voltage_kv=0.4,
        rated_current_a=630.0,
        ultimate_breaking_capacity_ka=25.0,
        service_breaking_capacity_ka=15.0,
        making_capacity_peak_ka=40.0,
        standard=CircuitBreakerStandard.IEC_60947_2,
    )
    result = ProtectionDutyEvaluator().evaluate_breaker(
        breaker, make_iec_result(), operating_voltage_kv=0.4
    )
    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.checks["icu"] is ProtectionAssessmentStatus.PASS
    assert result.checks["ics"] is ProtectionAssessmentStatus.PASS


def test_lv_breaker_duty_fails_when_ics_is_below_calculated_breaking_current():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="LV-CB-ICS-FAIL",
        rated_voltage_kv=0.4,
        rated_current_a=630.0,
        ultimate_breaking_capacity_ka=25.0,
        service_breaking_capacity_ka=8.0,
        standard=CircuitBreakerStandard.IEC_60947_2,
    )
    result = ProtectionDutyEvaluator().evaluate_breaker(
        breaker, make_iec_result(), operating_voltage_kv=0.4
    )
    assert result.checks["icu"] is ProtectionAssessmentStatus.PASS
    assert result.checks["ics"] is ProtectionAssessmentStatus.FAIL
    assert result.status is ProtectionAssessmentStatus.FAIL


def test_breaker_rejects_lv_standard_above_one_kv():
    with pytest.raises(ValueError, match="up to 1 kV"):
        CircuitBreaker(
            id=uuid4(),
            name="INVALID-LV-STANDARD",
            rated_voltage_kv=13.8,
            rated_current_a=630.0,
            standard=CircuitBreakerStandard.IEC_60947_2,
            ultimate_breaking_capacity_ka=25.0,
        )


def test_breaker_rejects_mv_standard_at_or_below_one_kv():
    with pytest.raises(ValueError, match="above 1 kV"):
        CircuitBreaker(
            id=uuid4(),
            name="INVALID-MV-STANDARD",
            rated_voltage_kv=0.4,
            rated_current_a=630.0,
            rated_short_circuit_breaking_current_ka=25.0,
            standard=CircuitBreakerStandard.IEC_62271_100,
        )


def test_mv_breaker_rejects_icu_ics_fields():
    with pytest.raises(ValueError, match="Icu/Ics fields are not used"):
        CircuitBreaker(
            id=uuid4(),
            name="MIXED-STANDARD-RATINGS",
            rated_voltage_kv=13.8,
            rated_current_a=630.0,
            ultimate_breaking_capacity_ka=25.0,
            rated_short_circuit_breaking_current_ka=25.0,
            standard=CircuitBreakerStandard.IEC_62271_100,
        )
