"""Multi-table CSV export for spreadsheet and data-science workflows."""

from __future__ import annotations

import csv
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from power_fault_analyzer.reporting.tables import (
    REPORT_TABLE_HEADERS,
    build_report_tables,
    spreadsheet_safe_value,
)
from power_fault_analyzer.results.result_models import EngineeringStudyReport


class CSVReportExporter:
    """Export one UTF-8 CSV file per report table."""

    def export(self, report: EngineeringStudyReport, directory: str | Path) -> Mapping[str, Path]:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        outputs: dict[str, Path] = {}
        for table_name, rows in build_report_tables(report).items():
            filename = re.sub(r"[^a-z0-9]+", "_", table_name.casefold()).strip("_") + ".csv"
            path = target / filename
            fieldnames = list(REPORT_TABLE_HEADERS[table_name])
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
                writer.writeheader()
                writer.writerows(
                    {key: spreadsheet_safe_value(value) for key, value in row.items()}
                    for row in rows
                )
            outputs[table_name] = path
        return MappingProxyType(outputs)
