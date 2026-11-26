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

$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Creating Python 3.13 virtual environment...' -ForegroundColor Cyan
    & py -3.13 -m venv (Join-Path $repoRoot '.venv')
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create .venv with Python 3.13. Install the Python 3.13 launcher first.'
    }
}

$script:PythonExe = $venvPython
$pythonVersion = & $script:PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $pythonVersion.Trim() -ne '3.13') {
    throw "APP-001 requires Python 3.13; .venv reports '$pythonVersion'."
}

if (-not $SkipInstall) {
    Write-Host "`n== Install editable desktop + reports + development extras ==" -ForegroundColor Cyan
    & $script:PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
    & $script:PythonExe -m pip install -e '.[dev,desktop,reports]'
    if ($LASTEXITCODE -ne 0) { throw 'Editable installation of APP-001 dependencies failed.' }
}

Invoke-PythonGate -Name 'Ruff lint' -Arguments @('-m', 'ruff', 'check', 'src', 'tests')
Invoke-PythonGate -Name 'Ruff format check' -Arguments @('-m', 'ruff', 'format', '--check', 'src', 'tests')
Invoke-PythonGate -Name 'Compileall' -Arguments @('-m', 'compileall', '-q', 'src', 'tests', 'scripts')
Invoke-PythonGate -Name 'Complete Pytest suite' -Arguments @('-m', 'pytest', '-q')
Invoke-PythonGate -Name 'Desktop composition and Qt window construction' -Arguments @(
    '-c',
    'from PySide6.QtWidgets import QApplication; from power_fault_analyzer.bootstrap.desktop_container import build_desktop_services; from power_fault_analyzer.interfaces.desktop.main_window import MainWindow; app = QApplication([]); services = build_desktop_services(); window = MainWindow(services); assert window.windowTitle(); print(True)'
)

Write-Host "`nAPP-001 verification completed successfully." -ForegroundColor Green
