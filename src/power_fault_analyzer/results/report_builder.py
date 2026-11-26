"""Adapters from solver results to immutable engineering report records."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.iec60909_study import IEC60909StudyResult
from power_fault_analyzer.domain.value_objects.line_fault_result import LineFaultStudyResult
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.results.result_models import (
    BranchCurrentResult,
    CorrectionFactorResult,
    DiagnosticResult,
    EngineeringStudyReport,
    FaultResultRecord,
    IECQuantityResult,
    PhaseQuantityResult,
    PhasorValue,
    QuantityAvailability,
    ResultLocationKind,
    SequenceQuantityResult,
    SourceContributionBalanceResult,
    SourceContributionResult,
    StudyMetadata,
)
from power_fault_analyzer.standards.iec60909.models import IEC60909QuantityStatus

if TYPE_CHECKING:
    from power_fault_analyzer.infrastructure.numerical.iec60909_source_contributions import (
        IEC60909SourceContributionAnalysis,
    )

_PHASES = ("A", "B", "C")
_SEQUENCE_ORDER = (SequenceType.ZERO, SequenceType.POSITIVE, SequenceType.NEGATIVE)


class EngineeringStudyReportBuilder:
    """Build report-ready results without changing any electrical calculation."""

    def __init__(
        self,
        *,
        project_name: str,
        study_name: str,
        network: object | None = None,
        generated_at: datetime | None = None,
        study_id: UUID | None = None,
        limitations: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(project_name, str) or not project_name.strip():
            raise ValueError("project_name must be a non-empty string.")
        if not isinstance(study_name, str) or not study_name.strip():
            raise ValueError("study_name must be a non-empty string.")
        if network is not None and not hasattr(network, "buses"):
            raise TypeError("network must expose an immutable buses collection.")
        if generated_at is None:
            generated_at = datetime.now(UTC)
        if not isinstance(generated_at, datetime) or generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")
        if study_id is not None and not isinstance(study_id, UUID):
            raise TypeError("study_id must be a UUID or None.")
        if not isinstance(limitations, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in limitations
        ):
            raise TypeError("limitations must be a tuple of non-empty strings.")
        self._project_name = project_name.strip()
        self._study_name = study_name.strip()
        self._network = network
        self._generated_at = generated_at
        self._study_id = study_id or uuid4()
        default_limitations = (
            (
                "Network-wide branch through-currents and transformer winding currents are not "
                "exposed by the current solver result contracts. The report does not infer them "
                "from bus voltages or Ybus off-diagonal terms."
            ),
            (
                "For an interior-line fault, branch-current rows are limited to the two line-terminal "
                "currents explicitly supplied by LineFaultStudyResult; they are not a network-wide "
                "branch-current solution."
            ),
        )
        self._limitations = tuple(dict.fromkeys((*limitations, *default_limitations)))
        self._faults: list[FaultResultRecord] = []
        self._source_contributions: list[SourceContributionResult] = []
        self._source_balance_residuals: list[SourceContributionBalanceResult] = []
        self._branch_currents: list[BranchCurrentResult] = []
        self._diagnostics: list[DiagnosticResult] = []
        self._assumptions: list[str] = []
        self._standard_edition: str | None = None
        self._used_fault_ids: set[str] = set()
        self._bus_names = (
            {str(bus.id): str(bus.name) for bus in getattr(network, "buses", ())}
            if network is not None
            else {}
        )
        self._network_name = str(getattr(network, "name", "Not supplied"))

    def add_short_circuit_result(
        self,
        result: ShortCircuitResult,
        *,
        location_name: str | None = None,
        fault_id: str | None = None,
    ) -> EngineeringStudyReportBuilder:
        if not isinstance(result, ShortCircuitResult):
            raise TypeError("result must be a ShortCircuitResult.")
        record_id = fault_id or str(result.bus_id)
        record = self._fault_record(
            result,
            fault_id=record_id,
            location_kind=ResultLocationKind.BUS,
            location_id=str(result.bus_id),
            location_name=location_name
            or self._bus_names.get(str(result.bus_id), f"Bus {result.bus_id}"),
        )
        self._append_fault(record)
        return self

    def add_iec60909_result(
        self,
        result: IEC60909StudyResult,
        *,
        location_name: str | None = None,
        fault_id: str | None = None,
    ) -> EngineeringStudyReportBuilder:
        if not isinstance(result, IEC60909StudyResult):
            raise TypeError("result must be an IEC60909StudyResult.")
        self._set_standard(result.standard_edition)
        base = result.base_result
        record_id = fault_id or str(base.bus_id)
        record = self._fault_record(
            base,
            fault_id=record_id,
            location_kind=ResultLocationKind.BUS,
            location_id=str(base.bus_id),
            location_name=location_name
            or self._bus_names.get(str(base.bus_id), f"Bus {base.bus_id}"),
            current_case=result.current_case.value,
            voltage_factor=result.voltage_factor,
            equivalent_voltage_pu=PhasorValue.from_complex(result.equivalent_voltage_pu),
            fault_duration_s=result.fault_duration_s,
            frequency_hz=result.frequency_hz,
            first_pole_contact_separation_time_s=result.first_pole_contact_separation_time_s,
            iec_quantities=self._iec_quantities(result),
            correction_factors=tuple(
                CorrectionFactorResult(name, value)
                for name, value in sorted(result.applied_transformer_correction_factors.items())
            ),
            diagnostics=tuple(self._diagnostic(item) for item in result.diagnostics),
        )
        self._append_fault(record)
        return self

    def add_line_fault_result(
        self,
        result: LineFaultStudyResult,
        *,
        fault_id: str | None = None,
    ) -> EngineeringStudyReportBuilder:
        if not isinstance(result, LineFaultStudyResult):
            raise TypeError("result must be a LineFaultStudyResult.")
        record_id = fault_id or str(result.fault_node_id)
        location_name = (
            f"{result.line_name} at {result.distance_from_km:.6g} km from "
            f"{self._bus_names.get(str(result.from_bus_id), str(result.from_bus_id))}"
        )
        record = self._fault_record(
            result.fault_result,
            fault_id=record_id,
            location_kind=ResultLocationKind.LINE_INTERIOR,
            location_id=str(result.fault_node_id),
            location_name=location_name,
            line_branch_id=str(result.branch_id),
            line_name=result.line_name,
            from_bus_name=self._bus_names.get(str(result.from_bus_id), str(result.from_bus_id)),
            to_bus_name=self._bus_names.get(str(result.to_bus_id), str(result.to_bus_id)),
            distance_from_km=result.distance_from_km,
            distance_to_km=result.distance_to_km,
        )
        self._append_fault(record)
        self._add_line_terminal_currents(record_id, result)
        return self

    def add_source_contribution_analysis(
        self,
        analysis: IEC60909SourceContributionAnalysis,
        *,
        fault_id: str | None = None,
    ) -> EngineeringStudyReportBuilder:
        required_attributes = ("scenario_id", "total_result", "source_contributions", "trace")
        if any(not hasattr(analysis, name) for name in required_attributes):
            raise TypeError(
                "analysis must provide an IEC 60909 source-contribution analysis contract."
            )
        related_fault_id = fault_id or str(analysis.total_result.bus_id)
        if related_fault_id not in self._used_fault_ids:
            raise ValueError(
                "Add the corresponding fault result before its source-contribution analysis."
            )
        for contribution in analysis.source_contributions:
            for sequence, current in contribution.sequence_currents_ka.items():
                self._source_contributions.append(
                    SourceContributionResult(
                        fault_id=related_fault_id,
                        scenario_id=str(analysis.scenario_id),
                        source_id=str(contribution.source_id),
                        source_name=contribution.source_name,
                        source_family=contribution.source_family.value,
                        source_mode=contribution.source_mode.value,
                        domain="sequence",
                        component=sequence.value,
                        current_ka=PhasorValue.from_complex(current),
                        model_reference=contribution.model_reference,
                    )
                )
            for phase, current in contribution.phase_currents_ka.items():
                self._source_contributions.append(
                    SourceContributionResult(
                        fault_id=related_fault_id,
                        scenario_id=str(analysis.scenario_id),
                        source_id=str(contribution.source_id),
                        source_name=contribution.source_name,
                        source_family=contribution.source_family.value,
                        source_mode=contribution.source_mode.value,
                        domain="phase",
                        component=phase,
                        current_ka=PhasorValue.from_complex(current),
                        model_reference=contribution.model_reference,
                    )
                )
        self._source_balance_residuals.extend(
            SourceContributionBalanceResult(
                fault_id=related_fault_id,
                scenario_id=str(analysis.scenario_id),
                domain="sequence",
                component=sequence.value,
                residual_ka=residual,
                method_id=analysis.method_id,
            )
            for sequence, residual in analysis.sequence_balance_residual_ka.items()
        )
        self._source_balance_residuals.extend(
            SourceContributionBalanceResult(
                fault_id=related_fault_id,
                scenario_id=str(analysis.scenario_id),
                domain="phase",
                component=phase,
                residual_ka=residual,
                method_id=analysis.method_id,
            )
            for phase, residual in analysis.phase_balance_residual_ka.items()
        )
        trace_quantities = tuple(
            IECQuantityResult(
                name=item.quantity.value,
                unit=item.unit,
                value=item.value if item.status is IEC60909QuantityStatus.CALCULATED else None,
                status=(
                    QuantityAvailability.CALCULATED
                    if item.status is IEC60909QuantityStatus.CALCULATED
                    else QuantityAvailability.NOT_APPLICABLE
                    if item.status is IEC60909QuantityStatus.NOT_APPLICABLE
                    else QuantityAvailability.UNAVAILABLE
                ),
                method_reference=item.method_id,
                reason=item.reason,
            )
            for item in analysis.trace.quantity_results
        )
        if trace_quantities:
            index = next(
                index
                for index, item in enumerate(self._faults)
                if item.fault_id == related_fault_id
            )
            existing = self._faults[index]
            by_name = {item.name: item for item in existing.iec_quantities}
            for item in trace_quantities:
                previous = by_name.get(item.name)
                if previous is not None and previous != item:
                    raise ValueError(
                        f"IEC quantity '{item.name}' differs between the study result and source trace."
                    )
                by_name[item.name] = item
            self._faults[index] = replace(
                existing,
                iec_quantities=tuple(by_name[name] for name in sorted(by_name)),
            )

        trace_factors = tuple(
            CorrectionFactorResult(
                name=factor.name,
                value=factor.value,
                provenance=self._factor_provenance(factor),
            )
            for factor in analysis.trace.applied_factors
        )
        if trace_factors:
            index = next(
                index
                for index, item in enumerate(self._faults)
                if item.fault_id == related_fault_id
            )
            existing = self._faults[index]
            existing_by_id = {
                item.name + "|" + item.provenance for item in existing.correction_factors
            }
            combined = existing.correction_factors + tuple(
                item
                for item in trace_factors
                if item.name + "|" + item.provenance not in existing_by_id
            )
            self._faults[index] = replace(existing, correction_factors=combined)
        self._assumptions.extend(analysis.trace.assumptions)
        self._set_standard(analysis.trace.standard_edition)
        return self

    def add_assumption(self, assumption: str) -> EngineeringStudyReportBuilder:
        if not isinstance(assumption, str) or not assumption.strip():
            raise ValueError("assumption must be a non-empty string.")
        self._assumptions.append(assumption.strip())
        return self

    def build(self) -> EngineeringStudyReport:
        if not self._faults:
            raise ValueError(
                "At least one fault result is required to build an engineering report."
            )
        metadata = StudyMetadata(
            study_id=str(self._study_id),
            project_name=self._project_name,
            study_name=self._study_name,
            network_name=self._network_name,
            generated_at=self._generated_at,
            standard_edition=self._standard_edition,
        )
        return EngineeringStudyReport(
            metadata=metadata,
            faults=tuple(self._faults),
            source_contributions=tuple(self._source_contributions),
            source_balance_residuals=tuple(self._source_balance_residuals),
            branch_currents=tuple(self._branch_currents),
            diagnostics=tuple(self._diagnostics),
            assumptions=tuple(dict.fromkeys(self._assumptions)),
            limitations=self._limitations,
        )

    def _append_fault(self, record: FaultResultRecord) -> None:
        if record.fault_id in self._used_fault_ids:
            raise ValueError(f"Duplicate fault_id in report: {record.fault_id}.")
        self._used_fault_ids.add(record.fault_id)
        self._faults.append(record)
        for diagnostic in record.diagnostics:
            if diagnostic not in self._diagnostics:
                self._diagnostics.append(diagnostic)

    def _set_standard(self, edition: str) -> None:
        if self._standard_edition is not None and self._standard_edition != edition:
            raise ValueError("One report cannot mix calculation standard editions.")
        self._standard_edition = edition

    def _fault_record(
        self,
        result: ShortCircuitResult,
        *,
        fault_id: str,
        location_kind: ResultLocationKind,
        location_id: str,
        location_name: str,
        current_case: str | None = None,
        voltage_factor: float | None = None,
        equivalent_voltage_pu: PhasorValue | None = None,
        fault_duration_s: float | None = None,
        frequency_hz: float | None = None,
        first_pole_contact_separation_time_s: float | None = None,
        iec_quantities: tuple[IECQuantityResult, ...] = (),
        correction_factors: tuple[CorrectionFactorResult, ...] = (),
        diagnostics: tuple[DiagnosticResult, ...] | None = None,
        line_branch_id: str | None = None,
        line_name: str | None = None,
        from_bus_name: str | None = None,
        to_bus_name: str | None = None,
        distance_from_km: float | None = None,
        distance_to_km: float | None = None,
    ) -> FaultResultRecord:
        phase_results = tuple(
            PhaseQuantityResult(
                phase=phase,
                current_pu=PhasorValue.from_complex(result.phase_currents_pu[index]),
                current_ka=PhasorValue.from_complex(result.phase_currents_ka[index]),
                voltage_pu=PhasorValue.from_complex(result.phase_voltages_pu[index]),
                voltage_kv=PhasorValue.from_complex(result.phase_voltages_kv[index]),
            )
            for index, phase in enumerate(_PHASES)
        )
        sequence_results = tuple(
            SequenceQuantityResult(
                sequence=sequence.value,
                current_pu=(
                    PhasorValue.from_complex(result.sequence_currents_pu[sequence])
                    if sequence in result.sequence_currents_pu
                    else None
                ),
                voltage_pu=(
                    PhasorValue.from_complex(result.sequence_fault_voltages_pu[sequence])
                    if sequence in result.sequence_fault_voltages_pu
                    else None
                ),
                driving_point_impedance_pu=(
                    PhasorValue.from_complex(result.driving_point_impedances_pu[sequence])
                    if sequence in result.driving_point_impedances_pu
                    else None
                ),
                prefault_voltage_pu=(
                    PhasorValue.from_complex(result.prefault_sequence_voltages_pu[sequence])
                    if sequence in result.prefault_sequence_voltages_pu
                    else None
                ),
            )
            for sequence in _SEQUENCE_ORDER
            if sequence in result.sequence_currents_pu
            or sequence in result.sequence_fault_voltages_pu
            or sequence in result.driving_point_impedances_pu
            or sequence in result.prefault_sequence_voltages_pu
        )
        fault_diagnostics = (
            diagnostics
            if diagnostics is not None
            else tuple(self._diagnostic(item) for item in result.diagnostics)
        )
        return FaultResultRecord(
            fault_id=fault_id,
            location_kind=location_kind,
            location_id=location_id,
            location_name=location_name,
            fault_type=result.fault_type.value,
            fault_impedance_pu=PhasorValue.from_complex(result.fault_impedance_pu),
            base_power_mva=result.base_power_mva,
            base_voltage_kv=result.base_voltage_kv,
            base_current_ka=result.base_current_ka,
            maximum_phase_current_ka=result.maximum_phase_current_ka,
            phase_quantities=phase_results,
            sequence_quantities=sequence_results,
            ground_current_pu=PhasorValue.from_complex(result.ground_current_pu),
            ground_current_ka=PhasorValue.from_complex(result.ground_current_ka),
            current_case=current_case,
            voltage_factor=voltage_factor,
            equivalent_voltage_pu=equivalent_voltage_pu,
            fault_duration_s=fault_duration_s,
            frequency_hz=frequency_hz,
            first_pole_contact_separation_time_s=first_pole_contact_separation_time_s,
            line_branch_id=line_branch_id,
            line_name=line_name,
            from_bus_name=from_bus_name,
            to_bus_name=to_bus_name,
            distance_from_km=distance_from_km,
            distance_to_km=distance_to_km,
            iec_quantities=iec_quantities,
            correction_factors=correction_factors,
            diagnostics=fault_diagnostics,
        )

    @staticmethod
    def _diagnostic(diagnostic: object) -> DiagnosticResult:
        return DiagnosticResult(
            code=diagnostic.code,
            severity=diagnostic.severity.value,
            message=diagnostic.message,
            entity_id=str(diagnostic.entity_id) if diagnostic.entity_id is not None else None,
        )

    @staticmethod
    def _iec_quantities(result: IEC60909StudyResult) -> tuple[IECQuantityResult, ...]:
        value_map: tuple[tuple[str, str, float | None], ...] = (
            ("I''k", "kA", result.initial_symmetrical_current_ka),
            ("ip", "kA", result.peak_current_ka),
            ("Ib", "kA", result.breaking_current_ka),
            ("Ik", "kA", result.steady_state_current_ka),
            ("Ith", "kA", result.thermal_equivalent_current_ka),
            ("J", "kA^2 s", result.joule_integral_ka2s),
        )
        quantities: list[IECQuantityResult] = []
        for name, unit, value in value_map:
            if value is not None:
                quantities.append(
                    IECQuantityResult(
                        name=name,
                        unit=unit,
                        value=value,
                        status=QuantityAvailability.CALCULATED,
                        method_reference=result.current_method_references.get(name),
                    )
                )
            elif name in result.unavailable_quantity_reasons:
                quantities.append(
                    IECQuantityResult(
                        name=name,
                        unit=unit,
                        status=QuantityAvailability.UNAVAILABLE,
                        reason=result.unavailable_quantity_reasons[name],
                    )
                )
            else:
                quantities.append(
                    IECQuantityResult(
                        name=name, unit=unit, status=QuantityAvailability.NOT_REPORTED
                    )
                )
        for name, unit in (("iDC", "kA"), ("Ibasym", "kA")):
            if name in result.unavailable_quantity_reasons:
                quantities.append(
                    IECQuantityResult(
                        name=name,
                        unit=unit,
                        status=QuantityAvailability.UNAVAILABLE,
                        reason=result.unavailable_quantity_reasons[name],
                    )
                )
            else:
                quantities.append(
                    IECQuantityResult(
                        name=name, unit=unit, status=QuantityAvailability.NOT_REPORTED
                    )
                )
        if result.dc_component_at_separation_ka is not None:
            quantities.append(
                IECQuantityResult(
                    name="iDC_RL_supplement",
                    unit="kA",
                    value=result.dc_component_at_separation_ka,
                    status=QuantityAvailability.CALCULATED,
                    method_reference=result.current_method_references.get("iDC_supplement"),
                    classification="supplementary",
                )
            )
        if result.asymmetrical_breaking_current_ka is not None:
            quantities.append(
                IECQuantityResult(
                    name="Ibasym_RL_supplement",
                    unit="kA",
                    value=result.asymmetrical_breaking_current_ka,
                    status=QuantityAvailability.CALCULATED,
                    method_reference=result.current_method_references.get("Ibasym_supplement"),
                    classification="supplementary",
                )
            )
        return tuple(quantities)

    @staticmethod
    def _factor_provenance(factor: object) -> str:
        input_text = (
            "; ".join(f"{item.name}={item.value:g} {item.unit}" for item in factor.inputs)
            or "no factor inputs supplied"
        )
        scope = ", ".join(
            f"{name}={value}"
            for name, value in (
                ("equipment_id", factor.equipment_id),
                ("source_id", factor.source_id),
                ("scenario_id", factor.scenario_id),
            )
            if value is not None
        )
        return (
            f"{factor.standard_edition}, clause {factor.clause_reference}; "
            f"factor_id={factor.factor_id}; scope={scope}; inputs: {input_text}"
        )

    def _add_line_terminal_currents(self, fault_id: str, result: LineFaultStudyResult) -> None:
        for terminal_name, terminal, bus_name in (
            (
                "from",
                result.from_terminal,
                self._bus_names.get(str(result.from_bus_id), str(result.from_bus_id)),
            ),
            (
                "to",
                result.to_terminal,
                self._bus_names.get(str(result.to_bus_id), str(result.to_bus_id)),
            ),
        ):
            for index, phase in enumerate(_PHASES):
                self._branch_currents.append(
                    BranchCurrentResult(
                        fault_id=fault_id,
                        branch_id=str(result.branch_id),
                        branch_name=result.line_name,
                        equipment_type="line",
                        terminal=terminal_name,
                        bus_id=str(terminal.bus_id),
                        bus_name=bus_name,
                        phase=phase,
                        current_pu=PhasorValue.from_complex(
                            terminal.phase_currents_into_line_pu[index]
                        ),
                        current_ka=PhasorValue.from_complex(
                            terminal.phase_currents_into_line_ka[index]
                        ),
                    )
                )
