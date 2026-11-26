"""Excel workbook export. openpyxl is an optional reporting dependency."""

from __future__ import annotations

from pathlib import Path

from power_fault_analyzer.reporting.tables import (
    REPORT_TABLE_HEADERS,
    build_report_tables,
    spreadsheet_safe_value,
)
from power_fault_analyzer.results.result_models import EngineeringStudyReport


class ExcelReportExporter:
    """Create a multi-sheet XLSX engineering report."""

    def export(self, report: EngineeringStudyReport, path: str | Path) -> Path:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError as exc:
            raise RuntimeError(
                'Excel export requires the optional dependency. Install with: pip install -e ".[reports]"'
            ) from exc

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        default_sheet = workbook.active
        workbook.remove(default_sheet)
        for table_name, rows in build_report_tables(report).items():
            worksheet = workbook.create_sheet(title=table_name[:31])
            headers = list(REPORT_TABLE_HEADERS[table_name])
            worksheet.append(headers)
            for row in rows:
                worksheet.append([spreadsheet_safe_value(row.get(header)) for header in headers])
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="203864")
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            worksheet.row_dimensions[1].height = 30
            for column_index, header in enumerate(headers, start=1):
                width = min(max(len(str(header)) + 2, 14), 42)
                for row_index in range(2, worksheet.max_row + 1):
                    value = worksheet.cell(row_index, column_index).value
                    if value is not None:
                        width = min(max(width, len(str(value)) + 2), 42)
                worksheet.column_dimensions[get_column_letter(column_index)].width = width
            worksheet.sheet_view.showGridLines = False
        workbook.properties.title = report.metadata.study_name
        workbook.properties.subject = "POWER_FAULT_ANALYZER engineering results"
        workbook.properties.creator = "POWER_FAULT_ANALYZER"
        workbook.save(target)
        return target
