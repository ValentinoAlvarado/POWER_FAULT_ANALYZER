"""IEC 60909 study case and immutable calculation result contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from power_fault_analyzer.domain.enums.iec60909 import (
    IEC60909CurrentCase,
    IEC60909LowVoltageTolerance,
)
from power_fault_analyzer.domain.value_objects.diagnostic import DomainDiagnostic
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult

if TYPE_CHECKING:
    from power_fault_analyzer.network.sequence_networks.models import SequenceNetworkSet


@dataclass(frozen=True, slots=True)
class IEC60909StudySpecification:
    """Declared IEC 60909 maximum/minimum case and data for network-feeder studies.

    For minimum-current studies, ``minimum_line_resistance_factor`` is the ratio
    R(theta_end) / R(input) for positive- and negative-sequence line resistance.
    Zero-sequence line resistance uses its own optional factor because earth-return
    and mutual terms need not follow the phase-conductor temperature ratio.
    ``network_feeder_impedance_multiplier`` scales the declared external-grid
    Thevenin impedance to represent the selected utility short-circuit level.
    ``first_pole_contact_separation_time_s`` enables a restricted supplementary
    R/X waveform estimate. It does not establish a normative Clause 10 result.
    """

    current_case: IEC60909CurrentCase
    fault_duration_s: float
    frequency_hz: float
    low_voltage_tolerance: IEC60909LowVoltageTolerance = IEC60909LowVoltageTolerance.PERCENT_10
    minimum_line_resistance_factor: float | None = None
    minimum_zero_sequence_line_resistance_factor: float | None = None
    network_feeder_impedance_multiplier: float = 1.0
    equipment_max_voltage_kv: float | None = None
    first_pole_contact_separation_time_s: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.current_case, IEC60909CurrentCase):
            raise TypeError("current_case must be an IEC60909CurrentCase value.")
        if not isinstance(self.low_voltage_tolerance, IEC60909LowVoltageTolerance):
            raise TypeError("low_voltage_tolerance must be an IEC60909LowVoltageTolerance value.")
        duration = _positive_real(self.fault_duration_s, "fault_duration_s")
        frequency = _positive_real(self.frequency_hz, "frequency_hz")
        if frequency not in (50.0, 60.0):
            raise ValueError("IEC 60909 frequency_hz must be 50 Hz or 60 Hz.")
        multiplier = _positive_real(
            self.network_feeder_impedance_multiplier,
            "network_feeder_impedance_multiplier",
        )
        if self.minimum_line_resistance_factor is not None:
            line_factor = _positive_real(
                self.minimum_line_resistance_factor,
                "minimum_line_resistance_factor",
            )
            if line_factor < 1.0:
                raise ValueError("minimum_line_resistance_factor must be at least 1.0.")
            object.__setattr__(self, "minimum_line_resistance_factor", line_factor)
        if self.minimum_zero_sequence_line_resistance_factor is not None:
            zero_factor = _positive_real(
                self.minimum_zero_sequence_line_resistance_factor,
                "minimum_zero_sequence_line_resistance_factor",
            )
            if zero_factor < 1.0:
                raise ValueError(
                    "minimum_zero_sequence_line_resistance_factor must be at least 1.0."
                )
            object.__setattr__(self, "minimum_zero_sequence_line_resistance_factor", zero_factor)
        equipment_limit = self.equipment_max_voltage_kv
        if equipment_limit is not None:
            equipment_limit = _positive_real(equipment_limit, "equipment_max_voltage_kv")
            object.__setattr__(self, "equipment_max_voltage_kv", equipment_limit)
        separation_time = self.first_pole_contact_separation_time_s
        if separation_time is not None:
            separation_time = _positive_real(
                separation_time, "first_pole_contact_separation_time_s"
            )
            object.__setattr__(self, "first_pole_contact_separation_time_s", separation_time)
        object.__setattr__(self, "fault_duration_s", duration)
        object.__setattr__(self, "frequency_hz", frequency)
        object.__setattr__(self, "network_feeder_impedance_multiplier", multiplier)

    def voltage_factor(self, nominal_voltage_kv: float) -> float:
        """Return the selected maximum/minimum Table 1 voltage factor c."""
        values = self._voltage_factors(nominal_voltage_kv)
        factor = values[0] if self.current_case is IEC60909CurrentCase.MAXIMUM else values[1]
        self._validate_equipment_voltage_limit(nominal_voltage_kv, factor)
        return factor

    def maximum_voltage_factor(self, nominal_voltage_kv: float) -> float:
        """Return cmax, also used for transformer correction in minimum studies."""
        return self._voltage_factors(nominal_voltage_kv)[0]

    def _voltage_factors(self, nominal_voltage_kv: float) -> tuple[float, float]:
        voltage = _positive_real(nominal_voltage_kv, "nominal_voltage_kv")
        if 0.1 <= voltage <= 1.0:
            if self.low_voltage_tolerance is IEC60909LowVoltageTolerance.PERCENT_6:
                return 1.05, 0.95
            return 1.10, 0.90
        if 1.0 < voltage <= 420.0:
            return 1.10, 1.00
        raise ValueError(
            "IEC 60909 Table 1 voltage factors are not defined for this nominal voltage."
        )

    def _validate_equipment_voltage_limit(self, nominal_voltage_kv: float, factor: float) -> None:
        if (
            self.equipment_max_voltage_kv is not None
            and factor * nominal_voltage_kv > self.equipment_max_voltage_kv + 1e-9
        ):
            raise ValueError(
                "The product c * Un exceeds equipment_max_voltage_kv; check the "
                "equipment voltage class and the applicable national rules."
            )


def _nonnegative_real(value: float, name: str) -> float:
    """Validate a finite non-negative quantity, including exact numerical zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number, not bool.")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
    return numeric


def _positive_real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")
    return result


@dataclass(frozen=True, slots=True)
class IEC60909StudyResult:
    """IEC study result with quantity availability, provenance and separate supplements.

    The DC and asymmetrical-current fields store supplementary engineering estimates
    where available; the normative `iDC` and `Ibasym` statuses remain explicit in
    `unavailable_quantity_reasons` unless an applicable IEC strategy is verified.
    """

    standard_edition: str
    base_result: ShortCircuitResult
    current_case: IEC60909CurrentCase
    voltage_factor: float
    equivalent_voltage_pu: complex
    initial_symmetrical_current_ka: float
    peak_current_factor: float | None
    peak_current_ka: float | None
    breaking_current_ka: float | None
    steady_state_current_ka: float | None
    thermal_factor_dc: float | None
    thermal_factor_ac: float | None
    thermal_equivalent_current_ka: float | None
    joule_integral_ka2s: float | None
    fault_duration_s: float
    frequency_hz: float
    applied_transformer_correction_factors: Mapping[str, float]
    diagnostics: tuple[DomainDiagnostic, ...] = ()
    calculation_networks: SequenceNetworkSet | None = None
    current_method_references: Mapping[str, str] = field(default_factory=dict)
    unavailable_quantity_reasons: Mapping[str, str] = field(default_factory=dict)
    first_pole_contact_separation_time_s: float | None = None
    dc_component_at_separation_ka: float | None = None
    asymmetrical_breaking_current_ka: float | None = None

    def __post_init__(self) -> None:
        if self.standard_edition != "IEC 60909-0:2026":
            raise ValueError("standard_edition must identify IEC 60909-0:2026.")
        if not isinstance(self.base_result, ShortCircuitResult):
            raise TypeError("base_result must be a ShortCircuitResult value.")
        if not isinstance(self.current_case, IEC60909CurrentCase):
            raise TypeError("current_case must be an IEC60909CurrentCase value.")
        for name in (
            "voltage_factor",
            "initial_symmetrical_current_ka",
            "fault_duration_s",
            "frequency_hz",
        ):
            value = _positive_real(getattr(self, name), name)
            object.__setattr__(self, name, value)
        equivalent = complex(self.equivalent_voltage_pu)
        if not math.isfinite(equivalent.real) or not math.isfinite(equivalent.imag):
            raise ValueError("equivalent_voltage_pu must be finite.")
        object.__setattr__(self, "equivalent_voltage_pu", equivalent)
        separation_time = self.first_pole_contact_separation_time_s
        if separation_time is not None:
            separation_time = _positive_real(
                separation_time, "first_pole_contact_separation_time_s"
            )
            object.__setattr__(self, "first_pole_contact_separation_time_s", separation_time)
        for name in (
            "breaking_current_ka",
            "steady_state_current_ka",
            "asymmetrical_breaking_current_ka",
        ):
            value = getattr(self, name)
            if value is not None:
                numeric = _positive_real(value, name)
                object.__setattr__(self, name, numeric)
        if self.dc_component_at_separation_ka is not None:
            numeric_dc = _nonnegative_real(
                self.dc_component_at_separation_ka, "dc_component_at_separation_ka"
            )
            object.__setattr__(self, "dc_component_at_separation_ka", numeric_dc)
        for name in (
            "peak_current_factor",
            "peak_current_ka",
            "thermal_factor_dc",
            "thermal_factor_ac",
            "thermal_equivalent_current_ka",
            "joule_integral_ka2s",
        ):
            value = getattr(self, name)
            if value is not None:
                numeric = _positive_real(value, name)
                object.__setattr__(self, name, numeric)
        if not isinstance(self.applied_transformer_correction_factors, Mapping):
            raise TypeError("applied_transformer_correction_factors must be a mapping.")
        factors: dict[str, float] = {}
        for key, value in self.applied_transformer_correction_factors.items():
            if not isinstance(key, str) or not key.strip():
                raise TypeError("Transformer correction keys must be non-empty strings.")
            factors[key] = _positive_real(value, "transformer correction factor")
        object.__setattr__(
            self, "applied_transformer_correction_factors", MappingProxyType(factors)
        )
        if self.calculation_networks is not None and not all(
            hasattr(self.calculation_networks, attribute)
            for attribute in ("positive", "negative", "zero", "network_id")
        ):
            raise TypeError("calculation_networks must be a sequence network set or None.")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of DomainDiagnostic values.")
        for field_name in ("current_method_references", "unavailable_quantity_reasons"):
            values = getattr(self, field_name)
            if not isinstance(values, Mapping):
                raise TypeError(f"{field_name} must be a mapping.")
            normalized: dict[str, str] = {}
            for quantity, reference in values.items():
                if not isinstance(quantity, str) or not quantity.strip():
                    raise ValueError(f"{field_name} keys must be non-empty strings.")
                if not isinstance(reference, str) or not reference.strip():
                    raise ValueError(f"{field_name} values must be non-empty strings.")
                normalized[quantity.strip()] = reference.strip()
            object.__setattr__(self, field_name, MappingProxyType(normalized))
        if set(self.current_method_references).intersection(self.unavailable_quantity_reasons):
            raise ValueError("A quantity cannot be both calculated and unavailable.")
