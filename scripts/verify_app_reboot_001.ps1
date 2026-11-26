[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

function Invoke-PythonGate {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    Write-Host "`n== $Name ==" -ForegroundColor Cyan
    & $script:PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

$script:PythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $script:PythonExe -PathType Leaf)) {
    Write-Host 'Creating Python 3.13 virtual environment...' -ForegroundColor Cyan
    & py -3.13 -m venv (Join-Path $repoRoot '.venv')
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create .venv with Python 3.13. Install the Python 3.13 launcher first.'
    }
}

$pythonVersion = & $script:PythonExe -c "import sys; print('{}.{}'.format(sys.version_info.major, sys.version_info.minor))"
if ($LASTEXITCODE -ne 0 -or $pythonVersion.Trim() -ne '3.13') {
    throw "APP-REBOOT-001 requires Python 3.13; .venv reports '$pythonVersion'."
}

if (-not $SkipInstall) {
    Write-Host "`n== Install editable desktop + reports + development extras ==" -ForegroundColor Cyan
    & $script:PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
    & $script:PythonExe -m pip install -e '.[dev,desktop,reports]'
    if ($LASTEXITCODE -ne 0) { throw 'Editable installation of APP-REBOOT-001 dependencies failed.' }
}

Invoke-PythonGate -Name 'Ruff lint' -Arguments @('-m', 'ruff', 'check', 'src', 'tests', 'scripts')
Invoke-PythonGate -Name 'Ruff format check' -Arguments @('-m', 'ruff', 'format', '--check', 'src', 'tests', 'scripts')
Invoke-PythonGate -Name 'Compileall' -Arguments @('-m', 'compileall', '-q', 'src', 'tests', 'scripts')
Invoke-PythonGate -Name 'Complete Pytest suite' -Arguments @('-m', 'pytest', '-q')

$previousQtPlatform = $env:QT_QPA_PLATFORM
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    Invoke-PythonGate -Name 'Qt Workbench + REF-3PH-001B end-to-end smoke test' `
        -Arguments @('scripts/smoke_test_workbench.py')
}
finally {
    if ($null -eq $previousQtPlatform) {
        Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    }
    else {
        $env:QT_QPA_PLATFORM = $previousQtPlatform
    }
}

Write-Host "`nAPP-REBOOT-001 verification completed successfully." -ForegroundColor Green
