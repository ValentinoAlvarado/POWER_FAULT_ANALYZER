from __future__ import annotations

import math
from uuid import uuid4

import pytest

from power_fault_analyzer.domain.enums.protection import (
    CircuitBreakerStandard,
    IECInverseCurveType,
    ProtectionAssessmentStatus,
    ProtectionFunction,
    ProtectionStage,
)
from power_fault_analyzer.domain.value_objects.advanced_protection import (
    CTExcitationPoint,
    CurrentTransformerPerformanceModel,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    CurrentTransformerRatio,
    OvercurrentRelay,
)
from power_fault_analyzer.domain.value_objects.transient_protection import (
    BreakerTransientSettings,
    CTTransientSimulationSettings,
    RelayCurrentSample,
    RelayTransientResult,
    RelayTransientSettings,
    ThreePhaseCurrentSample,
)
from power_fault_analyzer.infrastructure.protection.transient import (
    CircuitBreakerTransientEvaluator,
    CurrentTransformerTransientSimulator,
    OvercurrentRelayTransientEvaluator,
    TransientProtectionError,
)


def make_ct_model(*, burden: complex = 0.5 + 0.05j) -> CurrentTransformerPerformanceModel:
    return CurrentTransformerPerformanceModel(
        name="CT-600-5-PX",
        current_transformer=CurrentTransformerRatio(600.0, 5.0),
        secondary_winding_resistance_ohm=0.2,
        burden_impedance_ohm=burden,
        knee_point_voltage_v=200.0,
        excitation_curve=(
            CTExcitationPoint(10.0, 0.01),
            CTExcitationPoint(25.0, 0.02),
            CTExcitationPoint(50.0, 0.04),
            CTExcitationPoint(100.0, 0.12),
            CTExcitationPoint(200.0, 0.5),
            CTExcitationPoint(400.0, 5.0),
            CTExcitationPoint(800.0, 30.0),
            CTExcitationPoint(1600.0, 100.0),
        ),
        rated_frequency_hz=50.0,
    )


def make_relay(
    *,
    tms: float = 0.01,
    curve: IECInverseCurveType = IECInverseCurveType.EXTREMELY_INVERSE,
    instantaneous_pickup: float | None = None,
    instantaneous_delay: float = 0.0,
) -> OvercurrentRelay:
    return OvercurrentRelay(
        id=uuid4(),
        name="51-TRANSIENT-TEST",
        current_transformer=CurrentTransformerRatio(600.0, 5.0),
        function=ProtectionFunction.PHASE,
        pickup_secondary_a=5.0,
        curve_type=curve,
        time_multiplier=tms,
        instantaneous_pickup_secondary_a=instantaneous_pickup,
        instantaneous_delay_s=instantaneous_delay,
    )


def make_current_samples(
    *,
    duration_s: float = 0.12,
    step_s: float = 0.0001,
    rms_secondary_a: float = 50.0,
    frequency_hz: float = 50.0,
) -> tuple[RelayCurrentSample, ...]:
    count = round(duration_s / step_s)
    return tuple(
        RelayCurrentSample(
            index * step_s,
            math.sqrt(2.0)
            * rms_secondary_a
            * math.sin(2.0 * math.pi * frequency_hz * index * step_s),
        )
        for index in range(count + 1)
    )


def make_breaker() -> CircuitBreaker:
    return CircuitBreaker(
        id=uuid4(),
        name="52-TEST-MV",
        rated_voltage_kv=13.8,
        rated_current_a=1250.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        rated_short_circuit_breaking_current_ka=25.0,
        opening_time_s=0.005,
        arcing_time_s=0.025,
    )


def make_three_phase_samples(
    *, duration_s: float = 0.08, step_s: float = 0.0001
) -> tuple[ThreePhaseCurrentSample, ...]:
    count = round(duration_s / step_s)
    omega = 2.0 * math.pi * 50.0
    amplitude = math.sqrt(2.0) * 1000.0
    return tuple(
        ThreePhaseCurrentSample(
            index * step_s,
            (
                amplitude * math.sin(omega * index * step_s),
                amplitude * math.sin(omega * index * step_s - 2.0 * math.pi / 3.0),
                amplitude * math.sin(omega * index * step_s + 2.0 * math.pi / 3.0),
            ),
        )
        for index in range(count + 1)
    )


def make_operated_relay_result() -> RelayTransientResult:
    return RelayTransientResult(
        relay_id=uuid4(),
        settings=RelayTransientSettings(50.0),
        status=ProtectionAssessmentStatus.PASS,
        operated=True,
        trip_stage=ProtectionStage.TIME_INVERSE_51,
        trip_command_time_s=0.01,
        trip_output_time_s=0.012,
        maximum_inverse_timer_fraction=1.0,
        samples=(),
    )


def test_ct_transient_returns_time_domain_samples_and_transfer_error():
    result = CurrentTransformerTransientSimulator().simulate(
        make_ct_model(),
        CTTransientSimulationSettings(
            primary_current_rms_a=500.0,
            system_frequency_hz=50.0,
            duration_s=0.06,
            time_step_s=0.0001,
        ),
    )

    assert result.status is ProtectionAssessmentStatus.PASS
    assert len(result.samples) == 601
    assert result.ideal_secondary_rms_current_a > 0.0
    assert result.secondary_rms_current_a > 0.0
    assert result.current_transfer_error_ratio >= 0.0
    assert all(math.isfinite(item.flux_pu) for item in result.samples)


def test_ct_transient_detects_core_flux_above_knee_point():
    result = CurrentTransformerTransientSimulator().simulate(
        make_ct_model(),
        CTTransientSimulationSettings(
            primary_current_rms_a=60_000.0,
            system_frequency_hz=50.0,
            duration_s=0.06,
            time_step_s=0.0001,
            dc_offset_initial_pu=0.4,
        ),
    )

    assert result.status is ProtectionAssessmentStatus.FAIL
    assert result.peak_flux_pu >= 1.0
    assert result.saturation_fraction > 0.0
    assert any(item.saturated for item in result.samples)


def test_ct_transient_remanent_flux_is_used_as_initial_state():
    result = CurrentTransformerTransientSimulator().simulate(
        make_ct_model(),
        CTTransientSimulationSettings(
            primary_current_rms_a=0.0,
            system_frequency_hz=50.0,
            duration_s=0.02,
            time_step_s=0.0001,
            remanent_flux_pu=0.75,
        ),
    )

    assert result.samples[0].flux_pu == pytest.approx(0.75)
    assert result.samples[0].saturated is False


def test_ct_transient_exposes_result_as_not_evaluated_above_curve_range():
    result = CurrentTransformerTransientSimulator().simulate(
        make_ct_model(),
        CTTransientSimulationSettings(
            primary_current_rms_a=400_000.0,
            system_frequency_hz=50.0,
            duration_s=0.08,
            time_step_s=0.0001,
            dc_offset_initial_pu=1.0,
        ),
    )

    assert result.excitation_curve_exceeded
    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED
    assert any("excitation-curve range" in item for item in result.diagnostics)


def test_ct_transient_rejects_negative_resistance_burden():
    with pytest.raises(TransientProtectionError, match="Negative-resistance"):
        CurrentTransformerTransientSimulator().simulate(
            make_ct_model(burden=-0.3 + 0.1j),
            CTTransientSimulationSettings(1000.0, 50.0, 0.02, 0.0001),
        )


def test_ct_transient_rejects_capacitive_burden():
    with pytest.raises(TransientProtectionError, match="Capacitive"):
        CurrentTransformerTransientSimulator().simulate(
            make_ct_model(burden=0.5 - 0.1j),
            CTTransientSimulationSettings(1000.0, 50.0, 0.02, 0.0001),
        )


def test_ct_transient_rejects_inadequate_time_resolution():
    with pytest.raises(TransientProtectionError, match="32 samples per"):
        CurrentTransformerTransientSimulator().simulate(
            make_ct_model(),
            CTTransientSimulationSettings(1000.0, 50.0, 0.02, 0.001),
        )


def test_ct_transient_requires_excitation_curve_to_reach_knee_point():
    model = CurrentTransformerPerformanceModel(
        name="CT-INCOMPLETE-EXCITATION-CURVE",
        current_transformer=CurrentTransformerRatio(600.0, 5.0),
        secondary_winding_resistance_ohm=0.2,
        burden_impedance_ohm=0.5 + 0j,
        knee_point_voltage_v=200.0,
        excitation_curve=(CTExcitationPoint(10.0, 0.01), CTExcitationPoint(100.0, 0.1)),
        rated_frequency_hz=50.0,
    )
    with pytest.raises(TransientProtectionError, match="extend at least"):
        CurrentTransformerTransientSimulator().simulate(
            model, CTTransientSimulationSettings(1000.0, 50.0, 0.02, 0.0001)
        )


def test_ct_transient_rejects_excessive_sample_count():
    with pytest.raises(TransientProtectionError, match="sample limit"):
        CurrentTransformerTransientSimulator().simulate(
            make_ct_model(),
            CTTransientSimulationSettings(1000.0, 50.0, 25.0, 0.0001),
        )


def test_relay_transient_integrates_inverse_time_to_trip():
    relay = make_relay()
    settings = RelayTransientSettings(
        system_frequency_hz=50.0,
        rms_window_cycles=1.0,
        output_delay_s=0.003,
    )
    result = OvercurrentRelayTransientEvaluator().evaluate(relay, make_current_samples(), settings)

    expected_time = relay.time_multiplier * 80.0 / (10.0**2 - 1.0)
    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.operated
    assert result.trip_stage is ProtectionStage.TIME_INVERSE_51
    assert result.trip_command_time_s is not None
    assert result.trip_command_time_s == pytest.approx(0.02 + expected_time, abs=0.001)
    assert result.trip_output_time_s == pytest.approx(result.trip_command_time_s + 0.003)


def test_relay_transient_uses_instantaneous_stage_and_delay():
    relay = make_relay(instantaneous_pickup=30.0, instantaneous_delay=0.002)
    result = OvercurrentRelayTransientEvaluator().evaluate(
        relay,
        make_current_samples(),
        RelayTransientSettings(50.0, output_delay_s=0.004),
    )

    assert result.operated
    assert result.trip_stage is ProtectionStage.INSTANTANEOUS_50
    assert result.trip_command_time_s == pytest.approx(0.022, abs=0.0002)
    assert result.trip_output_time_s == pytest.approx(0.026, abs=0.0002)


def test_relay_transient_does_not_operate_below_pickup():
    result = OvercurrentRelayTransientEvaluator().evaluate(
        make_relay(),
        make_current_samples(rms_secondary_a=4.0),
        RelayTransientSettings(50.0),
    )

    assert not result.operated
    assert result.status is ProtectionAssessmentStatus.PASS
    assert result.trip_stage is None


def test_relay_transient_returns_not_evaluated_for_short_waveform():
    samples = make_current_samples(duration_s=0.005)
    result = OvercurrentRelayTransientEvaluator().evaluate(
        make_relay(), samples, RelayTransientSettings(50.0)
    )

    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED
    assert not result.operated


def test_relay_transient_exponentially_resets_timer_below_dropout():
    samples = tuple(RelayCurrentSample(index * 0.0001, 0.0) for index in range(1201))
    result = OvercurrentRelayTransientEvaluator().evaluate(
        make_relay(),
        samples,
        RelayTransientSettings(50.0, initial_inverse_timer_fraction=0.8),
    )

    assert not result.operated
    assert result.samples[-1].inverse_timer_fraction < 0.8


def test_relay_transient_rejects_nonuniform_time_samples():
    samples = (
        RelayCurrentSample(0.0, 0.0),
        RelayCurrentSample(0.0001, 1.0),
        RelayCurrentSample(0.00025, 0.0),
    )
    with pytest.raises(TransientProtectionError, match="uniform"):
        OvercurrentRelayTransientEvaluator().evaluate(
            make_relay(), samples, RelayTransientSettings(50.0)
        )


def test_relay_transient_rejects_low_sampling_rate():
    samples = tuple(RelayCurrentSample(index * 0.001, 0.0) for index in range(20))
    with pytest.raises(TransientProtectionError, match="samples per cycle"):
        OvercurrentRelayTransientEvaluator().evaluate(
            make_relay(), samples, RelayTransientSettings(50.0)
        )


def test_relay_transient_can_consume_ct_secondary_waveform():
    ct_result = CurrentTransformerTransientSimulator().simulate(
        make_ct_model(),
        CTTransientSimulationSettings(40_000.0, 50.0, 0.08, 0.0001),
    )
    relay = make_relay(tms=0.001)
    result = OvercurrentRelayTransientEvaluator().evaluate_ct_output(
        relay, ct_result, RelayTransientSettings(50.0)
    )

    assert result.status is ProtectionAssessmentStatus.FAIL or result.operated
    assert result.relay_id == relay.id


def test_relay_transient_rejects_ct_ratio_mismatch():
    ct_result = CurrentTransformerTransientSimulator().simulate(
        make_ct_model(),
        CTTransientSimulationSettings(1000.0, 50.0, 0.04, 0.0001),
    )
    mismatched_relay = OvercurrentRelay(
        id=uuid4(),
        name="51-WRONG-CT-RATIO",
        current_transformer=CurrentTransformerRatio(300.0, 5.0),
        function=ProtectionFunction.PHASE,
        pickup_secondary_a=5.0,
        curve_type=IECInverseCurveType.STANDARD_INVERSE,
    )
    with pytest.raises(TransientProtectionError, match="must match"):
        OvercurrentRelayTransientEvaluator().evaluate_ct_output(
            mismatched_relay, ct_result, RelayTransientSettings(50.0)
        )


def test_breaker_transient_finds_first_natural_current_zero_per_pole():
    result = CircuitBreakerTransientEvaluator().evaluate(
        make_breaker(),
        make_operated_relay_result(),
        make_three_phase_samples(),
        BreakerTransientSettings(
            pole_scatter_s_by_phase=(0.0, 0.001, 0.002),
            maximum_arc_duration_s=0.025,
        ),
    )

    assert result.status is ProtectionAssessmentStatus.PASS
    assert all(item.interrupted for item in result.poles)
    assert result.poles[0].current_zero_time_s is not None
    assert result.total_clearing_time_s is not None
    assert result.total_clearing_time_s > 0.0


def test_breaker_transient_fails_when_arcing_time_exceeds_breaker_rating():
    breaker = CircuitBreaker(
        id=uuid4(),
        name="52-FAST-ARC-RATING",
        rated_voltage_kv=13.8,
        rated_current_a=1250.0,
        standard=CircuitBreakerStandard.IEC_62271_100,
        rated_short_circuit_breaking_current_ka=25.0,
        opening_time_s=0.005,
        arcing_time_s=0.001,
    )
    result = CircuitBreakerTransientEvaluator().evaluate(
        breaker,
        make_operated_relay_result(),
        make_three_phase_samples(),
        BreakerTransientSettings(maximum_arc_duration_s=0.025),
    )

    assert result.status is ProtectionAssessmentStatus.FAIL
    assert all(item.interrupted for item in result.poles)
    assert any(item.within_rated_arcing_time is False for item in result.poles)


def test_breaker_transient_requires_a_relay_trip():
    relay_result = RelayTransientResult(
        relay_id=uuid4(),
        settings=RelayTransientSettings(50.0),
        status=ProtectionAssessmentStatus.PASS,
        operated=False,
        trip_stage=None,
        trip_command_time_s=None,
        trip_output_time_s=None,
        maximum_inverse_timer_fraction=0.0,
        samples=(),
    )
    result = CircuitBreakerTransientEvaluator().evaluate(
        make_breaker(),
        relay_result,
        make_three_phase_samples(),
        BreakerTransientSettings(),
    )

    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED
    assert result.total_clearing_time_s is None


def test_breaker_transient_rejects_invalid_relay_result_even_if_partial_trip_exists():
    relay_result = RelayTransientResult(
        relay_id=uuid4(),
        settings=RelayTransientSettings(50.0),
        status=ProtectionAssessmentStatus.NOT_EVALUATED,
        operated=True,
        trip_stage=ProtectionStage.TIME_INVERSE_51,
        trip_command_time_s=0.01,
        trip_output_time_s=0.012,
        maximum_inverse_timer_fraction=1.0,
        samples=(),
    )
    result = CircuitBreakerTransientEvaluator().evaluate(
        make_breaker(),
        relay_result,
        make_three_phase_samples(),
        BreakerTransientSettings(),
    )

    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED
    assert result.total_clearing_time_s is None
    assert any("not PASS" in item for item in result.diagnostics)


def test_breaker_transient_marks_missing_current_zero_as_not_evaluated():
    constant = tuple(
        ThreePhaseCurrentSample(index * 0.0001, (1000.0, 1000.0, 1000.0)) for index in range(801)
    )
    result = CircuitBreakerTransientEvaluator().evaluate(
        make_breaker(),
        make_operated_relay_result(),
        constant,
        BreakerTransientSettings(maximum_arc_duration_s=0.01),
    )

    assert result.status is ProtectionAssessmentStatus.NOT_EVALUATED
    assert not any(item.interrupted for item in result.poles)


def test_breaker_transient_rejects_non_monotonic_samples():
    samples = (
        ThreePhaseCurrentSample(0.0, (0.0, 1.0, 2.0)),
        ThreePhaseCurrentSample(0.002, (1.0, 2.0, 3.0)),
        ThreePhaseCurrentSample(0.001, (2.0, 3.0, 4.0)),
    )
    with pytest.raises(TransientProtectionError, match="strictly increasing"):
        CircuitBreakerTransientEvaluator().evaluate(
            make_breaker(),
            make_operated_relay_result(),
            samples,
            BreakerTransientSettings(),
        )


def test_transient_settings_reject_boolean_and_invalid_remanence():
    with pytest.raises(TypeError, match="real number"):
        CTTransientSimulationSettings(1000.0, True, 0.02, 0.0001)
    with pytest.raises(ValueError, match="remanent_flux_pu"):
        CTTransientSimulationSettings(1000.0, 50.0, 0.02, 0.0001, remanent_flux_pu=1.2)
