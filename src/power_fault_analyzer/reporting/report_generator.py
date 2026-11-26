"""Convenience facade for all engineering report export formats."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from types import MappingProxyType

from power_fault_analyzer.reporting.csv_exporter import CSVReportExporter
from power_fault_analyzer.reporting.excel_exporter import ExcelReportExporter
from power_fault_analyzer.reporting.json_exporter import JSONReportExporter
from power_fault_analyzer.reporting.pdf_exporter import PDFReportExporter
from power_fault_analyzer.results.result_models import EngineeringStudyReport


@dataclass(frozen=True, slots=True)
class EngineeringReportFiles:
    json_path: Path
    csv_paths: Mapping[str, Path]
    excel_path: Path | None = None
    pdf_path: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "csv_paths", MappingProxyType(dict(self.csv_paths)))


class EngineeringReportGenerator:
    """Export one normalized report to JSON/CSV and optional PDF/XLSX."""

    def __init__(self) -> None:
        self._json = JSONReportExporter()
        self._csv = CSVReportExporter()
        self._excel = ExcelReportExporter()
        self._pdf = PDFReportExporter()

    def export_all(
        self,
        report: EngineeringStudyReport,
        directory: str | Path,
        *,
        include_pdf: bool = True,
        include_excel: bool = True,
    ) -> EngineeringReportFiles:
        if not isinstance(include_pdf, bool) or not isinstance(include_excel, bool):
            raise TypeError("include_pdf and include_excel must be bool values.")
        if include_excel and find_spec("openpyxl") is None:
            raise RuntimeError(
                'Excel export requires openpyxl. Install with: pip install -e ".[reports]"'
            )
        if include_pdf and find_spec("reportlab") is None:
            raise RuntimeError(
                'PDF export requires reportlab. Install with: pip install -e ".[reports]"'
            )
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        json_path = self._json.export(report, target / "engineering_results.json")
        csv_paths = self._csv.export(report, target / "csv")
        excel_path = (
            self._excel.export(report, target / "engineering_results.xlsx")
            if include_excel
            else None
        )
        pdf_path = (
            self._pdf.export(report, target / "engineering_report.pdf") if include_pdf else None
        )
        return EngineeringReportFiles(
            json_path=json_path,
            csv_paths=csv_paths,
            excel_path=excel_path,
            pdf_path=pdf_path,
        )
