"""Output port and application DTO for engineering-report exports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from power_fault_analyzer.results.result_models import EngineeringStudyReport


@dataclass(frozen=True, slots=True)
class ExportedStudyReport:
    json_path: Path
    csv_paths: Mapping[str, Path]
    excel_path: Path | None = None
    pdf_path: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "csv_paths", MappingProxyType(dict(self.csv_paths)))


class StudyReportExporterPort(Protocol):
    def export(
        self,
        report: EngineeringStudyReport,
        directory: str | Path,
        *,
        include_pdf: bool = True,
        include_excel: bool = True,
    ) -> ExportedStudyReport: ...
