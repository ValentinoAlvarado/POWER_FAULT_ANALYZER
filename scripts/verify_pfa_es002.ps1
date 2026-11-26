[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PreviousLocation = Get-Location
$PreviousPythonPath = $env:PYTHONPATH
$PreviousQtPlatform = $env:QT_QPA_PLATFORM
$PreviousQtFontDirectory = $env:QT_QPA_FONTDIR

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

try {
    Set-Location $RepositoryRoot
    $SourcePath = Join-Path $RepositoryRoot 'src'
    if ([string]::IsNullOrWhiteSpace($PreviousPythonPath)) {
        $env:PYTHONPATH = $SourcePath
    }
    else {
        $env:PYTHONPATH = $SourcePath + [IO.Path]::PathSeparator + $PreviousPythonPath
    }
    $env:QT_QPA_PLATFORM = 'offscreen'

    $qtFontDirectory = Join-Path $env:WINDIR 'Fonts'
    if (Test-Path -LiteralPath $qtFontDirectory) {
        $env:QT_QPA_FONTDIR = $qtFontDirectory
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
        throw "PFA-ES-002 requires Python 3.13; detected $pythonVersion."
    }
    Write-Host "Python: $(& $script:Python --version 2>&1)" -ForegroundColor Green

    $TouchedPython = @(
        'src/power_fault_analyzer/application/use_cases/resolve_substation_boundary.py'
        'src/power_fault_analyzer/application/use_cases/run_network_short_circuit_study.py'
        'src/power_fault_analyzer/bootstrap/workbench_container.py'
        'src/power_fault_analyzer/equipment/sources/equivalent_source.py'
        'src/power_fault_analyzer/equipment/transmission/line.py'
        'src/power_fault_analyzer/equipment/transformers/two_winding_transformer.py'
        'src/power_fault_analyzer/infrastructure/numerical/short_circuit.py'
        'src/power_fault_analyzer/infrastructure/persistence/json_network_document_repository.py'
        'src/power_fault_analyzer/interfaces/desktop/workbench/dialogs.py'
        'src/power_fault_analyzer/interfaces/desktop/workbench/workbench_window.py'
        'src/power_fault_analyzer/network/sequence_networks/builder.py'
        'src/power_fault_analyzer/network/sequence_networks/models.py'
        'tests/unit/application/test_pfa_es001_substation.py'
        'tests/unit/application/test_pfa_es002_boundary_resolution.py'
        'tests/unit/application/test_workbench_network_workspace.py'
        'tests/unit/infrastructure/numerical/test_short_circuit.py'
        'scripts/smoke_test_pfa_es002.py'
    )

    foreach ($relativePath in $TouchedPython) {
        if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot $relativePath))) {
            throw "Expected PFA-ES-002 file is missing: $relativePath"
        }
    }

    $ruffCheckArguments = @('-m', 'ruff', 'check') + $TouchedPython
    Invoke-PythonChecked -Name 'Ruff lint — PFA-ES-002 touched Python files' -Arguments $ruffCheckArguments

    $ruffFormatArguments = @('-m', 'ruff', 'format', '--check') + $TouchedPython
    Invoke-PythonChecked -Name 'Ruff format — PFA-ES-002 touched Python files' -Arguments $ruffFormatArguments

    Invoke-PythonChecked -Name 'Compileall — src, tests and scripts' -Arguments @('-m', 'compileall', '-q', 'src', 'tests', 'scripts')
    Invoke-PythonChecked -Name 'Full repository regression suite' -Arguments @('-m', 'pytest', '-q')
    Invoke-PythonChecked -Name 'PFA-ES-001 Qt desktop smoke — offscreen' -Arguments @('scripts/smoke_test_pfa_es001.py')
    Invoke-PythonChecked -Name 'PFA-ES-002 boundary, study and export smoke' -Arguments @('scripts/smoke_test_pfa_es002.py')

    Write-Host "`nPFA-ES-002 VERIFICATION: ALL LOCAL GATES PASSED" -ForegroundColor Green
    Write-Host 'The smoke scenario uses synthetic test fixtures and is not real substation data.'
    Write-Host 'This does not claim IEC 60909 compliance or external electrical benchmark validation.'
}
finally {
    if ($null -eq $PreviousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $PreviousPythonPath
    }

    if ($null -eq $PreviousQtPlatform) {
        Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    }
    else {
        $env:QT_QPA_PLATFORM = $PreviousQtPlatform
    }

    if ($null -eq $PreviousQtFontDirectory) {
        Remove-Item Env:QT_QPA_FONTDIR -ErrorAction SilentlyContinue
    }
    else {
        $env:QT_QPA_FONTDIR = $PreviousQtFontDirectory
    }
    Set-Location $PreviousLocation
}
