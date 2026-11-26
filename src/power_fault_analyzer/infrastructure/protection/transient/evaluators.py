"""Time-domain CT, overcurrent-relay and circuit-breaker evaluators.

These evaluators use explicit single-valued CT magnetization and ideal current-zero
interruption assumptions. They are engineering simulations, not type-test models.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from itertools import pairwise

import numpy as np
from scipy.integrate import solve_ivp

from power_fault_analyzer.domain.enums.protection import (
    ProtectionAssessmentStatus,
    ProtectionStage,
)
from power_fault_analyzer.domain.value_objects.advanced_protection import (
    CurrentTransformerPerformanceModel,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    OvercurrentRelay,
)
from power_fault_analyzer.domain.value_objects.transient_protection import (
    BreakerPoleInterruption,
    BreakerTransientResult,
    BreakerTransientSettings,
    CTTransientSample,
    CTTransientSimulationResult,
    CTTransientSimulationSettings,
    RelayCurrentSample,
    RelayTransientResult,
    RelayTransientSample,
    RelayTransientSettings,
    ThreePhaseCurrentSample,
)


class TransientProtectionError(ValueError):
    """Raised when transient protection inputs are inconsistent or unsupported."""


class CurrentTransformerTransientSimulator:
    """Integrate a nonlinear single-phase CT equivalent in the time domain.

    The excitation curve is converted from RMS voltage/current points into peak
    flux-linkage/excitation-current points at the CT rated frequency. The
    magnetization characteristic is single-valued and log-log interpolated;
    hysteresis loops, eddy currents and remanence evolution are not represented.
    """

    _MAX_SAMPLES = 200_001

    def simulate(
        self,
        model: CurrentTransformerPerformanceModel,
        settings: CTTransientSimulationSettings,
    ) -> CTTransientSimulationResult:
        if not isinstance(model, CurrentTransformerPerformanceModel):
            raise TypeError("model must be a CurrentTransformerPerformanceModel.")
        if not isinstance(settings, CTTransientSimulationSettings):
            raise TypeError("settings must be CTTransientSimulationSettings.")
        if model.burden_impedance_ohm.real < -1e-12:
            raise TransientProtectionError(
                "Negative-resistance CT burden is not supported by the transient equivalent."
            )
        if model.burden_impedance_ohm.imag < -1e-12:
            raise TransientProtectionError(
                "Capacitive CT burden is not supported by the transient equivalent."
            )
        if model.excitation_curve[-1].voltage_v < model.knee_point_voltage_v:
            raise TransientProtectionError(
                "CT excitation curve must extend at least to the declared knee-point voltage."
            )
        samples_count = math.ceil(settings.duration_s / settings.time_step_s) + 1
        if samples_count > self._MAX_SAMPLES:
            raise TransientProtectionError(
                f"CT simulation exceeds the sample limit ({self._MAX_SAMPLES:,})."
            )
        if settings.time_step_s * settings.system_frequency_hz > 1.0 / 32.0:
            raise TransientProtectionError(
                "time_step_s must provide at least 32 samples per system cycle."
            )

        frequency = settings.system_frequency_hz
        omega = 2.0 * math.pi * frequency
        rated_omega = 2.0 * math.pi * model.rated_frequency_hz
        ratio = model.current_transformer.ratio
        resistance = model.secondary_winding_resistance_ohm + model.burden_impedance_ohm.real
        inductance = model.burden_impedance_ohm.imag / rated_omega
        knee_flux = math.sqrt(2.0) * model.knee_point_voltage_v / rated_omega
        curve_flux = tuple(
            math.sqrt(2.0) * point.voltage_v / rated_omega for point in model.excitation_curve
        )
        curve_current = tuple(
            math.sqrt(2.0) * point.exciting_current_a for point in model.excitation_curve
        )
        maximum_curve_flux = curve_flux[-1]
        peak_secondary_scale = math.sqrt(2.0) * settings.primary_current_rms_a / ratio

        def excitation(flux: float) -> tuple[float, float]:
            magnitude = abs(flux)
            if magnitude <= 0.0:
                slope = curve_current[0] / curve_flux[0]
                return 0.0, slope
            if magnitude <= curve_flux[0]:
                slope = curve_current[0] / curve_flux[0]
                return math.copysign(slope * magnitude, flux), slope
            index = len(curve_flux) - 2
            for candidate, (left, right) in enumerate(pairwise(curve_flux)):
                if magnitude <= right:
                    index = candidate
                    break
            left_flux = curve_flux[index]
            right_flux = curve_flux[index + 1]
            left_current = curve_current[index]
            right_current = curve_current[index + 1]
            exponent = math.log(right_current / left_current) / math.log(right_flux / left_flux)
            current_magnitude = left_current * (magnitude / left_flux) ** exponent
            derivative = exponent * current_magnitude / magnitude
            return math.copysign(current_magnitude, flux), derivative

        def primary_current(time_s: float) -> float:
            phase = omega * time_s + settings.inception_angle_rad
            dc = settings.dc_offset_initial_pu * math.exp(-time_s / settings.dc_time_constant_s)
            return peak_secondary_scale * (math.sin(phase) + dc) * ratio

        def ideal_secondary_current(time_s: float) -> float:
            phase = omega * time_s + settings.inception_angle_rad
            dc = settings.dc_offset_initial_pu * math.exp(-time_s / settings.dc_time_constant_s)
            return peak_secondary_scale * (math.sin(phase) + dc)

        def ideal_secondary_derivative(time_s: float) -> float:
            phase = omega * time_s + settings.inception_angle_rad
            dc_derivative = (
                -settings.dc_offset_initial_pu
                / settings.dc_time_constant_s
                * math.exp(-time_s / settings.dc_time_constant_s)
            )
            return peak_secondary_scale * (omega * math.cos(phase) + dc_derivative)

        def flux_derivative(time_s: float, state: np.ndarray) -> np.ndarray:
            flux = float(state[0])
            exciting_current, exciting_slope = excitation(flux)
            ideal_current = ideal_secondary_current(time_s)
            secondary_current = ideal_current - exciting_current
            numerator = resistance * secondary_current + inductance * ideal_secondary_derivative(
                time_s
            )
            denominator = 1.0 + inductance * exciting_slope
            return np.asarray([numerator / denominator], dtype=float)

        step_count = samples_count - 1
        actual_step = settings.duration_s / step_count
        time_values = np.linspace(0.0, settings.duration_s, samples_count)
        initial_flux = settings.remanent_flux_pu * knee_flux
        solution = solve_ivp(
            flux_derivative,
            (0.0, settings.duration_s),
            [initial_flux],
            method="RK45",
            t_eval=time_values,
            max_step=actual_step,
            rtol=1e-7,
            atol=1e-10,
        )
        if not solution.success or solution.y.shape[1] != samples_count:
            raise TransientProtectionError(f"CT transient integration failed: {solution.message}")

        output: list[CTTransientSample] = []
        ideal_values: list[float] = []
        secondary_values: list[float] = []
        curve_exceeded = False
        saturation_count = 0
        peak_flux_pu = 0.0
        for index, time_s in enumerate(solution.t):
            flux = float(solution.y[0, index])
            exciting_current, _ = excitation(flux)
            ideal_current = ideal_secondary_current(float(time_s))
            secondary_current = ideal_current - exciting_current
            voltage = float(flux_derivative(float(time_s), np.asarray([flux]))[0])
            flux_pu = flux / knee_flux
            saturated = abs(flux_pu) >= 1.0
            saturation_count += int(saturated)
            peak_flux_pu = max(peak_flux_pu, abs(flux_pu))
            curve_exceeded = curve_exceeded or abs(flux) > maximum_curve_flux * (1.0 + 1e-9)
            ideal_values.append(ideal_current)
            secondary_values.append(secondary_current)
            output.append(
                CTTransientSample(
                    time_s=float(time_s),
                    primary_current_a=primary_current(float(time_s)),
                    ideal_secondary_current_a=ideal_current,
                    exciting_current_a=exciting_current,
                    secondary_current_a=secondary_current,
                    secondary_voltage_v=voltage,
                    flux_linkage_v_s=flux,
                    flux_pu=flux_pu,
                    saturated=saturated,
                )
            )

        ideal_rms = math.sqrt(sum(value * value for value in ideal_values) / len(ideal_values))
        secondary_rms = math.sqrt(
            sum(value * value for value in secondary_values) / len(secondary_values)
        )
        error_rms = math.sqrt(
            sum((actual - ideal) ** 2 for actual, ideal in zip(secondary_values, ideal_values))
            / len(ideal_values)
        )
        error_ratio = error_rms / ideal_rms if ideal_rms > 1e-15 else 0.0
        saturation_fraction = saturation_count / samples_count
        diagnostics = [
            (
                "Single-valued magnetization curve; hysteresis and eddy-current losses "
                "are not modeled."
            ),
            "Remanent flux is an initial condition and does not evolve through a hysteresis model.",
            "DC offset is represented by a user-specified exponential time constant.",
        ]
        if curve_exceeded:
            diagnostics.append(
                "Flux exceeded the supplied excitation-curve range; post-range continuation is "
                "numerical only and the transient result is NOT_EVALUATED."
            )
            status = ProtectionAssessmentStatus.NOT_EVALUATED
        elif saturation_fraction > 0.0:
            status = ProtectionAssessmentStatus.FAIL
        else:
            status = ProtectionAssessmentStatus.PASS
        return CTTransientSimulationResult(
            current_transformer_id=model.id,
            current_transformer_ratio=ratio,
            settings=settings,
            status=status,
            samples=tuple(output),
            knee_point_flux_linkage_v_s=knee_flux,
            peak_flux_pu=peak_flux_pu,
            saturation_fraction=saturation_fraction,
            ideal_secondary_rms_current_a=ideal_rms,
            secondary_rms_current_a=secondary_rms,
            current_transfer_error_ratio=error_ratio,
            excitation_curve_exceeded=curve_exceeded,
            diagnostics=tuple(diagnostics),
        )


class OvercurrentRelayTransientEvaluator:
    """Sample instantaneous secondary current and integrate 50/51 operating time.

    A one-cycle sliding RMS is used by default. The IDMT timer accumulates the
    fraction ``dt / t_operate(I_rms)``; below the configured dropout ratio it
    decays exponentially using the supplied reset time constant. This is an
    explicit numerical relay model, not a manufacturer-specific firmware model.
    """

    _MIN_SAMPLES_PER_CYCLE = 32

    def evaluate(
        self,
        relay: OvercurrentRelay,
        current_samples: Sequence[RelayCurrentSample],
        settings: RelayTransientSettings,
    ) -> RelayTransientResult:
        if not isinstance(relay, OvercurrentRelay):
            raise TypeError("relay must be an OvercurrentRelay.")
        if not isinstance(settings, RelayTransientSettings):
            raise TypeError("settings must be RelayTransientSettings.")
        samples = tuple(current_samples)
        if len(samples) < 2 or any(not isinstance(item, RelayCurrentSample) for item in samples):
            raise TypeError("current_samples must contain at least two RelayCurrentSample values.")
        intervals = tuple(right.time_s - left.time_s for left, right in pairwise(samples))
        if any(value <= 0.0 for value in intervals):
            raise TransientProtectionError(
                "Relay current sample times must be strictly increasing."
            )
        dt = intervals[0]
        if any(not math.isclose(value, dt, rel_tol=1e-6, abs_tol=1e-12) for value in intervals):
            raise TransientProtectionError("Relay current samples must use a uniform time step.")
        samples_per_cycle = 1.0 / (dt * settings.system_frequency_hz)
        if samples_per_cycle < self._MIN_SAMPLES_PER_CYCLE:
            raise TransientProtectionError(
                f"At least {self._MIN_SAMPLES_PER_CYCLE} samples per cycle are required."
            )
        window_size = max(
            2, round(settings.rms_window_cycles / (settings.system_frequency_hz * dt))
        )
        if window_size > len(samples):
            return RelayTransientResult(
                relay_id=relay.id,
                settings=settings,
                status=ProtectionAssessmentStatus.NOT_EVALUATED,
                operated=False,
                trip_stage=None,
                trip_command_time_s=None,
                trip_output_time_s=None,
                maximum_inverse_timer_fraction=settings.initial_inverse_timer_fraction,
                samples=tuple(
                    RelayTransientSample(
                        item.time_s,
                        None,
                        None,
                        settings.initial_inverse_timer_fraction,
                        0.0,
                        None,
                        False,
                    )
                    for item in samples
                ),
                diagnostics=("Waveform is shorter than the configured RMS measurement window.",),
            )

        square_window: deque[float] = deque()
        square_sum = 0.0
        inverse_timer = settings.initial_inverse_timer_fraction
        maximum_timer = inverse_timer
        instantaneous_elapsed = 0.0
        tripped = False
        trip_stage: ProtectionStage | None = None
        trip_command: float | None = None
        output: list[RelayTransientSample] = []
        reset_secondary = relay.pickup_secondary_a * settings.reset_ratio

        for sample in samples:
            squared = sample.secondary_current_a * sample.secondary_current_a
            square_window.append(squared)
            square_sum += squared
            if len(square_window) > window_size:
                square_sum -= square_window.popleft()
            measured_rms: float | None = None
            multiple: float | None = None
            selected_stage: ProtectionStage | None = None
            if len(square_window) == window_size:
                measured_rms = math.sqrt(max(0.0, square_sum / window_size))
                primary_rms = measured_rms * relay.current_transformer.ratio
                operating_point = relay.operate(primary_rms)
                multiple = operating_point.pickup_multiple
                is_instantaneous = (
                    not tripped and operating_point.stage is ProtectionStage.INSTANTANEOUS_50
                )
                if is_instantaneous:
                    selected_stage = ProtectionStage.INSTANTANEOUS_50
                    instantaneous_elapsed += dt
                else:
                    instantaneous_elapsed = 0.0
                instantaneous_trip = (
                    is_instantaneous
                    and instantaneous_elapsed + 1e-12 >= relay.instantaneous_delay_s
                )
                if instantaneous_trip:
                    tripped = True
                    trip_stage = ProtectionStage.INSTANTANEOUS_50
                    trip_command = sample.time_s

                is_inverse = (
                    not tripped and operating_point.stage is ProtectionStage.TIME_INVERSE_51
                )
                is_below_reset = (
                    not tripped
                    and operating_point.stage is None
                    and measured_rms <= reset_secondary
                )
                if is_inverse:
                    selected_stage = ProtectionStage.TIME_INVERSE_51
                    assert operating_point.operating_time_s is not None
                    inverse_timer += dt / operating_point.operating_time_s
                elif is_below_reset:
                    inverse_timer *= math.exp(-dt / settings.reset_time_constant_s)
                if not tripped and inverse_timer >= 1.0:
                    inverse_timer = 1.0
                    tripped = True
                    trip_stage = ProtectionStage.TIME_INVERSE_51
                    trip_command = sample.time_s
            maximum_timer = max(maximum_timer, inverse_timer)
            output.append(
                RelayTransientSample(
                    time_s=sample.time_s,
                    measured_secondary_rms_a=measured_rms,
                    pickup_multiple=multiple,
                    inverse_timer_fraction=min(1.0, inverse_timer),
                    instantaneous_elapsed_s=instantaneous_elapsed,
                    selected_stage=selected_stage,
                    tripped=tripped,
                )
            )
        status = ProtectionAssessmentStatus.PASS
        diagnostics = []
        if not tripped:
            diagnostics.append(
                "Relay did not reach its trip criterion within the supplied waveform."
            )
        return RelayTransientResult(
            relay_id=relay.id,
            settings=settings,
            status=status,
            operated=tripped,
            trip_stage=trip_stage,
            trip_command_time_s=trip_command,
            trip_output_time_s=(
                None if trip_command is None else trip_command + settings.output_delay_s
            ),
            maximum_inverse_timer_fraction=min(1.0, maximum_timer),
            samples=tuple(output),
            diagnostics=tuple(diagnostics),
        )

    def evaluate_ct_output(
        self,
        relay: OvercurrentRelay,
        ct_result: CTTransientSimulationResult,
        settings: RelayTransientSettings,
    ) -> RelayTransientResult:
        if not isinstance(ct_result, CTTransientSimulationResult):
            raise TypeError("ct_result must be a CTTransientSimulationResult.")
        if not math.isclose(
            ct_result.current_transformer_ratio,
            relay.current_transformer.ratio,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise TransientProtectionError(
                "CT transient ratio must match the relay current-transformer ratio."
            )
        current_samples = tuple(
            RelayCurrentSample(item.time_s, item.secondary_current_a) for item in ct_result.samples
        )
        result = self.evaluate(relay, current_samples, settings)
        if ct_result.status is ProtectionAssessmentStatus.NOT_EVALUATED:
            return RelayTransientResult(
                relay_id=result.relay_id,
                settings=result.settings,
                status=ProtectionAssessmentStatus.NOT_EVALUATED,
                operated=result.operated,
                trip_stage=result.trip_stage,
                trip_command_time_s=result.trip_command_time_s,
                trip_output_time_s=result.trip_output_time_s,
                maximum_inverse_timer_fraction=result.maximum_inverse_timer_fraction,
                samples=result.samples,
                diagnostics=result.diagnostics
                + (
                    (
                        "CT transient exceeded the manufacturer excitation-curve range; "
                        "relay response is retained as an indicative partial result."
                    ),
                ),
            )
        if ct_result.status is ProtectionAssessmentStatus.FAIL:
            return RelayTransientResult(
                relay_id=result.relay_id,
                settings=result.settings,
                status=ProtectionAssessmentStatus.FAIL,
                operated=result.operated,
                trip_stage=result.trip_stage,
                trip_command_time_s=result.trip_command_time_s,
                trip_output_time_s=result.trip_output_time_s,
                maximum_inverse_timer_fraction=result.maximum_inverse_timer_fraction,
                samples=result.samples,
                diagnostics=result.diagnostics
                + ("CT core flux crossed the knee-point threshold during the transient.",),
            )
        return result


class CircuitBreakerTransientEvaluator:
    """Estimate per-pole current-zero interruption after a relay trip command.

    The breaker contacts separate after the device opening time and supplied
    per-pole scatter. Arc extinction is assumed at the first subsequent natural
    current zero; TRV, dielectric recovery and restrike are not simulated.
    """

    def evaluate(
        self,
        breaker: CircuitBreaker,
        relay_result: RelayTransientResult,
        current_samples: Sequence[ThreePhaseCurrentSample],
        settings: BreakerTransientSettings,
    ) -> BreakerTransientResult:
        if not isinstance(breaker, CircuitBreaker):
            raise TypeError("breaker must be a CircuitBreaker.")
        if not isinstance(relay_result, RelayTransientResult):
            raise TypeError("relay_result must be a RelayTransientResult.")
        if not isinstance(settings, BreakerTransientSettings):
            raise TypeError("settings must be BreakerTransientSettings.")
        samples = tuple(current_samples)
        if len(samples) < 2 or any(
            not isinstance(item, ThreePhaseCurrentSample) for item in samples
        ):
            raise TypeError("current_samples must contain at least two three-phase samples.")
        if any(right.time_s <= left.time_s for left, right in pairwise(samples)):
            raise TransientProtectionError(
                "Three-phase current sample times must be strictly increasing."
            )
        if (
            not relay_result.operated
            or relay_result.trip_output_time_s is None
            or relay_result.status is not ProtectionAssessmentStatus.PASS
        ):
            reason = (
                "Circuit breaker cannot be evaluated because the relay did not trip."
                if not relay_result.operated
                else "Circuit breaker cannot consume a relay result that is not PASS."
            )
            return BreakerTransientResult(
                breaker_id=breaker.id,
                settings=settings,
                status=ProtectionAssessmentStatus.NOT_EVALUATED,
                relay_trip_command_time_s=0.0,
                poles=tuple(
                    BreakerPoleInterruption(phase, 0.0, None, None, False, None, None)
                    for phase in ("A", "B", "C")
                ),  # type: ignore[arg-type]
                total_clearing_time_s=None,
                diagnostics=(reason,),
            )

        trip_time = relay_result.trip_output_time_s
        poles: list[BreakerPoleInterruption] = []
        for phase_index, phase in enumerate(("A", "B", "C")):
            contact_time = (
                trip_time + breaker.opening_time_s + settings.pole_scatter_s_by_phase[phase_index]
            )
            contact_current = self._interpolate_current(samples, phase_index, contact_time)
            zero_time = self._first_zero_after(
                samples,
                phase_index,
                contact_time,
                contact_time + settings.maximum_arc_duration_s,
            )
            arcing_duration = None if zero_time is None else zero_time - contact_time
            poles.append(
                BreakerPoleInterruption(
                    phase=phase,
                    contact_separation_time_s=contact_time,
                    current_at_contact_separation_a=contact_current,
                    current_zero_time_s=zero_time,
                    interrupted=zero_time is not None,
                    arcing_duration_s=arcing_duration,
                    within_rated_arcing_time=(
                        None
                        if arcing_duration is None
                        else arcing_duration <= breaker.arcing_time_s + 1e-12
                    ),
                )
            )
        all_interrupted = all(item.interrupted for item in poles)
        rated_arcing_ok = all(item.within_rated_arcing_time for item in poles)
        if not all_interrupted:
            status = ProtectionAssessmentStatus.NOT_EVALUATED
        elif rated_arcing_ok:
            status = ProtectionAssessmentStatus.PASS
        else:
            status = ProtectionAssessmentStatus.FAIL
        clearing_time = (
            max(item.current_zero_time_s for item in poles if item.current_zero_time_s is not None)
            - relay_result.trip_command_time_s
            if all_interrupted and relay_result.trip_command_time_s is not None
            else None
        )
        diagnostics = (
            "Ideal interruption at first natural current zero; TRV and restrike are not modeled.",
        )
        if not all_interrupted:
            diagnostics += ("At least one pole has no sampled current zero within the arc window.",)
        elif not rated_arcing_ok:
            diagnostics += ("At least one pole exceeds the breaker rated arcing time.",)
        return BreakerTransientResult(
            breaker_id=breaker.id,
            settings=settings,
            status=status,
            relay_trip_command_time_s=relay_result.trip_command_time_s or 0.0,
            poles=(poles[0], poles[1], poles[2]),
            total_clearing_time_s=clearing_time,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _interpolate_current(
        samples: tuple[ThreePhaseCurrentSample, ...], phase_index: int, time_s: float
    ) -> float | None:
        if time_s < samples[0].time_s or time_s > samples[-1].time_s:
            return None
        for left, right in pairwise(samples):
            if left.time_s <= time_s <= right.time_s:
                fraction = (time_s - left.time_s) / (right.time_s - left.time_s)
                return left.phase_currents_a[phase_index] + fraction * (
                    right.phase_currents_a[phase_index] - left.phase_currents_a[phase_index]
                )
        if math.isclose(time_s, samples[-1].time_s, abs_tol=1e-12):
            return samples[-1].phase_currents_a[phase_index]
        return None

    @staticmethod
    def _first_zero_after(
        samples: tuple[ThreePhaseCurrentSample, ...],
        phase_index: int,
        start_s: float,
        end_s: float,
    ) -> float | None:
        start_current = CircuitBreakerTransientEvaluator._interpolate_current(
            samples, phase_index, start_s
        )
        if start_current is None:
            return None
        if abs(start_current) <= 1e-9:
            return start_s
        previous_time = start_s
        previous_current = start_current
        for sample in samples:
            if sample.time_s <= start_s:
                continue
            if sample.time_s > end_s:
                break
            current = sample.phase_currents_a[phase_index]
            if abs(current) <= 1e-9:
                return sample.time_s
            if previous_current * current < 0.0:
                fraction = abs(previous_current) / (abs(previous_current) + abs(current))
                return previous_time + fraction * (sample.time_s - previous_time)
            previous_time = sample.time_s
            previous_current = current
        return None
