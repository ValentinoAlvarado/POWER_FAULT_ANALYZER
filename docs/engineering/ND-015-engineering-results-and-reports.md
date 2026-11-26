# ND-015 — Engineering Results & Reports

## Objective

ND-015 adds a presentation and export layer over solver outputs already produced by
POWER_FAULT_ANALYZER. It does not recalculate electrical quantities. Its job is to
normalize, preserve, and communicate the supplied results with units, phasor angles,
availability status, calculation references, diagnostics, and limitations.

## Implemented capabilities

| Requirement from the project directive | Implementation |
|---|---|
| Phase fault currents | A-B-C complex phasors in pu and kA, including magnitude and angle |
| Voltages during the fault | A-B-C complex phase-to-neutral phasors in pu and kV |
| Sequence results | Zero, positive, negative currents and voltages; Thevenin impedances and prefault voltage when present |
| Source contributions | Per-source phase and sequence phasors from `IEC60909SourceContributionAnalysis` |
| Results by bus | Bus UUID and bus name (when a `NetworkAggregate` is supplied) |
| Results at an interior line fault | Line ID/name, fault fraction, distances from each terminal, and fault-node result |
| Line terminal currents | Both line terminal phase currents, retaining the defined current-into-line direction |
| IEC quantities | Value, unit, calculated/unavailable/not-reported state, method reference, and reason |
| Correction factors | Factor name/value; source provenance is explicitly marked unavailable when the result contract does not contain it |
| PDF report | Paginated technical report with fault summary, phase/sequence results, IEC quantities, source/branch data, corrections, diagnostics, assumptions, and limitations |
| Excel report | Multi-sheet workbook with filters, frozen header rows, and unit-labelled tables |
| CSV export | UTF-8-with-BOM CSV per report table for Excel and data pipelines |
| JSON export | Versioned structured JSON preserving complex values as real/imaginary/magnitude/angle |

## Public API

Build a report from a bus fault:

```python
from power_fault_analyzer.results import EngineeringStudyReportBuilder
from power_fault_analyzer.reporting import EngineeringReportGenerator

builder = EngineeringStudyReportBuilder(
    project_name="POWER_FAULT_ANALYZER",
    study_name="Maximum short-circuit study",
    network=network,
)
builder.add_iec60909_result(iec_result, location_name="BUS-13.8")
report = builder.build()

files = EngineeringReportGenerator().export_all(report, "artifacts/reports")
```

For per-source contribution rows, add the matching analysis before building:

```python
builder.add_source_contribution_analysis(source_analysis)
```

For an interior-line fault:

```python
builder.add_line_fault_result(line_fault_result)
```

The builder links source and branch rows to the referenced fault ID. Duplicate fault IDs,
mixed standard editions, and orphaned source/branch rows are rejected.

## Output layout

`EngineeringReportGenerator.export_all()` writes:

- `engineering_report.pdf`
- `engineering_results.xlsx`
- `engineering_results.json`
- `csv/study.csv`
- `csv/faults.csv`
- `csv/phases.csv`
- `csv/sequences.csv`
- `csv/iec_quantities.csv`
- `csv/sources.csv`
- `csv/source_balance.csv`
- `csv/branches.csv`
- `csv/corrections.csv`
- `csv/diagnostics.csv`

PDF and Excel dependencies are optional and loaded only when those exporters run. Install
both with:

```powershell
python -m pip install -e ".[reports]"
```

JSON and CSV use the Python standard library and do not require the optional reporting extra.

## Explicit engineering boundaries

1. The reporting layer does not synthesize branch currents from bus voltages or Ybus
   off-diagonal entries. Such a reconstruction would require the exact branch primitive
   model, tap ratio, phase shift, shunts, mutual coupling, and terminal orientation.
2. The current solver contracts expose both terminal currents for an interior-line fault;
   those six phase records are included. They are **not** a complete network-wide branch
   current solution.
3. Transformer winding through-currents are not yet present in the solver result contracts.
   No transformer current is fabricated in the report. The limitation is included in the
   report metadata and in PDF/JSON/CSV outputs.
4. Source contributions are included only when a matching source analysis object is supplied.
   They preserve the physical superposition model and do not imply IEC source correction
   unless that correction was actually applied upstream.
5. A supplementary engineering estimate (for example the single-Thevenin R-L DC waveform)
   is labelled `supplementary`; it is never merged into an unavailable normative IEC quantity.
6. Source contribution phase/sequence balance residuals and their analysis method ID are
   included whenever a source-analysis object is supplied.
7. Missing values are not exported as numerical zero. IEC quantities have explicit
   `calculated`, `unavailable`, or `not_reported` states.
8. IEC study settings (voltage factor, equivalent voltage, fault duration, frequency, and
   first-pole separation time where supplied) are retained in the fault record.
9. The report timestamp is timezone-aware and serialized in UTC. Tests inject a fixed time
   to keep report generation reproducible.

## Verification

ND-015 adds 12 tests covering normalization, phasor preservation, bus/line location,
source linkage, IEC availability state, JSON, CSV, XLSX, and PDF output. The baseline
ND-014 regression count is retained.

The deliverable validator runs Ruff lint, repository-wide format checking, compileall,
and the full pytest suite. PDF/XLSX exporter tests require the `reports` extra.


## Spreadsheet safety and schema stability

CSV and XLSX use a fixed column schema for every table, including empty tables and
partially populated sequence phasors. Missing phasors remain blank rather than being
coerced to numerical zero. Text beginning with spreadsheet formula introducers is escaped
in CSV/XLSX exports; JSON retains the original text value.
