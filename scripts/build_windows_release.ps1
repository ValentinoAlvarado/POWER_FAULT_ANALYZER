[CmdletBinding()]
param(
    [switch]$SkipTests,
    [string]$OutputDirectory = "dist\release"
)

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

$Python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}
$pythonVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) { throw 'Unable to identify the selected Python interpreter.' }
if ($pythonVersion -ne '3.13') {
    throw "Release build requires Python 3.13; detected $pythonVersion."
}

$projectLicense = Join-Path $RepositoryRoot 'LICENSE'
if (-not (Test-Path $projectLicense) -or (Get-Item $projectLicense).Length -eq 0) {
    throw 'Release blocked: the root LICENSE file is empty. Select and publish the project license and review Qt/PySide6 redistribution obligations before producing a public binary.'
}

$manifest = Join-Path $RepositoryRoot 'RESEARCH\qelectrotech-symbol-candidates.csv'
$assetRoot = Join-Path $RepositoryRoot 'assets\third_party\qelectrotech-elements'
if (-not (Test-Path $manifest)) { throw "Missing pinned QET manifest: $manifest" }
if (-not (Test-Path (Join-Path $assetRoot 'ELEMENTS.LICENSE'))) {
    & (Join-Path $PSScriptRoot 'Acquire-QElectroTechSymbolSeed.ps1') -RepositoryRoot $RepositoryRoot
    if ($LASTEXITCODE -ne 0) { throw 'QET source seed acquisition failed.' }
}

Invoke-Checked 'Install release dependencies' { & $Python -m pip install -e '.[dev,desktop,reports,release]' }
if (-not $SkipTests) {
    Invoke-Checked 'Complete APP-REBOOT-005 quality and desktop acceptance gates' {
        & (Join-Path $PSScriptRoot 'verify_app_reboot_005.ps1')
    }
}

$distRoot = Join-Path $RepositoryRoot 'dist'
$workPath = Join-Path $distRoot 'pyinstaller-work'
$specPath = Join-Path $distRoot 'pyinstaller-spec'
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null

Invoke-Checked 'Build standalone Windows application' {
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
        --name POWER_FAULT_ANALYZER `
        --paths src `
        --collect-all PySide6 `
        --collect-all numpy `
        --collect-all scipy `
        --collect-all pandas `
        --collect-all networkx `
        --collect-all reportlab `
        --collect-all openpyxl `
        --collect-all matplotlib `
        --collect-all pyqtgraph `
        --add-data "$manifest;RESEARCH" `
        --add-data "$assetRoot;assets/third_party/qelectrotech-elements" `
        --workpath $workPath `
        --specpath $specPath `
        src/power_fault_analyzer/interfaces/desktop/app.py
}

$appFolder = Join-Path $distRoot 'POWER_FAULT_ANALYZER'
if (-not (Test-Path (Join-Path $appFolder 'POWER_FAULT_ANALYZER.exe'))) {
    throw 'PyInstaller completed without the expected executable.'
}
Copy-Item LICENSE $appFolder -Force
Copy-Item README.md $appFolder -Force
Copy-Item docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md $appFolder -Force

$releaseDirectory = Join-Path $RepositoryRoot $OutputDirectory
New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
$zipPath = Join-Path $releaseDirectory 'PFA-Windows-x64.zip'
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $appFolder '*') -DestinationPath $zipPath -CompressionLevel Optimal
$hash = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  PFA-Windows-x64.zip" | Set-Content (Join-Path $releaseDirectory 'SHA256SUMS.txt') -Encoding ASCII
Write-Host "Release bundle created: $zipPath" -ForegroundColor Green
Write-Host "SHA-256: $hash"
