[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$requiredPaths = @(
    'src\power_fault_analyzer\infrastructure\persistence\json_project_repository.py',
    'src\power_fault_analyzer\interfaces\desktop\app.py',
    'tests\integration\test_desktop_application_use_cases.py',
    'scripts\verify_app001.ps1'
)

foreach ($relativePath in $requiredPaths) {
    $fullPath = Join-Path $repoRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "Required APP-001 format-repair file is missing: $relativePath"
    }
}

Write-Host 'APP-001 format-repair files are present.' -ForegroundColor Green
$verificationScript = Join-Path $PSScriptRoot 'verify_app001.ps1'
& $verificationScript -SkipInstall
if ($LASTEXITCODE -ne 0) {
    throw "APP-001 verification failed with exit code $LASTEXITCODE."
}

Write-Host 'APP-001 format-repair verification completed successfully.' -ForegroundColor Green
