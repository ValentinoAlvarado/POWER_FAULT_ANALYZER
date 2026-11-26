"""Analytical tests for the supplementary single-Thevenin R-L waveform model."""

from __future__ import annotations

import math

import pytest

from power_fault_analyzer.infrastructure.numerical.short_circuit_waveform import (
    TheveninRLWaveformCalculator,
)


def test_worst_case_inception_returns_maximum_dc_offset_and_asymmetrical_rms():
    result = TheveninRLWaveformCalculator().calculate(
        initial_symmetrical_current_ka=10.0,
        thevenin_impedance_ohm=0.1 + 1.0j,
        frequency_hz=50.0,
        first_pole_contact_separation_time_s=0.02,
    )

    expected_tau = 1.0 / (2.0 * math.pi * 50.0 * 0.1)
    expected_decay = math.exp(-0.02 / expected_tau)
    expected_dc = -math.sqrt(2.0) * 10.0 * expected_decay

    assert result.time_constant_s == pytest.approx(expected_tau)
    assert result.dc_decay_factor == pytest.approx(expected_decay)
    assert result.dc_component_at_separation_ka == pytest.approx(expected_dc)
    assert result.asymmetrical_breaking_current_rms_ka == pytest.approx(
        math.hypot(10.0, expected_dc)
    )
    assert result.is_iec_60909_result is False


def test_fault_inception_angle_at_impedance_angle_has_no_initial_dc_offset():
    impedance = 0.2 + 1.4j
    impedance_angle = math.atan2(impedance.imag, impedance.real)

    result = TheveninRLWaveformCalculator().calculate(
        initial_symmetrical_current_ka=5.0,
        thevenin_impedance_ohm=impedance,
        frequency_hz=60.0,
        first_pole_contact_separation_time_s=0.03,
        fault_inception_angle_rad=impedance_angle,
    )

    assert result.dc_component_at_separation_ka == pytest.approx(0.0, abs=1e-12)
    assert result.asymmetrical_breaking_current_rms_ka == pytest.approx(5.0)


def test_instantaneous_current_is_zero_at_fault_inception():
    result = TheveninRLWaveformCalculator().calculate(
        initial_symmetrical_current_ka=8.0,
        thevenin_impedance_ohm=0.15 + 0.8j,
        frequency_hz=50.0,
        first_pole_contact_separation_time_s=0.04,
    )

    assert result.instantaneous_current_ka(0.0) == pytest.approx(0.0, abs=1e-12)


def test_instantaneous_current_contains_ac_and_decaying_dc_components():
    result = TheveninRLWaveformCalculator().calculate(
        initial_symmetrical_current_ka=8.0,
        thevenin_impedance_ohm=0.15 + 0.8j,
        frequency_hz=50.0,
        first_pole_contact_separation_time_s=0.04,
    )

    sample_time = 0.005
    phase_offset = result.fault_inception_angle_rad - result.impedance_angle_rad
    decay = math.exp(-sample_time / result.time_constant_s)
    expected = (
        math.sqrt(2.0)
        * 8.0
        * (
            math.sin(2.0 * math.pi * 50.0 * sample_time + phase_offset)
            - math.sin(phase_offset) * decay
        )
    )
    assert result.instantaneous_current_ka(sample_time) == pytest.approx(expected)


def test_zero_resistance_has_non_decaying_dc_component():
    result = TheveninRLWaveformCalculator().calculate(
        initial_symmetrical_current_ka=4.0,
        thevenin_impedance_ohm=0.0 + 1.0j,
        frequency_hz=60.0,
        first_pole_contact_separation_time_s=0.1,
    )

    assert result.time_constant_s is None
    assert result.dc_decay_factor == pytest.approx(1.0)
    assert abs(result.dc_component_at_separation_ka) == pytest.approx(4.0 * math.sqrt(2.0))


@pytest.mark.parametrize(
    ("arguments", "error_type"),
    [
        ({"initial_symmetrical_current_ka": 0.0}, ValueError),
        ({"initial_symmetrical_current_ka": -1.0}, ValueError),
        ({"frequency_hz": 0.0}, ValueError),
        ({"first_pole_contact_separation_time_s": -0.1}, ValueError),
        ({"thevenin_impedance_ohm": -0.1 + 1.0j}, ValueError),
        ({"thevenin_impedance_ohm": 0.1 - 1.0j}, ValueError),
        ({"fault_inception_angle_rad": math.inf}, ValueError),
    ],
)
def test_invalid_inputs_are_rejected(arguments, error_type):
    parameters = {
        "initial_symmetrical_current_ka": 10.0,
        "thevenin_impedance_ohm": 0.1 + 1.0j,
        "frequency_hz": 50.0,
        "first_pole_contact_separation_time_s": 0.02,
    }
    parameters.update(arguments)

    with pytest.raises(error_type):
        TheveninRLWaveformCalculator().calculate(**parameters)


def test_negative_waveform_time_is_rejected():
    result = TheveninRLWaveformCalculator().calculate(
        initial_symmetrical_current_ka=5.0,
        thevenin_impedance_ohm=0.1 + 1.0j,
        frequency_hz=50.0,
        first_pole_contact_separation_time_s=0.02,
    )

    with pytest.raises(ValueError, match="time_s"):
        result.instantaneous_current_ka(-0.001)
