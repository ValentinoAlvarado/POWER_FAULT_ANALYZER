"""Composition root for the PySide6 desktop application."""

from __future__ import annotations

from dataclasses import dataclass

from power_fault_analyzer.application.use_cases.export_study_report import ExportStudyReport
from power_fault_analyzer.application.use_cases.project_workspace import ProjectWorkspaceService
from power_fault_analyzer.application.use_cases.run_thevenin_fault_study import (
    RunTheveninFaultStudy,
)
from power_fault_analyzer.infrastructure.adapters.engineering_report_exporter_adapter import (
    EngineeringReportExporterAdapter,
)
from power_fault_analyzer.infrastructure.adapters.short_circuit_solver_adapter import (
    NumericalShortCircuitSolverAdapter,
)
from power_fault_analyzer.infrastructure.adapters.thevenin_sequence_network_factory_adapter import (
    TheveninSequenceNetworkFactoryAdapter,
)
from power_fault_analyzer.infrastructure.persistence.json_project_repository import (
    JSONProjectRepository,
)


@dataclass(frozen=True, slots=True)
class DesktopApplicationServices:
    project_workspace: ProjectWorkspaceService
    run_fault_study: RunTheveninFaultStudy
    export_report: ExportStudyReport


def build_desktop_services() -> DesktopApplicationServices:
    repository = JSONProjectRepository()
    solver = NumericalShortCircuitSolverAdapter()
    exporter = EngineeringReportExporterAdapter()
    return DesktopApplicationServices(
        project_workspace=ProjectWorkspaceService(repository),
        run_fault_study=RunTheveninFaultStudy(
            solver,
            TheveninSequenceNetworkFactoryAdapter(),
        ),
        export_report=ExportStudyReport(exporter),
    )
