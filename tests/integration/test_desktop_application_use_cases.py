from __future__ import annotations

import cmath
import math
from pathlib import Path

from power_fault_analyzer.application.use_cases.export_study_report import ExportStudyReport
from power_fault_analyzer.application.use_cases.run_thevenin_fault_study import (
    RunTheveninFaultStudy,
)
from power_fault_analyzer.domain.projects.models import Project
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


def test_desktop_use_case_executes_ref_3ph_through_production_solver(tmp_path: Path) -> None:
    project = Project.create("REF-3PH-001B Desktop Integration")
    execution = RunTheveninFaultStudy(
        NumericalShortCircuitSolverAdapter(), TheveninSequenceNetworkFactoryAdapter()
    ).execute(project)
    result = execution.result

    assert abs(abs(result.phase_currents_pu[0]) - 3.117347105392) < 1e-10
    assert abs(abs(result.phase_voltages_pu[0]) - 0.231713481890) < 1e-10
    assert abs(abs(result.phase_currents_ka[0]) - 13.042037611997) < 1e-9
    assert execution.report.metadata.project_name == project.name
    assert len(execution.report.faults) == 1
    assert len(execution.report.limitations) == 4
    assert execution.report.limitations[0].startswith(
        "This desktop study uses a single-bus Thevenin equivalent."
    )
    assert execution.report.limitations[0].endswith("network branch currents.")
    assert execution.report.limitations[1].startswith(
        "The calculation is a general symmetrical-components bus-fault study;"
    )
    assert execution.report.limitations[1].endswith("correction procedure is applied.")
    assert all(isinstance(item, str) for item in execution.report.limitations)
    assert len(execution.project.study_history) == 1

    repository = JSONProjectRepository()
    project_path = repository.save(execution.project, tmp_path / "benchmark.pfa")
    loaded = repository.load(project_path)
    assert len(loaded.study_history) == 1
    assert loaded.study_history[0].settings_snapshot == project.study_settings
    assert (
        loaded.study_history[0].driving_point_impedances_pu
        == execution.project.study_history[0].driving_point_impedances_pu
    )
    assert loaded.study_history[0].phase_currents_pu[0] == (
        result.phase_currents_pu[0].real,
        result.phase_currents_pu[0].imag,
    )


def test_desktop_report_use_case_exports_existing_report_models(tmp_path: Path) -> None:
    project = Project.create("Report export integration")
    execution = RunTheveninFaultStudy(
        NumericalShortCircuitSolverAdapter(), TheveninSequenceNetworkFactoryAdapter()
    ).execute(project)
    exporter = ExportStudyReport(EngineeringReportExporterAdapter())

    files = exporter.execute(execution.report, tmp_path, include_pdf=True, include_excel=True)

    assert files.json_path.is_file()
    assert files.excel_path is not None and files.excel_path.is_file()
    assert files.pdf_path is not None and files.pdf_path.is_file()
    assert files.csv_paths
    assert all(path.is_file() for path in files.csv_paths.values())


def test_production_solver_phase_currents_are_balanced() -> None:
    execution = RunTheveninFaultStudy(
        NumericalShortCircuitSolverAdapter(), TheveninSequenceNetworkFactoryAdapter()
    ).execute(Project.create("Balanced fault"))
    currents = execution.result.phase_currents_pu

    assert max(abs(abs(value) - abs(currents[0])) for value in currents) < 1e-12
    angles = sorted((math.degrees(cmath.phase(value)) % 360.0) for value in currents)
    assert abs((angles[1] - angles[0]) - 120.0) < 1e-9
    assert abs((angles[2] - angles[1]) - 120.0) < 1e-9


def test_desktop_use_case_routes_supported_fault_types_to_production_solver() -> None:
    from power_fault_analyzer.domain.enums.fault_type import FaultType
    from power_fault_analyzer.domain.projects.models import TheveninStudySettings

    for fault_type in (
        FaultType.THREE_PHASE,
        FaultType.SINGLE_LINE_TO_GROUND,
        FaultType.LINE_TO_LINE,
        FaultType.DOUBLE_LINE_TO_GROUND,
    ):
        project = Project.create(
            f"{fault_type.value} desktop study",
            study_settings=TheveninStudySettings(fault_type=fault_type),
        )
        execution = RunTheveninFaultStudy(
            NumericalShortCircuitSolverAdapter(),
            TheveninSequenceNetworkFactoryAdapter(),
        ).execute(project)
        assert execution.result.fault_type is fault_type
        assert len(execution.report.faults) == 1
        assert len(execution.project.study_history) == 1
