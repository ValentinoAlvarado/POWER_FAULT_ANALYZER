import csv
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.reporting import (
    CSVReportExporter,
    EngineeringReportGenerator,
    ExcelReportExporter,
    JSONReportExporter,
    PDFReportExporter,
    report_to_dict,
)
from power_fault_analyzer.results import EngineeringStudyReportBuilder


def make_report(study_name="Three-phase bus fault", *, include_sequence_data=True):
    bus_id = uuid4()
    result = ShortCircuitResult(
        fault_type=FaultType.THREE_PHASE,
        bus_id=bus_id,
        fault_impedance_pu=0j,
        base_power_mva=100.0,
        base_voltage_kv=13.8,
        base_current_ka=4.184,
        prefault_sequence_voltages_pu=(
            {SequenceType.POSITIVE: 1 + 0j} if include_sequence_data else {}
        ),
        driving_point_impedances_pu=(
            {SequenceType.ZERO: 0.3 + 0.6j, SequenceType.POSITIVE: 0.1 + 0.2j}
            if include_sequence_data
            else {}
        ),
        sequence_currents_pu=({SequenceType.POSITIVE: 5 - 10j} if include_sequence_data else {}),
        sequence_fault_voltages_pu=(
            {SequenceType.ZERO: 0j, SequenceType.POSITIVE: 0j} if include_sequence_data else {}
        ),
        phase_currents_pu=(5 - 10j, (-11.16 + 0.67j), (6.16 + 9.33j)),
        phase_voltages_pu=(0j, 0j, 0j),
        phase_currents_ka=(20.92 - 41.84j, -46.69 + 2.80j, 25.77 + 39.02j),
        phase_voltages_kv=(0j, 0j, 0j),
    )
    return (
        EngineeringStudyReportBuilder(
            project_name="POWER_FAULT_ANALYZER",
            study_name=study_name,
            generated_at=datetime(2026, 11, 22, 12, 0, tzinfo=UTC),
        )
        .add_short_circuit_result(result, location_name="BUS-13.8")
        .build()
    )


def test_json_export_is_complete_unit_labelled_and_parseable(tmp_path):
    report = make_report()
    path = JSONReportExporter().export(report, tmp_path / "results.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["metadata"]["project_name"] == "POWER_FAULT_ANALYZER"
    assert payload["faults"][0]["phases"][0]["phase"] == "A"
    assert payload["faults"][0]["base"]["voltage_kv_line_to_line"] == 13.8
    assert payload["faults"][0]["phases"][0]["voltage_kv_line_to_neutral"]["magnitude"] == 0.0
    assert report_to_dict(report)["schema_version"] == "1.0"


def test_csv_export_writes_all_tables_with_headers_when_empty(tmp_path):
    outputs = CSVReportExporter().export(make_report(), tmp_path / "csv")
    assert set(outputs) == {
        "Study",
        "Faults",
        "Phases",
        "Sequences",
        "IEC Quantities",
        "Sources",
        "Source Balance",
        "Branches",
        "Corrections",
        "Diagnostics",
    }
    assert outputs["Faults"].exists()
    with outputs["Phases"].open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3
    assert rows[0]["phase"] == "A"
    with outputs["Branches"].open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        assert "current_ka_magnitude" in reader.fieldnames
        assert list(reader) == []


def test_excel_export_creates_expected_worksheets_and_freeze_panes(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = ExcelReportExporter().export(make_report(), tmp_path / "results.xlsx")
    workbook = openpyxl.load_workbook(path, read_only=False)
    assert {
        "Study",
        "Faults",
        "Phases",
        "Sequences",
        "IEC Quantities",
        "Source Balance",
        "Branches",
    }.issubset(workbook.sheetnames)
    assert workbook["Phases"].freeze_panes == "A2"
    assert workbook["Phases"].max_row == 4


def test_pdf_export_creates_readable_pdf_file(tmp_path):
    pytest.importorskip("reportlab")
    path = PDFReportExporter().export(make_report(), tmp_path / "report.pdf")
    assert path.read_bytes().startswith(b"%PDF-")
    assert path.stat().st_size > 1000


def test_export_all_generates_json_csv_excel_and_pdf(tmp_path):
    pytest.importorskip("openpyxl")
    pytest.importorskip("reportlab")
    files = EngineeringReportGenerator().export_all(make_report(), tmp_path / "all")
    assert files.json_path.exists()
    assert len(files.csv_paths) == 10
    assert files.excel_path is not None and files.excel_path.exists()
    assert files.pdf_path is not None and files.pdf_path.exists()


def test_export_all_can_skip_optional_document_formats(tmp_path):
    files = EngineeringReportGenerator().export_all(
        make_report(), tmp_path / "data-only", include_pdf=False, include_excel=False
    )
    assert files.json_path.exists()
    assert files.excel_path is None
    assert files.pdf_path is None


def test_sequence_table_keeps_a_stable_schema_and_preserves_missing_values(tmp_path):
    report = make_report()
    outputs = CSVReportExporter().export(report, tmp_path / "sequence-csv")
    with outputs["Sequences"].open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    zero = next(row for row in rows if row["sequence"] == "zero")
    assert zero["current_pu_magnitude"] == ""
    assert zero["voltage_pu_magnitude"] == "0.0"

    payload = json.loads(
        JSONReportExporter().export(report, tmp_path / "sequence.json").read_text()
    )
    zero_json = next(
        item for item in payload["faults"][0]["sequences"] if item["sequence"] == "zero"
    )
    assert zero_json["current_pu"] is None
    assert zero_json["voltage_pu"]["magnitude"] == 0.0


def test_csv_and_excel_exports_treat_formula_like_user_text_as_literal(tmp_path):
    formula_like_name = '=HYPERLINK("https://example.invalid","open")'
    report = make_report(study_name=formula_like_name)

    csv_outputs = CSVReportExporter().export(report, tmp_path / "safe-csv")
    with csv_outputs["Study"].open(encoding="utf-8-sig", newline="") as stream:
        study_rows = list(csv.DictReader(stream))
    study_name_row = next(row for row in study_rows if row["field"] == "study_name")
    assert study_name_row["value"].startswith("'=")

    openpyxl = pytest.importorskip("openpyxl")
    workbook_path = ExcelReportExporter().export(report, tmp_path / "safe.xlsx")
    workbook = openpyxl.load_workbook(workbook_path, data_only=False)
    study_sheet = workbook["Study"]
    row_index = next(
        row
        for row in range(2, study_sheet.max_row + 1)
        if study_sheet.cell(row, 1).value == "study_name"
    )
    cell = study_sheet.cell(row_index, 2)
    assert cell.data_type == "s"
    assert cell.value.startswith("'=")


def test_empty_report_tables_still_export_their_full_schema(tmp_path):
    report = make_report(include_sequence_data=False)
    csv_outputs = CSVReportExporter().export(report, tmp_path / "empty-sequences")
    with csv_outputs["Sequences"].open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        assert "current_pu_magnitude" in reader.fieldnames
        assert "prefault_voltage_pu_angle_deg" in reader.fieldnames
        assert list(reader) == []

    openpyxl = pytest.importorskip("openpyxl")
    workbook_path = ExcelReportExporter().export(report, tmp_path / "empty-sequences.xlsx")
    workbook = openpyxl.load_workbook(workbook_path, read_only=True)
    worksheet = workbook["Sequences"]
    headers = next(worksheet.iter_rows(values_only=True))
    assert "current_pu_magnitude" in headers
    assert "prefault_voltage_pu_angle_deg" in headers
    assert worksheet.max_row == 1
