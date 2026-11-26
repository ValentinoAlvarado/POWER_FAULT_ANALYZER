"""Time-current calculations and selective-coordination studies."""

from __future__ import annotations

import math

from power_fault_analyzer.domain.enums.protection import (
    ProtectionAssessmentStatus,
)
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.protection_assessment import (
    CoordinationAssessment,
    CoordinationSample,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    FuseLink,
    OvercurrentRelay,
)


class ProtectionCoordinationError(ValueError):
    """Raised when a coordination study's declared current range is invalid."""


class ProtectionCoordinationAnalyzer:
    """Compare downstream clearing against upstream relay operating time.

    The analyzer evaluates a declared through-fault current range on a logarithmic
    grid. The user supplies the required time interval; no universal selectivity
    margin is assumed because breaker times, relay tolerances and utility rules vary.
    """

    def coordinate_relay_pair(
        self,
        downstream_relay: OvercurrentRelay,
        upstream_relay: OvercurrentRelay,
        *,
        minimum_current_a: float,
        maximum_current_a: float,
        minimum_coordination_interval_s: float,
        downstream_breaker: CircuitBreaker,
        sample_count: int = 101,
    ) -> CoordinationAssessment:
        self._validate_common(
            downstream_relay,
            upstream_relay,
            minimum_current_a,
            maximum_current_a,
            minimum_coordination_interval_s,
            sample_count,
        )
        if not isinstance(downstream_breaker, CircuitBreaker):
            raise TypeError("downstream_breaker must be a CircuitBreaker.")
        return self._evaluate(
            downstream_relay,
            upstream_relay,
            minimum_current_a,
            maximum_current_a,
            minimum_coordination_interval_s,
            sample_count,
            downstream_breaker.total_clearing_time_s,
        )

    def coordinate_fuse_relay(
        self,
        downstream_fuse: FuseLink,
        upstream_relay: OvercurrentRelay,
        *,
        minimum_current_a: float,
        maximum_current_a: float,
        minimum_coordination_interval_s: float,
        sample_count: int = 101,
    ) -> CoordinationAssessment:
        if not isinstance(downstream_fuse, FuseLink):
            raise TypeError("downstream_fuse must be a FuseLink.")
        if not isinstance(upstream_relay, OvercurrentRelay):
            raise TypeError("upstream_relay must be an OvercurrentRelay.")
        self._validate_range(
            minimum_current_a,
            maximum_current_a,
            minimum_coordination_interval_s,
            sample_count,
        )
        fuse_minimum, fuse_maximum = downstream_fuse.current_range_a
        if minimum_current_a < fuse_minimum or maximum_current_a > fuse_maximum:
            raise ProtectionCoordinationError(
                "The requested current range must be fully covered by the manufacturer's "
                "fuse characteristic; extrapolation is intentionally disabled."
            )

        points = self._logarithmic_grid(minimum_current_a, maximum_current_a, sample_count)
        samples: list[CoordinationSample] = []
        diagnostics: list[DomainDiagnostic] = []
        for current in points:
            fuse_time = downstream_fuse.total_clearing_time(current)
            upstream = upstream_relay.operate(current)
            if fuse_time is None:
                raise ProtectionCoordinationError(
                    "Fuse characteristic does not cover a requested current sample."
                )
            if not upstream.picked_up or upstream.operating_time_s is None:
                diagnostics.append(
                    DomainDiagnostic(
                        code="PROTECTION-UPSTREAM-NOT-SENSITIVE",
                        message=(
                            f"Upstream relay '{upstream_relay.name}' does not pick up at "
                            f"{current:.6g} A while the downstream fuse clears."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=upstream_relay.id,
                    )
                )
                continue
            margin = upstream.operating_time_s - fuse_time
            samples.append(
                CoordinationSample(
                    current_a=current,
                    downstream_operating_time_s=fuse_time,
                    downstream_clearing_time_s=fuse_time,
                    upstream_operating_time_s=upstream.operating_time_s,
                    coordination_margin_s=margin,
                )
            )
        return self._assessment(
            samples,
            diagnostics,
            minimum_coordination_interval_s,
        )

    def _evaluate(
        self,
        downstream_relay: OvercurrentRelay,
        upstream_relay: OvercurrentRelay,
        minimum_current_a: float,
        maximum_current_a: float,
        minimum_interval_s: float,
        sample_count: int,
        downstream_breaker_clearing_s: float,
    ) -> CoordinationAssessment:
        samples: list[CoordinationSample] = []
        diagnostics: list[DomainDiagnostic] = []
        for current in self._logarithmic_grid(minimum_current_a, maximum_current_a, sample_count):
            downstream = downstream_relay.operate(current)
            if not downstream.picked_up or downstream.operating_time_s is None:
                continue
            upstream = upstream_relay.operate(current)
            if not upstream.picked_up or upstream.operating_time_s is None:
                diagnostics.append(
                    DomainDiagnostic(
                        code="PROTECTION-UPSTREAM-NOT-SENSITIVE",
                        message=(
                            f"Upstream relay '{upstream_relay.name}' does not pick up at "
                            f"{current:.6g} A while downstream relay '{downstream_relay.name}' "
                            "is expected to operate."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=upstream_relay.id,
                    )
                )
                continue
            downstream_clear = downstream.operating_time_s + downstream_breaker_clearing_s
            margin = upstream.operating_time_s - downstream_clear
            samples.append(
                CoordinationSample(
                    current_a=current,
                    downstream_operating_time_s=downstream.operating_time_s,
                    downstream_clearing_time_s=downstream_clear,
                    upstream_operating_time_s=upstream.operating_time_s,
                    coordination_margin_s=margin,
                )
            )
        return self._assessment(samples, diagnostics, minimum_interval_s)

    @staticmethod
    def _assessment(
        samples: list[CoordinationSample],
        diagnostics: list[DomainDiagnostic],
        minimum_interval_s: float,
    ) -> CoordinationAssessment:
        failed_sensitivity = any(
            item.code == "PROTECTION-UPSTREAM-NOT-SENSITIVE" for item in diagnostics
        )
        if not samples:
            if not failed_sensitivity:
                diagnostics.append(
                    DomainDiagnostic(
                        code="PROTECTION-COORDINATION-NO-OVERLAP",
                        message=(
                            "No current samples produced simultaneous downstream and upstream "
                            "operation; coordination could not be demonstrated."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                    )
                )
            status = (
                ProtectionAssessmentStatus.FAIL
                if failed_sensitivity
                else ProtectionAssessmentStatus.NOT_EVALUATED
            )
            minimum_margin = None
            critical_current = None
        else:
            critical = min(samples, key=lambda item: item.coordination_margin_s)
            minimum_margin = critical.coordination_margin_s
            critical_current = critical.current_a
            failed_sensitivity = any(
                item.code == "PROTECTION-UPSTREAM-NOT-SENSITIVE" for item in diagnostics
            )
            status = (
                ProtectionAssessmentStatus.FAIL
                if failed_sensitivity or minimum_margin < minimum_interval_s
                else ProtectionAssessmentStatus.PASS
            )
            if minimum_margin < minimum_interval_s:
                diagnostics.append(
                    DomainDiagnostic(
                        code="PROTECTION-COORDINATION-MARGIN-INSUFFICIENT",
                        message=(
                            f"Minimum achieved margin {minimum_margin:.6g} s is below the "
                            f"required {minimum_interval_s:.6g} s."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                    )
                )
        return CoordinationAssessment(
            status=status,
            minimum_required_margin_s=minimum_interval_s,
            minimum_achieved_margin_s=minimum_margin,
            critical_current_a=critical_current,
            samples=tuple(samples),
            diagnostics=tuple(diagnostics),
        )

    @staticmethod
    def _validate_common(
        downstream_relay: OvercurrentRelay,
        upstream_relay: OvercurrentRelay,
        minimum_current_a: float,
        maximum_current_a: float,
        minimum_interval_s: float,
        sample_count: int,
    ) -> None:
        if not isinstance(downstream_relay, OvercurrentRelay):
            raise TypeError("downstream_relay must be an OvercurrentRelay.")
        if not isinstance(upstream_relay, OvercurrentRelay):
            raise TypeError("upstream_relay must be an OvercurrentRelay.")
        ProtectionCoordinationAnalyzer._validate_range(
            minimum_current_a, maximum_current_a, minimum_interval_s, sample_count
        )
        if downstream_relay.function is not upstream_relay.function:
            raise ProtectionCoordinationError(
                "Relay pair coordination requires the same phase/earth current channel."
            )

    @staticmethod
    def _validate_range(
        minimum_current_a: float,
        maximum_current_a: float,
        minimum_interval_s: float,
        sample_count: int,
    ) -> None:
        values = (minimum_current_a, maximum_current_a, minimum_interval_s)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values
        ):
            raise TypeError("Current bounds and coordination interval must be finite real numbers.")
        if minimum_current_a <= 0.0 or maximum_current_a < minimum_current_a:
            raise ProtectionCoordinationError("Invalid positive fault-current range.")
        if minimum_interval_s < 0.0:
            raise ProtectionCoordinationError("Coordination interval cannot be negative.")
        if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 2:
            raise ProtectionCoordinationError("sample_count must be an integer greater than one.")

    @staticmethod
    def _logarithmic_grid(minimum: float, maximum: float, count: int) -> tuple[float, ...]:
        if math.isclose(minimum, maximum, rel_tol=1e-12, abs_tol=1e-12):
            return (float(minimum),)
        log_min, log_max = math.log(minimum), math.log(maximum)
        return tuple(
            math.exp(log_min + index * (log_max - log_min) / (count - 1)) for index in range(count)
        )
