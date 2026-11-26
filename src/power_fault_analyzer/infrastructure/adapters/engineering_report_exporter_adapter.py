"""Hexagonal adapter for the existing PDF/XLSX/CSV/JSON report generator."""

from __future__ import annotations

from pathlib import Path

from power_fault_analyzer.application.ports.study_report_exporter import ExportedStudyReport
from power_fault_analyzer.reporting.report_generator import EngineeringReportGenerator
from power_fault_analyzer.results.result_models import EngineeringStudyReport


class EngineeringReportExporterAdapter:
    def __init__(self, generator: EngineeringReportGenerator | None = None) -> None:
        self._generator = generator or EngineeringReportGenerator()

    def export(
        self,
        report: EngineeringStudyReport,
        directory: str | Path,
        *,
        include_pdf: bool = True,
        include_excel: bool = True,
    ) -> ExportedStudyReport:
        files = self._generator.export_all(
            report,
            directory,
            include_pdf=include_pdf,
            include_excel=include_excel,
        )
        return ExportedStudyReport(
            json_path=files.json_path,
            csv_paths=files.csv_paths,
            excel_path=files.excel_path,
            pdf_path=files.pdf_path,
        )
