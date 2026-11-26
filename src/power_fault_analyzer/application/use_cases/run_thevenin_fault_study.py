"""Execute a single-bus Thevenin fault study through the production solver port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from power_fault_analyzer.application.ports.short_circuit_solver import ShortCircuitSolverPort
from power_fault_analyzer.application.ports.thevenin_sequence_network_factory import (
    TheveninSequenceNetworkFactoryPort,
)
from power_fault_analyzer.domain.projects.models import Project, ProjectStudyRun
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet
from power_fault_analyzer.results.report_builder import EngineeringStudyReportBuilder
from power_fault_analyzer.results.result_models import EngineeringStudyReport


@dataclass(frozen=True, slots=True)
class StudyExecution:
    project: Project
    result: ShortCircuitResult
    report: EngineeringStudyReport
    run: ProjectStudyRun


class RunTheveninFaultStudy:
    """Application use case for an explicitly parameterized Thevenin equivalent."""

    def __init__(
        self,
        solver: ShortCircuitSolverPort,
        network_factory: TheveninSequenceNetworkFactoryPort,
    ) -> None:
        self._solver = solver
        self._network_factory = network_factory

    def execute(self, project: Project) -> StudyExecution:
        if not isinstance(project, Project):
            raise TypeError("project must be a Project aggregate.")

        settings = project.study_settings
        bus_id, networks = self._network_factory.build(settings)
        system_base = SystemBaseSet(
            base_power_mva=settings.base_power_mva,
            bus_voltage_bases_kv={bus_id: settings.base_voltage_ll_kv},
        )
        fault = FaultSpecification(
            fault_type=settings.fault_type,
            bus_id=bus_id,
            fault_impedance_pu=settings.fault_impedance_pu,
        )

        result = self._solver.solve(networks, fault, system_base)
        now = datetime.now(UTC)
        report_builder = EngineeringStudyReportBuilder(
            project_name=project.name,
            study_name=settings.study_name,
            generated_at=now,
            study_id=uuid4(),
            limitations=(
                (
                    "This desktop study uses a single-bus Thevenin equivalent. "
                    "It does not represent a multi-bus network or "
                    "calculate network branch currents."
                ),
                (
                    "The calculation is a general symmetrical-components bus-fault study; no IEC "
                    "60909 correction procedure is applied."
                ),
            ),
        )
        report_builder.add_short_circuit_result(
            result,
            location_name=settings.bus_name,
            fault_id=f"{settings.study_name}-{now.strftime('%Y%m%dT%H%M%S%fZ')}",
        )
        report_builder.add_assumption(
            "The system is represented by explicit positive-, negative- and zero-sequence "
            "Thevenin impedances at one faulted bus."
        )
        report_builder.add_assumption(
            "Only the positive-sequence Thevenin source has a non-zero prefault EMF; the "
            "negative- and zero-sequence source EMFs are set to zero."
        )
        report = report_builder.build()
        run = ProjectStudyRun.from_result(
            result,
            study_name=settings.study_name,
            settings_snapshot=settings,
            executed_at=now,
        )
        updated_project = project.with_study_run(run)
        return StudyExecution(updated_project, result, report, run)
