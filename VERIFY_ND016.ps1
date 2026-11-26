$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath 'pyproject.toml')) {
    throw 'Run this validator from the POWER_FAULT_ANALYZER repository root.'
}

$ChangedPython = @(
    'src/power_fault_analyzer/validation/__init__.py',
    'src/power_fault_analyzer/validation/__main__.py',
    'src/power_fault_analyzer/validation/models.py',
    'src/power_fault_analyzer/validation/reference_cases.py',
    'src/power_fault_analyzer/validation/benchmark_runner.py',
    'src/power_fault_analyzer/validation/electrical_checks.py',
    'src/power_fault_analyzer/validation/sensitivity.py',
    'src/power_fault_analyzer/validation/external_reference.py',
    'src/power_fault_analyzer/validation/cli.py',
    'tests/unit/validation/test_nd016_validation.py',
    'scripts/run_nd016_validation.py'
)

Write-Host '1/8 - Formatting ND-016 Python files...'
python -m ruff format @ChangedPython
if ($LASTEXITCODE -ne 0) { throw 'Ruff format failed.' }

Write-Host '2/8 - Applying Ruff safe fixes to ND-016 files only (no unsafe fixes)...'
python -m ruff check --fix @ChangedPython
if ($LASTEXITCODE -ne 0) { throw 'Ruff safe fixes left lint errors; no unsafe fixes were used.' }

Write-Host '3/8 - Formatting ND-016 files after lint fixes...'
python -m ruff format @ChangedPython
if ($LASTEXITCODE -ne 0) { throw 'Ruff format after fixes failed.' }

Write-Host '4/8 - Running repository-wide Ruff lint...'
python -m ruff check src tests
if ($LASTEXITCODE -ne 0) { throw 'Repository Ruff lint failed.' }

Write-Host '5/8 - Checking repository-wide formatting...'
python -m ruff format --check src tests
if ($LASTEXITCODE -ne 0) { throw 'Repository Ruff format check failed.' }

Write-Host '6/8 - Compiling source, tests and scripts...'
python -m compileall -q src tests scripts
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }

Write-Host '7/8 - Running full regression suite...'
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Pytest regression failed.' }

Write-Host '8/8 - Running ND-016 analytical benchmarks, electrical audits and sensitivity...'
$ReportPath = Join-Path (Get-Location).Path 'outputs\nd016-validation-report.json'
$ReportDirectory = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null
python -m power_fault_analyzer.validation --json $ReportPath
if ($LASTEXITCODE -ne 0) { throw 'ND-016 validation suite failed.' }
python -c "import json,sys; r=json.load(open(sys.argv[1],encoding='utf-8')); b=r['benchmark']; a=r['electrical_audits']; s=r['sensitivity']; ok=(r.get('passed') is True and b['passed_cases']==4 and b['total_cases']==4 and b['passed_comparisons']==44 and all(x['passed'] for x in a) and s['passed'] is True); print('ND-016 report integrity:', 'PASS' if ok else 'FAIL'); sys.exit(0 if ok else 1)" $ReportPath
if ($LASTEXITCODE -ne 0) { throw 'ND-016 JSON report integrity check failed.' }

Write-Host 'ND-016 validation completed successfully.' -ForegroundColor Green
