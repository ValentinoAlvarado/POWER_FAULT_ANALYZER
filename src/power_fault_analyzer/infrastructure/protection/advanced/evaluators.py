"""Steady-state evaluators for 87, 67/67N, distance 21 and CT screening."""

from __future__ import annotations

import cmath
import math
from collections.abc import Sequence
from itertools import pairwise

from power_fault_analyzer.domain.enums.advanced_protection import (
    DirectionalSense,
    DistanceCharacteristic,
    DistanceLoop,
)
from power_fault_analyzer.domain.enums.protection import ProtectionAssessmentStatus
from power_fault_analyzer.domain.value_objects.advanced_protection import (
    CTExcitationPoint,
    CTSaturationAssessment,
    CurrentTransformerPerformanceModel,
    DifferentialMeasurement,
    DifferentialOperationResult,
    DifferentialPhaseOperation,
    DifferentialProtectionSettings,
    DirectionalMeasurement,
    DirectionalOperationResult,
    DirectionalOvercurrentSettings,
    DistanceLoopOperation,
    DistanceMeasurement,
    DistanceOperationResult,
    DistanceProtectionSettings,
)


class AdvancedProtectionError(ValueError):
    """Raised when an advanced-protection input is inconsistent with its settings."""


class DifferentialProtectionEvaluator:
    """Evaluate two-terminal biased differential characteristic in per unit."""

    def evaluate(
        self,
        settings: DifferentialProtectionSettings,
        measurement: DifferentialMeasurement,
    ) -> DifferentialOperationResult:
        if not isinstance(settings, DifferentialProtectionSettings):
            raise TypeError("settings must be DifferentialProtectionSettings.")
        if not isinstance(measurement, DifferentialMeasurement):
            raise TypeError("measurement must be DifferentialMeasurement.")
        expected_side_ids = {item.side_id for item in settings.sides}
        if set(measurement.side_currents_primary_a) != expected_side_ids:
            raise AdvancedProtectionError(
                "Differential measurement side IDs must exactly match relay settings."
            )

        compensated: list[tuple[complex, complex, complex]] = []
        for side in settings.sides:
            raw = measurement.side_currents_primary_a[side.side_id]
            secondary_currents = tuple(value / side.current_transformer.ratio for value in raw)
            secondary_base = side.current_base_primary_a / side.current_transformer.ratio
            normalized = tuple(value / secondary_base for value in secondary_currents)
            matrix = side.phase_compensation_matrix
            transformed = tuple(
                side.polarity * sum(matrix[row][column] * normalized[column] for column in range(3))
                for row in range(3)
            )
            compensated.append(transformed)

        phase_results: list[DifferentialPhaseOperation] = []
        for index, phase in enumerate(("A", "B", "C")):
            side_values = tuple(item[index] for item in compensated)
            differential = abs(sum(side_values))
            restraint = 0.5 * sum(abs(value) for value in side_values)
            if restraint <= settings.breakpoint_restraint_pu:
                threshold = settings.minimum_pickup_pu + settings.low_slope * restraint
            else:
                threshold = (
                    settings.minimum_pickup_pu
                    + settings.low_slope * settings.breakpoint_restraint_pu
                    + settings.high_slope * (restraint - settings.breakpoint_restraint_pu)
                )
            harmonic_ratio = measurement.second_harmonic_ratio_by_phase[index]
            blocked = (
                settings.second_harmonic_block_ratio is not None
                and harmonic_ratio >= settings.second_harmonic_block_ratio
            )
            high_set = (
                settings.unrestrained_pickup_pu is not None
                and differential >= settings.unrestrained_pickup_pu
            )
            operated = high_set or (differential > threshold and not blocked)
            phase_results.append(
                DifferentialPhaseOperation(
                    phase=phase,
                    differential_current_pu=differential,
                    restraint_current_pu=restraint,
                    operating_threshold_pu=threshold,
                    second_harmonic_ratio=harmonic_ratio,
                    blocked_by_harmonic=blocked and not high_set,
                    operated=operated,
                )
            )
        results = tuple(phase_results)
        return DifferentialOperationResult(
            relay_id=settings.id,
            phases=results,
            operated=any(item.operated for item in results),
        )


class DirectionalOvercurrentEvaluator:
    """Apply a cosine directional comparator to an existing overcurrent element."""

    def evaluate(
        self,
        settings: DirectionalOvercurrentSettings,
        measurement: DirectionalMeasurement,
    ) -> DirectionalOperationResult:
        if not isinstance(settings, DirectionalOvercurrentSettings):
            raise TypeError("settings must be DirectionalOvercurrentSettings.")
        if not isinstance(measurement, DirectionalMeasurement):
            raise TypeError("measurement must be DirectionalMeasurement.")
        current = measurement.operating_current_primary_a
        voltage = measurement.polarizing_voltage_v
        response = settings.relay.operate(abs(current))
        if not response.picked_up:
            return DirectionalOperationResult(
                relay_id=settings.id,
                overcurrent_picked_up=False,
                directional_decision=None,
                directional_torque=None,
                operated=False,
                operating_time_s=None,
                reason="Overcurrent element did not pick up.",
            )
        if abs(voltage) < settings.minimum_polarizing_voltage_v:
            return DirectionalOperationResult(
                relay_id=settings.id,
                overcurrent_picked_up=True,
                directional_decision=None,
                directional_torque=None,
                operated=False,
                operating_time_s=None,
                reason="Polarizing voltage is below the configured minimum.",
            )
        if abs(current) <= 1e-12:
            return DirectionalOperationResult(
                relay_id=settings.id,
                overcurrent_picked_up=True,
                directional_decision=None,
                directional_torque=None,
                operated=False,
                operating_time_s=None,
                reason="Operating current phasor is too small for direction determination.",
            )
        relative_angle = math.degrees(cmath.phase(current / voltage))
        torque = math.cos(math.radians(relative_angle - settings.maximum_torque_angle_deg))
        if abs(torque) <= 1e-12:
            return DirectionalOperationResult(
                relay_id=settings.id,
                overcurrent_picked_up=True,
                directional_decision=None,
                directional_torque=torque,
                operated=False,
                operating_time_s=None,
                reason="Directional torque is on the characteristic boundary.",
            )
        measured_direction = DirectionalSense.FORWARD if torque > 0.0 else DirectionalSense.REVERSE
        operated = measured_direction is settings.sense
        return DirectionalOperationResult(
            relay_id=settings.id,
            overcurrent_picked_up=True,
            directional_decision=measured_direction,
            directional_torque=torque,
            operated=operated,
            operating_time_s=response.operating_time_s if operated else None,
            reason=(
                "Overcurrent and directional elements both permit operation."
                if operated
                else "Directional element restrains the overcurrent operation."
            ),
        )


class DistanceProtectionEvaluator:
    """Evaluate phase-ground and phase-phase apparent impedance loops."""

    _LOOPS = (
        (DistanceLoop.AG, 0, None),
        (DistanceLoop.BG, 1, None),
        (DistanceLoop.CG, 2, None),
        (DistanceLoop.AB, 0, 1),
        (DistanceLoop.BC, 1, 2),
        (DistanceLoop.CA, 2, 0),
    )

    def evaluate(
        self,
        settings: DistanceProtectionSettings,
        measurement: DistanceMeasurement,
    ) -> DistanceOperationResult:
        if not isinstance(settings, DistanceProtectionSettings):
            raise TypeError("settings must be DistanceProtectionSettings.")
        if not isinstance(measurement, DistanceMeasurement):
            raise TypeError("measurement must be DistanceMeasurement.")
        current_scale = settings.current_transformer.ratio
        voltage_scale = settings.voltage_transformer.ratio
        currents = tuple(value / current_scale for value in measurement.phase_currents_primary_a)
        voltages = tuple(value / voltage_scale for value in measurement.phase_voltages_primary_v)
        residual_current = sum(currents)
        loop_results: list[DistanceLoopOperation] = []
        for loop, first, second in self._LOOPS:
            if second is None:
                denominator = (
                    currents[first] + settings.ground_compensation_factor * residual_current
                )
                numerator = voltages[first]
            else:
                denominator = currents[first] - currents[second]
                numerator = voltages[first] - voltages[second]
            if (
                abs(denominator) < settings.minimum_current_secondary_a
                or abs(numerator) < settings.minimum_voltage_secondary_v
            ):
                loop_results.append(DistanceLoopOperation(loop, None, None, None, False))
                continue
            apparent = numerator / denominator
            reached = next(
                (zone for zone in settings.zones if self._inside_zone(zone, apparent)),
                None,
            )
            loop_results.append(
                DistanceLoopOperation(
                    loop=loop,
                    apparent_impedance_secondary_ohm=apparent,
                    reached_zone_number=None if reached is None else reached.zone_number,
                    operating_time_s=None if reached is None else reached.operating_time_s,
                    evaluated=True,
                )
            )
        operated_loops = tuple(
            item for item in loop_results if item.reached_zone_number is not None
        )
        if operated_loops:
            fastest = min(operated_loops, key=lambda item: item.operating_time_s or 0.0)
            fastest_zone = fastest.reached_zone_number
            fastest_time = fastest.operating_time_s
        else:
            fastest_zone = None
            fastest_time = None
        return DistanceOperationResult(
            relay_id=settings.id,
            loops=tuple(loop_results),
            operated=bool(operated_loops),
            fastest_zone_number=fastest_zone,
            operating_time_s=fastest_time,
        )

    @staticmethod
    def _inside_zone(zone, impedance: complex) -> bool:
        if zone.characteristic is DistanceCharacteristic.MHO:
            reach = zone.reach_impedance_secondary_ohm
            assert reach is not None
            return abs(impedance - reach / 2.0) <= abs(reach) / 2.0 + 1e-12
        return (
            zone.resistance_min_ohm - 1e-12 <= impedance.real <= zone.resistance_max_ohm + 1e-12
            and zone.reactance_min_ohm - 1e-12 <= impedance.imag <= zone.reactance_max_ohm + 1e-12
        )


class CurrentTransformerSaturationEvaluator:
    """Steady-state AC CT excitation screen; transient flux simulation is not included."""

    def evaluate(
        self,
        model: CurrentTransformerPerformanceModel,
        primary_fault_current_a: float,
        *,
        system_frequency_hz: float,
    ) -> CTSaturationAssessment:
        if not isinstance(model, CurrentTransformerPerformanceModel):
            raise TypeError("model must be a CurrentTransformerPerformanceModel.")
        if isinstance(primary_fault_current_a, bool) or not isinstance(
            primary_fault_current_a, (int, float)
        ):
            raise TypeError("primary_fault_current_a must be a real number.")
        if isinstance(system_frequency_hz, bool) or not isinstance(
            system_frequency_hz, (int, float)
        ):
            raise TypeError("system_frequency_hz must be a real number.")
        current = float(primary_fault_current_a)
        frequency = float(system_frequency_hz)
        if not math.isfinite(current) or current < 0.0:
            raise ValueError("primary_fault_current_a must be finite and non-negative.")
        if not math.isfinite(frequency) or frequency <= 0.0:
            raise ValueError("system_frequency_hz must be finite and positive.")
        diagnostics = [
            (
                "Transient DC-offset, remanence and flux integration are not evaluated "
                "by this AC screen."
            )
        ]
        if not math.isclose(frequency, model.rated_frequency_hz, rel_tol=1e-6, abs_tol=1e-6):
            return CTSaturationAssessment(
                transformer_id=model.id,
                status=ProtectionAssessmentStatus.NOT_EVALUATED,
                required_secondary_voltage_v=0.0,
                knee_point_voltage_v=model.knee_point_voltage_v,
                voltage_margin_v=model.knee_point_voltage_v,
                exciting_current_a=None,
                diagnostics=tuple(
                    diagnostics + ["System frequency does not match CT rated frequency."]
                ),
            )
        secondary_current = model.current_transformer.to_secondary(current)
        required_voltage = abs(
            secondary_current
            * (model.secondary_winding_resistance_ohm + model.burden_impedance_ohm)
        )
        margin = model.knee_point_voltage_v - required_voltage
        status = (
            ProtectionAssessmentStatus.PASS if margin >= -1e-12 else ProtectionAssessmentStatus.FAIL
        )
        exciting_current = self._interpolate_excitation(model.excitation_curve, required_voltage)
        if exciting_current is None:
            diagnostics.append(
                "Required voltage lies outside the supplied excitation-curve range; "
                "exciting current was not extrapolated."
            )
        return CTSaturationAssessment(
            transformer_id=model.id,
            status=status,
            required_secondary_voltage_v=required_voltage,
            knee_point_voltage_v=model.knee_point_voltage_v,
            voltage_margin_v=margin,
            exciting_current_a=exciting_current,
            diagnostics=tuple(diagnostics),
        )

    @staticmethod
    def _interpolate_excitation(
        curve: Sequence[CTExcitationPoint], voltage_v: float
    ) -> float | None:
        if voltage_v <= 0.0:
            return 0.0
        if voltage_v < curve[0].voltage_v or voltage_v > curve[-1].voltage_v:
            return None
        for left, right in pairwise(curve):
            if math.isclose(voltage_v, left.voltage_v, rel_tol=1e-12, abs_tol=1e-12):
                return left.exciting_current_a
            if left.voltage_v < voltage_v <= right.voltage_v:
                fraction = math.log(voltage_v / left.voltage_v) / math.log(
                    right.voltage_v / left.voltage_v
                )
                return math.exp(
                    math.log(left.exciting_current_a)
                    + fraction * math.log(right.exciting_current_a / left.exciting_current_a)
                )
        return curve[-1].exciting_current_a
