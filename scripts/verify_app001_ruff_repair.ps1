[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$requiredPaths = @(
    'src\power_fault_analyzer\application\use_cases\run_thevenin_fault_study.py',
    'src\power_fault_analyzer\domain\projects\models.py',
    'src\power_fault_analyzer\interfaces\desktop\main_window.py',
    'tests\integration\test_desktop_application_use_cases.py',
    'scripts\verify_app001.ps1'
)

foreach ($relativePath in $requiredPaths) {
    $fullPath = Join-Path $repoRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "Required APP-001 file is missing: $relativePath"
    }
}

Write-Host 'APP-001 Ruff repair files are present.' -ForegroundColor Green
$verificationScript = Join-Path $repoRoot 'scripts\verify_app001.ps1'
if ($SkipInstall) {
    & $verificationScript -SkipInstall
} else {
    & $verificationScript
}

if ($LASTEXITCODE -ne 0) {
    throw "APP-001 verification failed with exit code $LASTEXITCODE."
}

Write-Host 'APP-001 Ruff repair verification completed.' -ForegroundColor Green
