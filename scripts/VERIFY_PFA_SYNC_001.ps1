[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RepositoryRoot)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $Command = Get-Command python -ErrorAction Stop
    $Python = $Command.Source
}
$Output = Join-Path $Root 'outputs\pfa_sync_001_windows_verification'
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$Transcript = Join-Path $Output 'verification-transcript.txt'
Start-Transcript -Path $Transcript -Force | Out-Null
try {
    Push-Location $Root
    Write-Host "Python: $Python"
    & $Python --version
    if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }

    & $Python -m compileall -q src examples scripts
    if ($LASTEXITCODE -ne 0) { throw 'compileall failed.' }
    Write-Host 'PASS compileall'

    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }
    Write-Host 'PASS pytest'

    & $Python -c "import PySide6"
    if ($LASTEXITCODE -ne 0) {
        throw 'PySide6 is missing. Install requirements-desktop.txt in this environment, then rerun this verification script.'
    }
    & $Python scripts\verify_pfa_sync_001_qt.py
    if ($LASTEXITCODE -ne 0) { throw 'Qt canvas smoke test failed.' }

    Write-Host "PASS. Transcript: $Transcript"
    Write-Host "Qt screenshots: $(Join-Path $Root 'outputs\pfa_sync_001_qt')"
}
finally {
    Pop-Location
    Stop-Transcript | Out-Null
}
