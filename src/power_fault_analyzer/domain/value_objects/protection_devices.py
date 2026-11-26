"""Immutable protective-device settings and manufacturer-curve data."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from power_fault_analyzer.domain.enums.protection import (
    CircuitBreakerStandard,
    IECInverseCurveType,
    ProtectionFunction,
    ProtectionStage,
)


def _positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")
    return result


def _non_negative(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number, not bool.")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
    return result


@dataclass(frozen=True, slots=True)
class CurrentTransformerRatio:
    """CT primary/secondary rated-current ratio used by a numerical relay."""

    primary_rated_current_a: float
    secondary_rated_current_a: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "primary_rated_current_a",
            _positive(self.primary_rated_current_a, "primary_rated_current_a"),
        )
        object.__setattr__(
            self,
            "secondary_rated_current_a",
            _positive(self.secondary_rated_current_a, "secondary_rated_current_a"),
        )

    @property
    def ratio(self) -> float:
        return self.primary_rated_current_a / self.secondary_rated_current_a

    def to_secondary(self, primary_current_a: float) -> float:
        current = _non_negative(primary_current_a, "primary_current_a")
        return current / self.ratio

    def to_primary(self, secondary_current_a: float) -> float:
        current = _non_negative(secondary_current_a, "secondary_current_a")
        return current * self.ratio


@dataclass(frozen=True, slots=True)
class RelayOperatingPoint:
    """Calculated relay response at one primary current."""

    relay_id: UUID
    measured_primary_current_a: float
    measured_secondary_current_a: float
    pickup_multiple: float
    stage: ProtectionStage | None
    operating_time_s: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.relay_id, UUID):
            raise TypeError("relay_id must be a UUID.")
        for name in (
            "measured_primary_current_a",
            "measured_secondary_current_a",
            "pickup_multiple",
        ):
            value = _non_negative(getattr(self, name), name)
            object.__setattr__(self, name, value)
        if self.stage is not None and not isinstance(self.stage, ProtectionStage):
            raise TypeError("stage must be a ProtectionStage or None.")
        if self.operating_time_s is not None:
            value = _non_negative(self.operating_time_s, "operating_time_s")
            object.__setattr__(self, "operating_time_s", value)
        if (self.stage is None) != (self.operating_time_s is None):
            raise ValueError("stage and operating_time_s must either both be set or both be None.")

    @property
    def picked_up(self) -> bool:
        return self.stage is not None


@dataclass(frozen=True, slots=True)
class OvercurrentRelay:
    """IEC 60255 inverse-time 51 element with optional instantaneous 50 stage.

    Settings are expressed on the relay's CT secondary side. Current passed to
    ``operate`` is primary amperes. Manufacturer tolerances, reset curves and
    directional/polarizing logic are outside this ideal characteristic model.
    """

    id: UUID
    name: str
    current_transformer: CurrentTransformerRatio
    function: ProtectionFunction
    pickup_secondary_a: float
    curve_type: IECInverseCurveType
    time_multiplier: float = 1.0
    instantaneous_pickup_secondary_a: float | None = None
    instantaneous_delay_s: float = 0.0

    _CURVE_CONSTANTS: ClassVar[dict[IECInverseCurveType, tuple[float, float]]] = {
        IECInverseCurveType.STANDARD_INVERSE: (0.14, 0.02),
        IECInverseCurveType.VERY_INVERSE: (13.5, 1.0),
        IECInverseCurveType.EXTREMELY_INVERSE: (80.0, 2.0),
        IECInverseCurveType.LONG_TIME_INVERSE: (120.0, 1.0),
    }

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name cannot be empty.")
        if not isinstance(self.current_transformer, CurrentTransformerRatio):
            raise TypeError("current_transformer must be a CurrentTransformerRatio.")
        if not isinstance(self.function, ProtectionFunction):
            raise TypeError("function must be a ProtectionFunction.")
        if not isinstance(self.curve_type, IECInverseCurveType):
            raise TypeError("curve_type must be an IECInverseCurveType.")
        object.__setattr__(
            self, "pickup_secondary_a", _positive(self.pickup_secondary_a, "pickup_secondary_a")
        )
        object.__setattr__(
            self, "time_multiplier", _positive(self.time_multiplier, "time_multiplier")
        )
        object.__setattr__(
            self,
            "instantaneous_delay_s",
            _non_negative(self.instantaneous_delay_s, "instantaneous_delay_s"),
        )
        if self.instantaneous_pickup_secondary_a is not None:
            pickup = _positive(
                self.instantaneous_pickup_secondary_a, "instantaneous_pickup_secondary_a"
            )
            if pickup <= self.pickup_secondary_a:
                raise ValueError("Instantaneous pickup must exceed the 51 pickup setting.")
            object.__setattr__(self, "instantaneous_pickup_secondary_a", pickup)

    @property
    def pickup_primary_a(self) -> float:
        return self.current_transformer.to_primary(self.pickup_secondary_a)

    def operate(self, primary_current_a: float) -> RelayOperatingPoint:
        current_primary = _non_negative(primary_current_a, "primary_current_a")
        current_secondary = self.current_transformer.to_secondary(current_primary)
        multiple = current_secondary / self.pickup_secondary_a
        stage: ProtectionStage | None = None
        operating_time: float | None = None

        if (
            self.instantaneous_pickup_secondary_a is not None
            and current_secondary >= self.instantaneous_pickup_secondary_a
        ):
            stage = ProtectionStage.INSTANTANEOUS_50
            operating_time = self.instantaneous_delay_s
            # A zero-delay instantaneous stage is a valid ideal trip time.
        elif multiple > 1.0:
            numerator, exponent = self._CURVE_CONSTANTS[self.curve_type]
            denominator = multiple**exponent - 1.0
            if denominator > 0.0:
                stage = ProtectionStage.TIME_INVERSE_51
                operating_time = self.time_multiplier * numerator / denominator

        return RelayOperatingPoint(
            relay_id=self.id,
            measured_primary_current_a=current_primary,
            measured_secondary_current_a=current_secondary,
            pickup_multiple=multiple,
            stage=stage,
            operating_time_s=operating_time,
        )


@dataclass(frozen=True, slots=True)
class FuseTimeCurrentPoint:
    """Manufacturer-supplied AC fuse current/time point."""

    current_a: float
    pre_arcing_time_s: float
    total_clearing_time_s: float

    def __post_init__(self) -> None:
        for name in ("current_a", "pre_arcing_time_s", "total_clearing_time_s"):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        if self.total_clearing_time_s < self.pre_arcing_time_s:
            raise ValueError("Total clearing time cannot be less than pre-arcing time.")


@dataclass(frozen=True, slots=True)
class FuseLink:
    """Fuse model driven by manufacturer data; no generic fuse curve is invented."""

    id: UUID
    name: str
    rated_current_a: float
    rated_voltage_kv: float
    breaking_capacity_ka: float
    characteristic_points: tuple[FuseTimeCurrentPoint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name cannot be empty.")
        for name in ("rated_current_a", "rated_voltage_kv", "breaking_capacity_ka"):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        if not isinstance(self.characteristic_points, tuple) or len(self.characteristic_points) < 2:
            raise TypeError("characteristic_points must contain at least two points in a tuple.")
        if any(not isinstance(item, FuseTimeCurrentPoint) for item in self.characteristic_points):
            raise TypeError("Every characteristic point must be a FuseTimeCurrentPoint.")
        currents = tuple(item.current_a for item in self.characteristic_points)
        if any(right <= left for left, right in itertools.pairwise(currents)):
            raise ValueError("Fuse current points must be strictly increasing.")
        pre_arcing = tuple(item.pre_arcing_time_s for item in self.characteristic_points)
        total = tuple(item.total_clearing_time_s for item in self.characteristic_points)
        if any(right > left for left, right in itertools.pairwise(pre_arcing)):
            raise ValueError("Fuse pre-arcing time must not increase with current.")
        if any(right > left for left, right in itertools.pairwise(total)):
            raise ValueError("Fuse total clearing time must not increase with current.")

    @property
    def current_range_a(self) -> tuple[float, float]:
        return self.characteristic_points[0].current_a, self.characteristic_points[-1].current_a

    def pre_arcing_time(self, current_a: float) -> float | None:
        return self._interpolate(current_a, "pre_arcing_time_s")

    def total_clearing_time(self, current_a: float) -> float | None:
        return self._interpolate(current_a, "total_clearing_time_s")

    def _interpolate(self, current_a: float, time_attribute: str) -> float | None:
        current = _positive(current_a, "current_a")
        points = self.characteristic_points
        if current < points[0].current_a or current > points[-1].current_a:
            return None
        for point in points:
            if math.isclose(current, point.current_a, rel_tol=1e-12, abs_tol=1e-12):
                return getattr(point, time_attribute)
        for left, right in itertools.pairwise(points):
            if left.current_a < current < right.current_a:
                x1, x2 = math.log(left.current_a), math.log(right.current_a)
                y1 = math.log(getattr(left, time_attribute))
                y2 = math.log(getattr(right, time_attribute))
                fraction = (math.log(current) - x1) / (x2 - x1)
                return math.exp(y1 + fraction * (y2 - y1))
        return None


@dataclass(frozen=True, slots=True)
class CircuitBreaker:
    """Three-phase AC circuit-breaker ratings for LV or MV/HV standards.

    IEC 60947-2 applies to the low-voltage rating set (up to 1 kV AC), while
    IEC 62271-100 applies above 1 kV AC. The corresponding breaking-current
    fields are deliberately distinct to prevent mixing Icu/Ics with the
    high-voltage rated short-circuit breaking current. This model covers the
    standard-specific nameplate duties; it does not model TRV or pole scatter.
    """

    id: UUID
    name: str
    rated_voltage_kv: float
    rated_current_a: float
    standard: CircuitBreakerStandard
    ultimate_breaking_capacity_ka: float | None = None
    service_breaking_capacity_ka: float | None = None
    rated_short_circuit_breaking_current_ka: float | None = None
    making_capacity_peak_ka: float | None = None
    short_time_withstand_current_ka: float | None = None
    short_time_withstand_duration_s: float | None = None
    opening_time_s: float = 0.05
    arcing_time_s: float = 0.02

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name cannot be empty.")
        for name in ("rated_voltage_kv", "rated_current_a"):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        if not isinstance(self.standard, CircuitBreakerStandard):
            raise TypeError("standard must be a CircuitBreakerStandard.")
        for name in (
            "ultimate_breaking_capacity_ka",
            "service_breaking_capacity_ka",
            "rated_short_circuit_breaking_current_ka",
            "making_capacity_peak_ka",
            "short_time_withstand_current_ka",
            "short_time_withstand_duration_s",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive(value, name))
        if self.standard is CircuitBreakerStandard.IEC_60947_2:
            if self.rated_voltage_kv > 1.0:
                raise ValueError("IEC 60947-2 rating applies only up to 1 kV AC.")
            if self.ultimate_breaking_capacity_ka is None:
                raise ValueError("IEC 60947-2 breakers require an Icu rating.")
            if self.rated_short_circuit_breaking_current_ka is not None:
                raise ValueError(
                    "Use Icu/Ics fields, not the IEC 62271 rated breaking-current field, "
                    "for IEC 60947-2."
                )
            if (
                self.service_breaking_capacity_ka is not None
                and self.service_breaking_capacity_ka > self.ultimate_breaking_capacity_ka
            ):
                raise ValueError("Ics cannot exceed Icu.")
        else:
            if self.rated_voltage_kv <= 1.0:
                raise ValueError("IEC 62271-100 rating applies to systems above 1 kV AC.")
            if self.rated_short_circuit_breaking_current_ka is None:
                raise ValueError(
                    "IEC 62271-100 breakers require a rated short-circuit breaking current."
                )
            if (
                self.ultimate_breaking_capacity_ka is not None
                or self.service_breaking_capacity_ka is not None
            ):
                raise ValueError("Icu/Ics fields are not used for IEC 62271-100 breakers.")
        if (self.short_time_withstand_current_ka is None) != (
            self.short_time_withstand_duration_s is None
        ):
            raise ValueError("Icw and its rated duration must be provided together.")
        object.__setattr__(
            self, "opening_time_s", _non_negative(self.opening_time_s, "opening_time_s")
        )
        object.__setattr__(
            self, "arcing_time_s", _non_negative(self.arcing_time_s, "arcing_time_s")
        )

    @property
    def rated_breaking_current_ka(self) -> float:
        """Return the standard-appropriate symmetrical AC breaking rating."""
        if self.standard is CircuitBreakerStandard.IEC_60947_2:
            assert self.ultimate_breaking_capacity_ka is not None
            return self.ultimate_breaking_capacity_ka
        assert self.rated_short_circuit_breaking_current_ka is not None
        return self.rated_short_circuit_breaking_current_ka

    @property
    def total_clearing_time_s(self) -> float:
        return self.opening_time_s + self.arcing_time_s


@dataclass(frozen=True, slots=True)
class ConductorThermalLimit:
    """Adiabatic conductor limit with user-declared k and cross-sectional area."""

    cross_section_mm2: float
    k_factor_a_sqrt_s_per_mm2: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "cross_section_mm2", _positive(self.cross_section_mm2, "cross_section_mm2")
        )
        object.__setattr__(
            self,
            "k_factor_a_sqrt_s_per_mm2",
            _positive(self.k_factor_a_sqrt_s_per_mm2, "k_factor_a_sqrt_s_per_mm2"),
        )

    @property
    def withstand_i2t_a2s(self) -> float:
        return (self.k_factor_a_sqrt_s_per_mm2 * self.cross_section_mm2) ** 2
