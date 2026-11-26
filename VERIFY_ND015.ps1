$ErrorActionPreference = 'Stop'

$Targets = @(
    'src/power_fault_analyzer/results/__init__.py',
    'src/power_fault_analyzer/results/branch_currents.py',
    'src/power_fault_analyzer/results/phasors.py',
    'src/power_fault_analyzer/results/report_builder.py',
    'src/power_fault_analyzer/results/result_models.py',
    'src/power_fault_analyzer/reporting/__init__.py',
    'src/power_fault_analyzer/reporting/csv_exporter.py',
    'src/power_fault_analyzer/reporting/excel_exporter.py',
    'src/power_fault_analyzer/reporting/json_exporter.py',
    'src/power_fault_analyzer/reporting/pdf_exporter.py',
    'src/power_fault_analyzer/reporting/report_generator.py',
    'src/power_fault_analyzer/reporting/tables.py',
    'tests/unit/results/test_report_builder.py',
    'tests/unit/reporting/test_exporters.py'
)

Write-Host '1/5 - Formatting the ND-015 Python files...'
python -m ruff format @Targets
if ($LASTEXITCODE -ne 0) { throw 'Ruff format failed.' }

Write-Host '2/5 - Running Ruff lint over src and tests...'
python -m ruff check src tests
if ($LASTEXITCODE -ne 0) { throw 'Ruff lint failed.' }

Write-Host '3/5 - Checking repository-wide formatting...'
python -m ruff format --check src tests
if ($LASTEXITCODE -ne 0) { throw 'Ruff format check failed.' }

Write-Host '4/5 - Compiling src and tests...'
python -m compileall -q src tests
if ($LASTEXITCODE -ne 0) { throw 'Compileall failed.' }

Write-Host '5/5 - Running the full regression suite...'
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Pytest failed.' }

Write-Host 'ND-015 validation commands completed successfully.'
