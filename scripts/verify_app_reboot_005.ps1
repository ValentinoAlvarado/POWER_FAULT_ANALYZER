[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}
Set-Location $RepositoryRoot

function Invoke-Checked {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "== $Name ==" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

Invoke-Checked 'Ruff, compilation, full test suite and pinned QET renderer' {
    & (Join-Path $PSScriptRoot 'verify_qet_symbol_importer.ps1')
}
Invoke-Checked 'Compile source, tests and scripts' {
    & $Python -m compileall -q src tests scripts
}
Invoke-Checked 'APP-REBOOT-005 visual workspace and source-library acceptance' {
    & $Python (Join-Path $PSScriptRoot 'smoke_test_app_reboot_005.py')
}
Write-Host 'APP-REBOOT-005 verification completed successfully.' -ForegroundColor Green
