"""Composition root for the rebuilt engineering desktop workbench."""

from __future__ import annotations

from dataclasses import dataclass

from power_fault_analyzer.application.use_cases.export_study_report import ExportStudyReport
from power_fault_analyzer.application.use_cases.network_editing import (
    AddBusToNetwork,
    AddLineBetweenBuses,
    AddSynchronousGeneratorToNetwork,
    AddTheveninEquivalentSourceToNetwork,
    RemoveBusFromNetwork,
    RemoveEquipmentFromNetwork,
    SetSwitchPosition,
    UpdateBusInNetwork,
)
from power_fault_analyzer.application.use_cases.project_workspace import ProjectWorkspaceService
from power_fault_analyzer.application.use_cases.reference_network_template import (
    BuildReferenceNetworkTemplate,
)
from power_fault_analyzer.application.use_cases.resolve_substation_boundary import (
    ResolveLineBoundary,
    ResolveTransformerBoundary,
)
from power_fault_analyzer.application.use_cases.run_network_short_circuit_study import (
    RunNetworkShortCircuitStudy,
)
from power_fault_analyzer.application.use_cases.substation_engineering import (
    BuildPFAES001Substation,
)
from power_fault_analyzer.infrastructure.adapters.engineering_report_exporter_adapter import (
    EngineeringReportExporterAdapter,
)
from power_fault_analyzer.infrastructure.adapters.sequence_network_set_factory_adapter import (
    SequenceNetworkSetFactoryAdapter,
)
from power_fault_analyzer.infrastructure.adapters.short_circuit_solver_adapter import (
    NumericalShortCircuitSolverAdapter,
)
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)
from power_fault_analyzer.infrastructure.persistence.json_project_repository import (
    JSONProjectRepository,
)


@dataclass(frozen=True, slots=True)
class WorkbenchApplicationServices:
    project_workspace: ProjectWorkspaceService
    network_document_repository: JSONNetworkDocumentRepository
    add_bus: AddBusToNetwork
    remove_bus: RemoveBusFromNetwork
    add_generator: AddSynchronousGeneratorToNetwork
    add_equivalent_source: AddTheveninEquivalentSourceToNetwork
    add_line: AddLineBetweenBuses
    remove_equipment: RemoveEquipmentFromNetwork
    set_switch_position: SetSwitchPosition
    update_bus: UpdateBusInNetwork
    build_reference_template: BuildReferenceNetworkTemplate
    build_pfa_es001_substation: BuildPFAES001Substation
    resolve_line_boundary: ResolveLineBoundary
    resolve_transformer_boundary: ResolveTransformerBoundary
    run_network_fault_study: RunNetworkShortCircuitStudy
    export_report: ExportStudyReport


def build_workbench_services() -> WorkbenchApplicationServices:
    solver = NumericalShortCircuitSolverAdapter()
    return WorkbenchApplicationServices(
        project_workspace=ProjectWorkspaceService(JSONProjectRepository()),
        network_document_repository=JSONNetworkDocumentRepository(),
        add_bus=AddBusToNetwork(),
        remove_bus=RemoveBusFromNetwork(),
        add_generator=AddSynchronousGeneratorToNetwork(),
        add_equivalent_source=AddTheveninEquivalentSourceToNetwork(),
        add_line=AddLineBetweenBuses(),
        remove_equipment=RemoveEquipmentFromNetwork(),
        set_switch_position=SetSwitchPosition(),
        update_bus=UpdateBusInNetwork(),
        build_reference_template=BuildReferenceNetworkTemplate(),
        build_pfa_es001_substation=BuildPFAES001Substation(),
        resolve_line_boundary=ResolveLineBoundary(),
        resolve_transformer_boundary=ResolveTransformerBoundary(),
        run_network_fault_study=RunNetworkShortCircuitStudy(
            solver, SequenceNetworkSetFactoryAdapter()
        ),
        export_report=ExportStudyReport(EngineeringReportExporterAdapter()),
    )
