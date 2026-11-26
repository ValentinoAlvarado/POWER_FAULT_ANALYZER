[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PreviousLocation = Get-Location
$PreviousPythonPath = $env:PYTHONPATH
$PreviousQtPlatform = $env:QT_QPA_PLATFORM

function Invoke-PfaPythonGate {
    param([string]$Name, [string[]]$Arguments)
    Write-Host "`n== $Name ==" -ForegroundColor Cyan
    & $script:Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
    Write-Host "$Name : PASS" -ForegroundColor Green
}

try {
    Set-Location $RepositoryRoot
    $env:PYTHONPATH = Join-Path $RepositoryRoot 'src'
    $env:QT_QPA_PLATFORM = 'offscreen'
    $script:Python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $script:Python)) {
        $script:Python = (Get-Command python -ErrorAction Stop).Source
    }

    $Touched = @(
        'src/power_fault_analyzer/application/use_cases/network_workspace.py',
        'src/power_fault_analyzer/application/use_cases/resolve_substation_boundary.py',
        'src/power_fault_analyzer/infrastructure/persistence/json_network_document_repository.py',
        'src/power_fault_analyzer/interfaces/desktop/icon_theme.py',
        'src/power_fault_analyzer/interfaces/desktop/workbench/network_canvas.py',
        'src/power_fault_analyzer/interfaces/desktop/workbench/qet_symbol_browser.py',
        'src/power_fault_analyzer/interfaces/desktop/workbench/workbench_window.py',
        'tests/unit/application/test_pfa_es001_substation.py',
        'tests/unit/application/test_pfa_es002_boundary_resolution.py',
        'tests/unit/application/test_workbench_network_workspace.py',
        'scripts/smoke_test_pfa_es001.py'
    )
    foreach ($File in $Touched) {
        if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot $File))) {
            throw "Required UI foundation file is missing: $File"
        }
    }

    Invoke-PfaPythonGate 'Ruff lint — UI foundation' (@('-m', 'ruff', 'check') + $Touched)
    Invoke-PfaPythonGate 'Ruff format — UI foundation' (@('-m', 'ruff', 'format', '--check') + $Touched)
    Invoke-PfaPythonGate 'Compileall' @('-m', 'compileall', '-q', 'src', 'tests', 'scripts')
    Invoke-PfaPythonGate 'Full regression suite' @('-m', 'pytest', '-q')
    Invoke-PfaPythonGate 'PFA-ES-001 Qt smoke with busbar rotation' @('scripts/smoke_test_pfa_es001.py')
    Invoke-PfaPythonGate 'PFA-ES-002 end-to-end smoke' @('scripts/smoke_test_pfa_es002.py')

    Write-Host "`nUI FOUNDATION: ALL LOCAL GATES PASSED" -ForegroundColor Green
}
finally {
    if ($null -eq $PreviousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $PreviousPythonPath
    }
    if ($null -eq $PreviousQtPlatform) {
        Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    } else {
        $env:QT_QPA_PLATFORM = $PreviousQtPlatform
    }
    Set-Location $PreviousLocation
}
