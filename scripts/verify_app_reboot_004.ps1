[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepositoryRoot

function Invoke-Checked {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "== $Name ==" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

Invoke-Checked 'Complete Ruff, compilation, test and QET verification' {
    & (Join-Path $PSScriptRoot 'verify_qet_symbol_importer.ps1')
}
Invoke-Checked 'APP-REBOOT-004 resizable workspace and drawing-symbol acceptance' {
    python scripts/smoke_test_app_reboot_004.py
}
Write-Host 'APP-REBOOT-004 verification completed successfully.' -ForegroundColor Green
