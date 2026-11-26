"""Immutable inputs and time-domain results for transient CT and relay studies."""

from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID

from power_fault_analyzer.domain.enums.protection import (
    ProtectionAssessmentStatus,
    ProtectionStage,
)


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def _non_negative(value: float, name: str) -> float:
    result = _finite(value, name)
    if result < 0.0:
        raise ValueError(f"{name} cannot be negative.")
    return result


def _positive(value: float, name: str) -> float:
    result = _finite(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive.")
    return result


def _unit_interval(value: float, name: str) -> float:
    result = _finite(value, name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1.")
    return result


@dataclass(frozen=True, slots=True)
class CTTransientSimulationSettings:
    """Single-phase CT transient excitation and fault-current conditions.

    ``dc_offset_initial_pu`` is the signed DC component at t=0 relative to the
    peak symmetrical AC component. ``remanent_flux_pu`` is the initial flux
    linkage relative to the CT knee-point flux linkage.
    """

    primary_current_rms_a: float
    system_frequency_hz: float
    duration_s: float
    time_step_s: float
    dc_offset_initial_pu: float = 0.0
    dc_time_constant_s: float = 0.04
    inception_angle_rad: float = 0.0
    remanent_flux_pu: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "primary_current_rms_a",
            _non_negative(self.primary_current_rms_a, "primary_current_rms_a"),
        )
        object.__setattr__(
            self,
            "system_frequency_hz",
            _positive(self.system_frequency_hz, "system_frequency_hz"),
        )
        object.__setattr__(self, "duration_s", _positive(self.duration_s, "duration_s"))
        object.__setattr__(self, "time_step_s", _positive(self.time_step_s, "time_step_s"))
        object.__setattr__(
            self,
            "dc_offset_initial_pu",
            _finite(self.dc_offset_initial_pu, "dc_offset_initial_pu"),
        )
        object.__setattr__(
            self,
            "dc_time_constant_s",
            _positive(self.dc_time_constant_s, "dc_time_constant_s"),
        )
        object.__setattr__(
            self, "inception_angle_rad", _finite(self.inception_angle_rad, "inception_angle_rad")
        )
        remanence = _finite(self.remanent_flux_pu, "remanent_flux_pu")
        if abs(remanence) > 1.0:
            raise ValueError("remanent_flux_pu magnitude cannot exceed 1.0 knee-point pu.")
        object.__setattr__(self, "remanent_flux_pu", remanence)


@dataclass(frozen=True, slots=True)
class CTTransientSample:
    time_s: float
    primary_current_a: float
    ideal_secondary_current_a: float
    exciting_current_a: float
    secondary_current_a: float
    secondary_voltage_v: float
    flux_linkage_v_s: float
    flux_pu: float
    saturated: bool

    def __post_init__(self) -> None:
        for name in (
            "time_s",
            "primary_current_a",
            "ideal_secondary_current_a",
            "exciting_current_a",
            "secondary_current_a",
            "secondary_voltage_v",
            "flux_linkage_v_s",
            "flux_pu",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.time_s < 0.0:
            raise ValueError("time_s cannot be negative.")
        if not isinstance(self.saturated, bool):
            raise TypeError("saturated must be bool.")


@dataclass(frozen=True, slots=True)
class CTTransientSimulationResult:
    current_transformer_id: UUID
    current_transformer_ratio: float
    settings: CTTransientSimulationSettings
    status: ProtectionAssessmentStatus
    samples: tuple[CTTransientSample, ...]
    knee_point_flux_linkage_v_s: float
    peak_flux_pu: float
    saturation_fraction: float
    ideal_secondary_rms_current_a: float
    secondary_rms_current_a: float
    current_transfer_error_ratio: float
    excitation_curve_exceeded: bool
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.current_transformer_id, UUID):
            raise TypeError("current_transformer_id must be a UUID.")
        object.__setattr__(
            self,
            "current_transformer_ratio",
            _positive(self.current_transformer_ratio, "current_transformer_ratio"),
        )
        if not isinstance(self.settings, CTTransientSimulationSettings):
            raise TypeError("settings must be CTTransientSimulationSettings.")
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")
        if not isinstance(self.samples, tuple) or any(
            not isinstance(item, CTTransientSample) for item in self.samples
        ):
            raise TypeError("samples must be a tuple of CTTransientSample values.")
        if len(self.samples) < 2:
            raise ValueError("At least two CT transient samples are required.")
        for name in (
            "knee_point_flux_linkage_v_s",
            "peak_flux_pu",
            "saturation_fraction",
            "ideal_secondary_rms_current_a",
            "secondary_rms_current_a",
            "current_transfer_error_ratio",
        ):
            object.__setattr__(self, name, _non_negative(getattr(self, name), name))
        if self.saturation_fraction > 1.0:
            raise ValueError("saturation_fraction cannot exceed 1.0.")
        if not isinstance(self.excitation_curve_exceeded, bool):
            raise TypeError("excitation_curve_exceeded must be bool.")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, str) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of strings.")


@dataclass(frozen=True, slots=True)
class RelayCurrentSample:
    """One secondary-side instantaneous current sample presented to a relay."""

    time_s: float
    secondary_current_a: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "time_s", _non_negative(self.time_s, "time_s"))
        object.__setattr__(
            self,
            "secondary_current_a",
            _finite(self.secondary_current_a, "secondary_current_a"),
        )


@dataclass(frozen=True, slots=True)
class RelayTransientSettings:
    """Numerical relay sampling, RMS window, reset and output-delay settings."""

    system_frequency_hz: float
    rms_window_cycles: float = 1.0
    reset_ratio: float = 0.95
    reset_time_constant_s: float = 0.5
    output_delay_s: float = 0.0
    initial_inverse_timer_fraction: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_frequency_hz",
            _positive(self.system_frequency_hz, "system_frequency_hz"),
        )
        object.__setattr__(
            self, "rms_window_cycles", _positive(self.rms_window_cycles, "rms_window_cycles")
        )
        ratio = _positive(self.reset_ratio, "reset_ratio")
        if ratio >= 1.0:
            raise ValueError("reset_ratio must be less than 1.0.")
        object.__setattr__(self, "reset_ratio", ratio)
        object.__setattr__(
            self,
            "reset_time_constant_s",
            _positive(self.reset_time_constant_s, "reset_time_constant_s"),
        )
        object.__setattr__(
            self, "output_delay_s", _non_negative(self.output_delay_s, "output_delay_s")
        )
        object.__setattr__(
            self,
            "initial_inverse_timer_fraction",
            _unit_interval(self.initial_inverse_timer_fraction, "initial_inverse_timer_fraction"),
        )


@dataclass(frozen=True, slots=True)
class RelayTransientSample:
    time_s: float
    measured_secondary_rms_a: float | None
    pickup_multiple: float | None
    inverse_timer_fraction: float
    instantaneous_elapsed_s: float
    selected_stage: ProtectionStage | None
    tripped: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "time_s", _non_negative(self.time_s, "time_s"))
        for name in ("measured_secondary_rms_a", "pickup_multiple"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_negative(value, name))
        object.__setattr__(
            self,
            "inverse_timer_fraction",
            _unit_interval(self.inverse_timer_fraction, "inverse_timer_fraction"),
        )
        object.__setattr__(
            self,
            "instantaneous_elapsed_s",
            _non_negative(self.instantaneous_elapsed_s, "instantaneous_elapsed_s"),
        )
        if self.selected_stage is not None and not isinstance(self.selected_stage, ProtectionStage):
            raise TypeError("selected_stage must be a ProtectionStage or None.")
        if not isinstance(self.tripped, bool):
            raise TypeError("tripped must be bool.")


@dataclass(frozen=True, slots=True)
class RelayTransientResult:
    relay_id: UUID
    settings: RelayTransientSettings
    status: ProtectionAssessmentStatus
    operated: bool
    trip_stage: ProtectionStage | None
    trip_command_time_s: float | None
    trip_output_time_s: float | None
    maximum_inverse_timer_fraction: float
    samples: tuple[RelayTransientSample, ...]
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.relay_id, UUID):
            raise TypeError("relay_id must be a UUID.")
        if not isinstance(self.settings, RelayTransientSettings):
            raise TypeError("settings must be RelayTransientSettings.")
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")
        if not isinstance(self.operated, bool):
            raise TypeError("operated must be bool.")
        if self.trip_stage is not None and not isinstance(self.trip_stage, ProtectionStage):
            raise TypeError("trip_stage must be a ProtectionStage or None.")
        if self.operated != (self.trip_command_time_s is not None):
            raise ValueError("operated must agree with trip_command_time_s.")
        if self.operated != (self.trip_stage is not None):
            raise ValueError("operated must agree with trip_stage.")
        for name in ("trip_command_time_s", "trip_output_time_s"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_negative(value, name))
        if self.operated != (self.trip_output_time_s is not None):
            raise ValueError("operated must agree with trip_output_time_s.")
        object.__setattr__(
            self,
            "maximum_inverse_timer_fraction",
            _unit_interval(self.maximum_inverse_timer_fraction, "maximum_inverse_timer_fraction"),
        )
        if not isinstance(self.samples, tuple) or any(
            not isinstance(item, RelayTransientSample) for item in self.samples
        ):
            raise TypeError("samples must be a tuple of RelayTransientSample values.")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, str) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of strings.")


@dataclass(frozen=True, slots=True)
class ThreePhaseCurrentSample:
    time_s: float
    phase_currents_a: tuple[float, float, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "time_s", _non_negative(self.time_s, "time_s"))
        if not isinstance(self.phase_currents_a, tuple) or len(self.phase_currents_a) != 3:
            raise TypeError("phase_currents_a must contain exactly three phase currents.")
        object.__setattr__(
            self,
            "phase_currents_a",
            tuple(_finite(value, "phase current") for value in self.phase_currents_a),
        )


@dataclass(frozen=True, slots=True)
class BreakerTransientSettings:
    """Per-pole scatter and allowed arc window for ideal current-zero interruption."""

    pole_scatter_s_by_phase: tuple[float, float, float] = (0.0, 0.0, 0.0)
    maximum_arc_duration_s: float = 0.03

    def __post_init__(self) -> None:
        if (
            not isinstance(self.pole_scatter_s_by_phase, tuple)
            or len(self.pole_scatter_s_by_phase) != 3
        ):
            raise TypeError("pole_scatter_s_by_phase must contain three values.")
        object.__setattr__(
            self,
            "pole_scatter_s_by_phase",
            tuple(_non_negative(value, "pole scatter") for value in self.pole_scatter_s_by_phase),
        )
        object.__setattr__(
            self,
            "maximum_arc_duration_s",
            _positive(self.maximum_arc_duration_s, "maximum_arc_duration_s"),
        )


@dataclass(frozen=True, slots=True)
class BreakerPoleInterruption:
    phase: str
    contact_separation_time_s: float
    current_at_contact_separation_a: float | None
    current_zero_time_s: float | None
    interrupted: bool
    arcing_duration_s: float | None
    within_rated_arcing_time: bool | None

    def __post_init__(self) -> None:
        if self.phase not in ("A", "B", "C"):
            raise ValueError("phase must be A, B or C.")
        object.__setattr__(
            self,
            "contact_separation_time_s",
            _non_negative(self.contact_separation_time_s, "contact_separation_time_s"),
        )
        for name in ("current_at_contact_separation_a", "current_zero_time_s"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite(value, name))
        if not isinstance(self.interrupted, bool):
            raise TypeError("interrupted must be bool.")
        if self.interrupted != (self.current_zero_time_s is not None):
            raise ValueError("interrupted must agree with current_zero_time_s.")
        if self.arcing_duration_s is not None:
            object.__setattr__(
                self,
                "arcing_duration_s",
                _non_negative(self.arcing_duration_s, "arcing_duration_s"),
            )
        if self.interrupted != (self.arcing_duration_s is not None):
            raise ValueError("interrupted must agree with arcing_duration_s.")
        if self.interrupted != isinstance(self.within_rated_arcing_time, bool):
            raise ValueError("within_rated_arcing_time must be bool exactly when interrupted.")


@dataclass(frozen=True, slots=True)
class BreakerTransientResult:
    breaker_id: UUID
    settings: BreakerTransientSettings
    status: ProtectionAssessmentStatus
    relay_trip_command_time_s: float
    poles: tuple[BreakerPoleInterruption, BreakerPoleInterruption, BreakerPoleInterruption]
    total_clearing_time_s: float | None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.breaker_id, UUID):
            raise TypeError("breaker_id must be a UUID.")
        if not isinstance(self.settings, BreakerTransientSettings):
            raise TypeError("settings must be BreakerTransientSettings.")
        if not isinstance(self.status, ProtectionAssessmentStatus):
            raise TypeError("status must be a ProtectionAssessmentStatus.")
        object.__setattr__(
            self,
            "relay_trip_command_time_s",
            _non_negative(self.relay_trip_command_time_s, "relay_trip_command_time_s"),
        )
        if (
            not isinstance(self.poles, tuple)
            or len(self.poles) != 3
            or any(not isinstance(item, BreakerPoleInterruption) for item in self.poles)
        ):
            raise TypeError("poles must contain exactly three BreakerPoleInterruption values.")
        if self.total_clearing_time_s is not None:
            object.__setattr__(
                self,
                "total_clearing_time_s",
                _non_negative(self.total_clearing_time_s, "total_clearing_time_s"),
            )
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, str) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of strings.")
