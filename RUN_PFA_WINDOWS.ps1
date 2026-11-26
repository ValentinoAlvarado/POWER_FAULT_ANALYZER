[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python 3.13 virtual environment not found: $Python`nCreate .venv and install: python -m pip install -e '.[dev,desktop,reports]'"
}
$env:PYTHONPATH = (Join-Path $Root 'src') + ';' + $env:PYTHONPATH
& $Python -m power_fault_analyzer.interfaces.desktop.app
if ($LASTEXITCODE -ne 0) { throw "POWER_FAULT_ANALYZER exited with code $LASTEXITCODE." }
