[CmdletBinding()]
param([string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($RepositoryRoot)
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Repository virtual environment not found: $Python"
}
$Output = Join-Path $Root 'outputs\current\verification'
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$Transcript = Join-Path $Output 'PFA_PRODUCT_CONSOLIDATED_001.txt'
$PreviousPythonPath = $env:PYTHONPATH
$PreviousQtPlatform = $env:QT_QPA_PLATFORM
$env:PYTHONPATH = (Join-Path $Root 'src') + ';' + $Root
$env:QT_QPA_PLATFORM = 'offscreen'
Start-Transcript -Path $Transcript -Force | Out-Null
function Invoke-Checked {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "== $Name ==" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE." }
}
try {
    Push-Location $Root
    Write-Host "Python: $Python"
    & $Python --version
    if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
    Invoke-Checked 'Compile source, scripts and tests' { & $Python -m compileall -q src scripts tests }
    Write-Host 'PASS compileall'
    Invoke-Checked 'Check Qt and vector PDF dependencies' {
        & $Python -c "import PySide6, cairosvg; print('PySide6 and CairoSVG available')"
    }
    Invoke-Checked 'Complete Python test suite' { & $Python -m pytest -q }
    Write-Host 'PASS pytest'
    Invoke-Checked 'Workbench transaction regression' { & $Python 'scripts\verify_pfa_workbench_004_1_commands.py' }
    Invoke-Checked 'Workbench property editor regression' { & $Python 'scripts\verify_pfa_workbench_004_2_property_editor.py' }
    Invoke-Checked 'Canonical route/Qt parity regression' { & $Python 'scripts\verify_pfa_design_003_qt.py' }
    Invoke-Checked 'Keyboard shortcut Qt acceptance' { & $Python 'scripts\verify_pfa_keyboard_shortcuts.py' }
    Invoke-Checked 'Transformer symbol Qt raster acceptance' { & $Python 'scripts\verify_pfa_symbols_001_qt.py' }
    Invoke-Checked 'Canonical SVG/PDF/PNG reference export' { & $Python 'scripts\export_pfa_symbols_001_reference_figures.py' }
    Write-Host "PASS PFA_PRODUCT_CONSOLIDATED_001. Transcript: $Transcript" -ForegroundColor Green
}
finally {
    if (Get-Location) { Pop-Location -ErrorAction SilentlyContinue }
    $env:PYTHONPATH = $PreviousPythonPath
    $env:QT_QPA_PLATFORM = $PreviousQtPlatform
    Stop-Transcript | Out-Null
}
