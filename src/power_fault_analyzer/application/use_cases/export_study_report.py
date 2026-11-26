"""Export one immutable engineering report through an output port."""

from __future__ import annotations

from pathlib import Path

from power_fault_analyzer.application.ports.study_report_exporter import (
    ExportedStudyReport,
    StudyReportExporterPort,
)
from power_fault_analyzer.results.result_models import EngineeringStudyReport


class ExportStudyReport:
    def __init__(self, exporter: StudyReportExporterPort) -> None:
        self._exporter = exporter

    def execute(
        self,
        report: EngineeringStudyReport,
        directory: str | Path,
        *,
        include_pdf: bool = True,
        include_excel: bool = True,
    ) -> ExportedStudyReport:
        return self._exporter.export(
            report,
            directory,
            include_pdf=include_pdf,
            include_excel=include_excel,
        )
