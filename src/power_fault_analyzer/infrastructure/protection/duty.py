"""Circuit-breaker interrupting and conductor thermal-withstand assessments."""

from __future__ import annotations

import math

from power_fault_analyzer.domain.enums.protection import (
    CircuitBreakerStandard,
    ProtectionAssessmentStatus,
)
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.iec60909_study import IEC60909StudyResult
from power_fault_analyzer.domain.value_objects.protection_assessment import (
    ConductorThermalAssessment,
    EquipmentDutyAssessment,
    RelaySensitivityAssessment,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    ConductorThermalLimit,
    FuseLink,
    OvercurrentRelay,
)


class ProtectionDutyEvaluator:
    """Assess breaker ratings and adiabatic conductor limits against IEC results."""

    def evaluate_breaker(
        self,
        breaker: CircuitBreaker,
        study: IEC60909StudyResult,
        *,
        operating_voltage_kv: float,
    ) -> EquipmentDutyAssessment:
        if not isinstance(breaker, CircuitBreaker):
            raise TypeError("breaker must be a CircuitBreaker.")
        if not isinstance(study, IEC60909StudyResult):
            raise TypeError("study must be an IEC60909StudyResult.")
        voltage = self._positive(operating_voltage_kv, "operating_voltage_kv")
        checks: dict[str, ProtectionAssessmentStatus] = {}
        margins: dict[str, float] = {}
        diagnostics: list[DomainDiagnostic] = []

        voltage_margin = breaker.rated_voltage_kv - voltage
        margins["voltage_kv"] = voltage_margin
        checks["voltage"] = (
            ProtectionAssessmentStatus.PASS
            if voltage_margin >= -1e-9
            else ProtectionAssessmentStatus.FAIL
        )
        if checks["voltage"] is ProtectionAssessmentStatus.FAIL:
            diagnostics.append(
                DomainDiagnostic(
                    code="BREAKER-RATED-VOLTAGE-EXCEEDED",
                    message=(
                        f"Operating voltage {voltage:.6g} kV exceeds breaker rating "
                        f"{breaker.rated_voltage_kv:.6g} kV."
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=breaker.id,
                )
            )

        breaking = study.breaking_current_ka
        breaking_check = (
            "icu"
            if breaker.standard is CircuitBreakerStandard.IEC_60947_2
            else "rated_breaking_current"
        )
        if breaking is None:
            checks[breaking_check] = ProtectionAssessmentStatus.NOT_EVALUATED
            diagnostics.append(
                DomainDiagnostic(
                    code="BREAKER-BREAKING-CURRENT-NOT-EVALUATED",
                    message="The IEC study does not provide a supported breaking-current value.",
                    severity=DiagnosticSeverity.WARNING,
                    entity_id=breaker.id,
                )
            )
        else:
            margins["breaking_capacity_ka"] = breaker.rated_breaking_current_ka - breaking
            checks[breaking_check] = (
                ProtectionAssessmentStatus.PASS
                if margins["breaking_capacity_ka"] >= -1e-9
                else ProtectionAssessmentStatus.FAIL
            )
        if (
            breaker.standard is CircuitBreakerStandard.IEC_60947_2
            and breaker.service_breaking_capacity_ka is not None
        ):
            if breaking is None:
                checks["ics"] = ProtectionAssessmentStatus.NOT_EVALUATED
            else:
                margins["ics_ka"] = breaker.service_breaking_capacity_ka - breaking
                checks["ics"] = (
                    ProtectionAssessmentStatus.PASS
                    if margins["ics_ka"] >= -1e-9
                    else ProtectionAssessmentStatus.FAIL
                )
        if breaker.making_capacity_peak_ka is not None:
            if study.peak_current_ka is None:
                checks["icm"] = ProtectionAssessmentStatus.NOT_EVALUATED
                diagnostics.append(
                    DomainDiagnostic(
                        code="BREAKER-ICM-NOT-EVALUATED",
                        message="The IEC study does not provide a supported peak-current value.",
                        severity=DiagnosticSeverity.WARNING,
                        entity_id=breaker.id,
                    )
                )
            else:
                margins["icm_ka_peak"] = breaker.making_capacity_peak_ka - study.peak_current_ka
                checks["icm"] = (
                    ProtectionAssessmentStatus.PASS
                    if margins["icm_ka_peak"] >= -1e-9
                    else ProtectionAssessmentStatus.FAIL
                )
        if breaker.short_time_withstand_current_ka is not None:
            if study.joule_integral_ka2s is None:
                checks["icw"] = ProtectionAssessmentStatus.NOT_EVALUATED
            else:
                rated_i2t = (
                    breaker.short_time_withstand_current_ka**2
                    * breaker.short_time_withstand_duration_s
                )
                actual_i2t = study.joule_integral_ka2s
                margins["icw_i2t_ka2s"] = rated_i2t - actual_i2t
                margins["icw_duration_s"] = (
                    breaker.short_time_withstand_duration_s - study.fault_duration_s
                )
                checks["icw"] = (
                    ProtectionAssessmentStatus.PASS
                    if margins["icw_i2t_ka2s"] >= -1e-9 and margins["icw_duration_s"] >= -1e-9
                    else ProtectionAssessmentStatus.FAIL
                )

        if any(value is ProtectionAssessmentStatus.FAIL for value in checks.values()):
            overall = ProtectionAssessmentStatus.FAIL
        elif any(
            checks.get(key) is ProtectionAssessmentStatus.NOT_EVALUATED
            for key in ("voltage", breaking_check)
        ) or any(value is ProtectionAssessmentStatus.NOT_EVALUATED for value in checks.values()):
            overall = ProtectionAssessmentStatus.NOT_EVALUATED
        else:
            overall = ProtectionAssessmentStatus.PASS

        return EquipmentDutyAssessment(
            equipment_id=breaker.id,
            status=overall,
            checks=checks,
            margins=margins,
            diagnostics=tuple(diagnostics),
        )

    def evaluate_fuse(
        self,
        fuse: FuseLink,
        study: IEC60909StudyResult,
        *,
        operating_voltage_kv: float,
    ) -> EquipmentDutyAssessment:
        """Check fuse rated voltage and AC symmetrical breaking capacity."""
        if not isinstance(fuse, FuseLink):
            raise TypeError("fuse must be a FuseLink.")
        if not isinstance(study, IEC60909StudyResult):
            raise TypeError("study must be an IEC60909StudyResult.")
        voltage = self._positive(operating_voltage_kv, "operating_voltage_kv")
        checks: dict[str, ProtectionAssessmentStatus] = {}
        margins: dict[str, float] = {}
        voltage_margin = fuse.rated_voltage_kv - voltage
        margins["voltage_kv"] = voltage_margin
        checks["voltage"] = (
            ProtectionAssessmentStatus.PASS
            if voltage_margin >= -1e-9
            else ProtectionAssessmentStatus.FAIL
        )
        margins["breaking_capacity_ka"] = (
            fuse.breaking_capacity_ka - study.initial_symmetrical_current_ka
        )
        checks["breaking_capacity"] = (
            ProtectionAssessmentStatus.PASS
            if margins["breaking_capacity_ka"] >= -1e-9
            else ProtectionAssessmentStatus.FAIL
        )
        diagnostics: list[DomainDiagnostic] = []
        if checks["voltage"] is ProtectionAssessmentStatus.FAIL:
            diagnostics.append(
                DomainDiagnostic(
                    code="FUSE-RATED-VOLTAGE-EXCEEDED",
                    message="Operating voltage exceeds the fuse-link rated voltage.",
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=fuse.id,
                )
            )
        if checks["breaking_capacity"] is ProtectionAssessmentStatus.FAIL:
            diagnostics.append(
                DomainDiagnostic(
                    code="FUSE-BREAKING-CAPACITY-EXCEEDED",
                    message=(
                        "Prospective symmetrical short-circuit current exceeds the fuse-link "
                        "rated breaking capacity."
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=fuse.id,
                )
            )
        status = (
            ProtectionAssessmentStatus.FAIL
            if any(value is ProtectionAssessmentStatus.FAIL for value in checks.values())
            else ProtectionAssessmentStatus.PASS
        )
        return EquipmentDutyAssessment(
            equipment_id=fuse.id,
            status=status,
            checks=checks,
            margins=margins,
            diagnostics=tuple(diagnostics),
        )

    def evaluate_conductor(
        self,
        conductor: ConductorThermalLimit,
        study: IEC60909StudyResult,
    ) -> ConductorThermalAssessment:
        if not isinstance(conductor, ConductorThermalLimit):
            raise TypeError("conductor must be a ConductorThermalLimit.")
        if not isinstance(study, IEC60909StudyResult):
            raise TypeError("study must be an IEC60909StudyResult.")
        if study.fault_duration_s > 5.0:
            raise ValueError(
                "The adiabatic k²S² method is restricted to short-circuit durations up to 5 s."
            )
        if study.joule_integral_ka2s is None:
            raise ValueError("The IEC study does not contain a supported Joule integral.")
        actual = study.joule_integral_ka2s * 1e6
        withstand = conductor.withstand_i2t_a2s
        utilization = actual / withstand
        return ConductorThermalAssessment(
            status=(
                ProtectionAssessmentStatus.PASS
                if actual <= withstand * (1.0 + 1e-12)
                else ProtectionAssessmentStatus.FAIL
            ),
            actual_i2t_a2s=actual,
            withstand_i2t_a2s=withstand,
            utilization=utilization,
            fault_duration_s=study.fault_duration_s,
        )

    def evaluate_relay_sensitivity(
        self,
        relay: OvercurrentRelay,
        *,
        minimum_fault_current_a: float,
        required_sensitivity_ratio: float,
    ) -> RelaySensitivityAssessment:
        if not isinstance(relay, OvercurrentRelay):
            raise TypeError("relay must be an OvercurrentRelay.")
        minimum_current = self._positive(minimum_fault_current_a, "minimum_fault_current_a")
        required_ratio = self._positive(required_sensitivity_ratio, "required_sensitivity_ratio")
        pickup = relay.pickup_primary_a
        ratio = minimum_current / pickup
        return RelaySensitivityAssessment(
            status=(
                ProtectionAssessmentStatus.PASS
                if ratio >= required_ratio
                else ProtectionAssessmentStatus.FAIL
            ),
            minimum_fault_current_a=minimum_current,
            relay_pickup_current_primary_a=pickup,
            sensitivity_ratio=ratio,
            required_sensitivity_ratio=required_ratio,
        )

    @staticmethod
    def _positive(value: float, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a real number, not bool.")
        result = float(value)
        if not math.isfinite(result) or result <= 0.0:
            raise ValueError(f"{name} must be finite and positive.")
        return result
