[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RepositoryRoot)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Repository virtual environment not found: $Python"
}
$Output = Join-Path $Root 'outputs\pfa_design_003_windows_verification'
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$Transcript = Join-Path $Output 'verification-transcript.txt'
Start-Transcript -Path $Transcript -Force | Out-Null
try {
    Push-Location $Root
    Write-Host "Python: $Python"
    & $Python --version
    if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }

    & $Python -m compileall -q src examples scripts tests
    if ($LASTEXITCODE -ne 0) { throw 'compileall failed.' }
    Write-Host 'PASS compileall'

    & $Python -c "import cairosvg; import PySide6; print('CairoSVG and PySide6 available')"
    if ($LASTEXITCODE -ne 0) {
        throw 'CairoSVG and PySide6 are required in the repository virtual environment.'
    }

    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }
    Write-Host 'PASS pytest'

    & $Python scripts\verify_pfa_design_003_qt.py
    if ($LASTEXITCODE -ne 0) { throw 'PFA-DESIGN-003 Qt canvas smoke test failed.' }
    Write-Host "PASS. Transcript: $Transcript"
    Write-Host "Qt screenshots: $(Join-Path $Root 'outputs\pfa_design_003_qt')"
}
finally {
    Pop-Location
    Stop-Transcript | Out-Null
}
