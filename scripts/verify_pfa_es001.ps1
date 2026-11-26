[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepositoryRoot

function Invoke-PythonChecked {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    Write-Host "`n== $Name ==" -ForegroundColor Cyan
    & $script:Python @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode."
    }
    Write-Host "$Name : PASS" -ForegroundColor Green
}

$script:Python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $script:Python)) {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $script:Python = $pythonCommand.Source
}

$pythonVersion = & $script:Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to identify the selected Python interpreter.'
}
if ($pythonVersion -ne '3.13') {
    throw "PFA-ES-001 requires Python 3.13; detected $pythonVersion."
}
Write-Host "Python: $(& $script:Python --version 2>&1)" -ForegroundColor Green

$changedPython = @(
    'src/power_fault_analyzer/application/use_cases/network_editing.py'
    'src/power_fault_analyzer/application/use_cases/network_workspace.py'
    'src/power_fault_analyzer/application/use_cases/substation_engineering.py'
    'src/power_fault_analyzer/bootstrap/workbench_container.py'
    'src/power_fault_analyzer/domain/aggregates/network.py'
    'src/power_fault_analyzer/domain/entities/bus.py'
    'src/power_fault_analyzer/domain/enums/bus_kind.py'
    'src/power_fault_analyzer/domain/enums/equipment_interface.py'
    'src/power_fault_analyzer/domain/enums/switching_device.py'
    'src/power_fault_analyzer/equipment/interfaces/__init__.py'
    'src/power_fault_analyzer/equipment/interfaces/unresolved_equipment.py'
    'src/power_fault_analyzer/equipment/switching/__init__.py'
    'src/power_fault_analyzer/equipment/switching/switching_device.py'
    'src/power_fault_analyzer/infrastructure/persistence/json_network_document_repository.py'
    'src/power_fault_analyzer/interfaces/desktop/workbench/network_canvas.py'
    'src/power_fault_analyzer/interfaces/desktop/workbench/workbench_window.py'
    'src/power_fault_analyzer/network/sequence_networks/builder.py'
    'scripts/smoke_test_pfa_es001.py'
    'tests/unit/application/test_pfa_es001_substation.py'
    'tests/unit/application/test_workbench_network_workspace.py'
)
foreach ($relativePath in $changedPython) {
    if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot $relativePath))) {
        throw "Expected PFA-ES-001 file is missing: $relativePath"
    }
}

$ruffCheckArguments = @('-m', 'ruff', 'check') + $changedPython
Invoke-PythonChecked -Name 'Ruff lint — touched Python files' -Arguments $ruffCheckArguments

$ruffFormatArguments = @('-m', 'ruff', 'format', '--check') + $changedPython
Invoke-PythonChecked -Name 'Ruff format — touched Python files' -Arguments $ruffFormatArguments

$compileArguments = @('-m', 'compileall', '-q') + @(
    'src/power_fault_analyzer/application/use_cases/network_editing.py'
    'src/power_fault_analyzer/application/use_cases/network_workspace.py'
    'src/power_fault_analyzer/application/use_cases/substation_engineering.py'
    'src/power_fault_analyzer/bootstrap/workbench_container.py'
    'src/power_fault_analyzer/domain/aggregates/network.py'
    'src/power_fault_analyzer/domain/entities/bus.py'
    'src/power_fault_analyzer/domain/enums/bus_kind.py'
    'src/power_fault_analyzer/domain/enums/equipment_interface.py'
    'src/power_fault_analyzer/domain/enums/switching_device.py'
    'src/power_fault_analyzer/equipment/interfaces'
    'src/power_fault_analyzer/equipment/switching'
    'src/power_fault_analyzer/infrastructure/persistence/json_network_document_repository.py'
    'src/power_fault_analyzer/interfaces/desktop/workbench/network_canvas.py'
    'src/power_fault_analyzer/interfaces/desktop/workbench/workbench_window.py'
    'src/power_fault_analyzer/network/sequence_networks/builder.py'
    'scripts/smoke_test_pfa_es001.py'
)
Invoke-PythonChecked -Name 'Compileall — PFA-ES-001 touched modules' -Arguments $compileArguments

$pytestArguments = @('-m', 'pytest', '-q') + @(
    'tests/unit/application/test_pfa_es001_substation.py'
    'tests/unit/application/test_workbench_network_workspace.py'
    'tests/unit/network/sequence_networks/test_sequence_network_builder.py'
    'tests/unit/infrastructure/symbols/test_qet_catalog.py'
    'tests/unit/infrastructure/symbols/test_qet_elmt.py'
    'tests/unit/interfaces/desktop/workbench/test_qet_symbol_item.py'
)
Invoke-PythonChecked -Name 'Targeted regression tests — topology, persistence, QET and workspace' -Arguments $pytestArguments

$env:QT_QPA_PLATFORM = 'offscreen'
$qtFontDirectory = Join-Path $env:WINDIR 'Fonts'
if (Test-Path -LiteralPath $qtFontDirectory) {
    $env:QT_QPA_FONTDIR = $qtFontDirectory
}

# The project uses a src/ layout and may not be installed in the selected
# interpreter. Expose the repository source tree for this direct script run.
$previousPythonPath = $env:PYTHONPATH
$sourceRoot = Join-Path $RepositoryRoot 'src'
if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $env:PYTHONPATH = $sourceRoot
} else {
    $env:PYTHONPATH = "$sourceRoot;$previousPythonPath"
}
try {
    Invoke-PythonChecked -Name 'PFA-ES-001 desktop smoke — Qt offscreen' -Arguments @('scripts/smoke_test_pfa_es001.py')
}
finally {
    if ($null -eq $previousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $previousPythonPath
    }
}

Write-Host "`nPFA-ES-001 VERIFICATION: ALL LOCAL GATES PASSED" -ForegroundColor Green
Write-Host 'This verifier does not run the full repository test suite or claim an external electrical benchmark.'
Write-Host 'Study calculation remains correctly blocked until unresolved line and transformer data are supplied.'
