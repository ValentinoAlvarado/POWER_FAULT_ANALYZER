"""Supplementary single-Thevenin R-L short-circuit waveform model.

This engineering model is intentionally separate from IEC 60909 calculation
policies. It represents a balanced sinusoidal source behind one lumped
Thevenin R-L impedance, with constant symmetrical AC current magnitude and a
single exponentially decaying aperiodic component.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_METHOD_ID = "PFA-ENGINEERING-RL-THEVENIN-DC-001"
_SQRT_TWO = math.sqrt(2.0)


def _finite_real(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a real number.")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite.")
    return numeric_value


@dataclass(frozen=True, slots=True)
class RLShortCircuitWaveformResult:
    """Result of a single-equivalent R-L waveform calculation.

    Currents are in kA, impedance in ohms, time in seconds, frequency in Hz,
    and angles in radians. ``dc_component_at_separation_ka`` is signed; its
    magnitude is used to calculate the asymmetrical RMS value.

    ``fault_inception_angle_rad`` is the source-voltage electrical angle at
    fault inception. When the caller omits it, the calculator selects the
    inception angle that produces the maximum initial aperiodic offset.
    """

    initial_symmetrical_current_ka: float
    thevenin_impedance_ohm: complex
    frequency_hz: float
    first_pole_contact_separation_time_s: float
    fault_inception_angle_rad: float
    impedance_angle_rad: float
    time_constant_s: float | None
    dc_decay_factor: float
    dc_component_at_separation_ka: float
    asymmetrical_breaking_current_rms_ka: float
    method_id: str = _METHOD_ID
    is_iec_60909_result: bool = False

    def instantaneous_current_ka(self, time_s: float) -> float:
        """Return the instantaneous phase current for ``time_s`` after fault inception."""
        time_value = _finite_real(time_s, "time_s")
        if time_value < 0.0:
            raise ValueError("time_s must be greater than or equal to zero.")

        angular_frequency = 2.0 * math.pi * self.frequency_hz
        phase_offset = self.fault_inception_angle_rad - self.impedance_angle_rad
        if self.time_constant_s is None:
            decay = 1.0
        else:
            decay = math.exp(-time_value / self.time_constant_s)

        ac_component = math.sin(angular_frequency * time_value + phase_offset)
        dc_component = math.sin(phase_offset) * decay
        return _SQRT_TWO * self.initial_symmetrical_current_ka * (ac_component - dc_component)


class TheveninRLWaveformCalculator:
    """Calculate DC offset and asymmetrical RMS for one lumped Thevenin R-L source.

    This is a general engineering transient model, not an implementation of
    IEC 60909 Clause 10. It must not be used for source aggregation, rotating
    machine AC decrement, converter controls, sequence-coupled unbalanced
    faults, or meshed-network equivalent-frequency procedures.
    """

    def calculate(
        self,
        *,
        initial_symmetrical_current_ka: float,
        thevenin_impedance_ohm: complex,
        frequency_hz: float,
        first_pole_contact_separation_time_s: float,
        fault_inception_angle_rad: float | None = None,
    ) -> RLShortCircuitWaveformResult:
        current = _finite_real(initial_symmetrical_current_ka, "initial_symmetrical_current_ka")
        frequency = _finite_real(frequency_hz, "frequency_hz")
        separation_time = _finite_real(
            first_pole_contact_separation_time_s,
            "first_pole_contact_separation_time_s",
        )

        if current <= 0.0:
            raise ValueError("initial_symmetrical_current_ka must be greater than zero.")
        if frequency <= 0.0:
            raise ValueError("frequency_hz must be greater than zero.")
        if separation_time < 0.0:
            raise ValueError("first_pole_contact_separation_time_s must be non-negative.")
        if isinstance(thevenin_impedance_ohm, bool) or not isinstance(
            thevenin_impedance_ohm, (int, float, complex)
        ):
            raise TypeError("thevenin_impedance_ohm must be a finite complex number.")

        impedance = complex(thevenin_impedance_ohm)
        resistance = impedance.real
        reactance = impedance.imag
        if not math.isfinite(resistance) or not math.isfinite(reactance):
            raise ValueError("thevenin_impedance_ohm must be finite.")
        if resistance < 0.0:
            raise ValueError("Thevenin resistance must be non-negative.")
        if reactance <= 0.0:
            raise ValueError("Thevenin inductive reactance must be greater than zero.")

        impedance_angle = math.atan2(reactance, resistance)
        if fault_inception_angle_rad is None:
            inception_angle = impedance_angle + math.pi / 2.0
        else:
            inception_angle = _finite_real(
                fault_inception_angle_rad,
                "fault_inception_angle_rad",
            )

        if resistance == 0.0:
            time_constant = None
            decay_factor = 1.0
        else:
            time_constant = reactance / (2.0 * math.pi * frequency * resistance)
            decay_factor = math.exp(-separation_time / time_constant)

        phase_offset = inception_angle - impedance_angle
        dc_initial = -_SQRT_TWO * current * math.sin(phase_offset)
        dc_at_separation = dc_initial * decay_factor
        asymmetrical_rms = math.hypot(current, dc_at_separation)

        return RLShortCircuitWaveformResult(
            initial_symmetrical_current_ka=current,
            thevenin_impedance_ohm=impedance,
            frequency_hz=frequency,
            first_pole_contact_separation_time_s=separation_time,
            fault_inception_angle_rad=inception_angle,
            impedance_angle_rad=impedance_angle,
            time_constant_s=time_constant,
            dc_decay_factor=decay_factor,
            dc_component_at_separation_ka=dc_at_separation,
            asymmetrical_breaking_current_rms_ka=asymmetrical_rms,
        )
