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
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE." }
}

$BootstrapPython = (Get-Command python -ErrorAction Stop).Source
$Python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    & $BootstrapPython -m venv (Join-Path $RepositoryRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the isolated release virtual environment.' }
}
if (-not (Test-Path -LiteralPath $Python)) { throw "Release virtual environment not found: $Python" }
$pythonVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne '3.13') { throw "Release build requires Python 3.13; detected $pythonVersion." }
$pythonArch = & $Python -c "import struct; print(struct.calcsize('P') * 8)"
if ($LASTEXITCODE -ne 0 -or $pythonArch -ne '64') { throw "Release build requires 64-bit Python; detected $pythonArch-bit." }

$license = Join-Path $RepositoryRoot 'LICENSE'
if (-not (Test-Path $license) -or (Get-Item $license).Length -lt 30000) { throw 'GPL license text is missing or incomplete.' }
$notice = Join-Path $RepositoryRoot 'NOTICE.md'
if (-not (Test-Path $notice)) { throw 'NOTICE.md is required for third-party redistribution notices.' }
$manifest = Join-Path $RepositoryRoot 'RESEARCH\qelectrotech-symbol-candidates.csv'
$assetRoot = Join-Path $RepositoryRoot 'assets\third_party\qelectrotech-elements'
if (-not (Test-Path $manifest)) { throw "Missing pinned QET manifest: $manifest" }
if (-not (Test-Path (Join-Path $assetRoot 'ELEMENTS.LICENSE'))) {
    & (Join-Path $PSScriptRoot 'Acquire-QElectroTechSymbolSeed.ps1') -RepositoryRoot $RepositoryRoot
    if ($LASTEXITCODE -ne 0) { throw 'QET source seed acquisition failed.' }
}

$releaseVersion = $env:PFA_RELEASE_VERSION
if ([string]::IsNullOrWhiteSpace($releaseVersion)) {
    $toml = Get-Content (Join-Path $RepositoryRoot 'pyproject.toml') -Raw
    $match = [regex]::Match($toml, '(?m)^version\s*=\s*"([^"]+)"')
    if (-not $match.Success) { throw 'Could not read project version from pyproject.toml.' }
    $releaseVersion = "v$($match.Groups[1].Value)"
}
$releaseVersion = $releaseVersion.Trim()
if ($releaseVersion.StartsWith('v')) { $displayVersion = $releaseVersion.Substring(1) } else { $displayVersion = $releaseVersion }
$numericVersion = [regex]::Match($displayVersion, '^(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)')
if (-not $numericVersion.Success) { throw "Invalid release version: $displayVersion" }
$versionResource = "$($numericVersion.Groups['major'].Value).$($numericVersion.Groups['minor'].Value).$($numericVersion.Groups['patch'].Value).0"

Invoke-Checked 'Install development, desktop, reporting and release dependencies' {
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
    & $Python -m pip install -e '.[dev,desktop,reports,release]'
}
if (-not $SkipTests) {
    Invoke-Checked 'Consolidated PFA transaction, property, route, keyboard and transformer acceptance' {
        & (Join-Path $PSScriptRoot 'VERIFY_PFA_PRODUCT_CONSOLIDATED_001.ps1') -RepositoryRoot $RepositoryRoot
    }
    Invoke-Checked 'Pinned QElectroTech import and Qt renderer acceptance' {
        & (Join-Path $PSScriptRoot 'verify_qet_symbol_importer.ps1')
    }
    Invoke-Checked 'Desktop application startup smoke test' {
        & $Python (Join-Path $PSScriptRoot 'smoke_test_app_reboot_005.py')
    }
}

$distRoot = Join-Path $RepositoryRoot 'dist'
$workPath = Join-Path $distRoot 'pyinstaller-work'
$specPath = Join-Path $distRoot 'pyinstaller-spec'
$appFolder = Join-Path $distRoot 'POWER_FAULT_ANALYZER'
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
if (Test-Path $appFolder) { Remove-Item $appFolder -Recurse -Force }
if (Test-Path $workPath) { Remove-Item $workPath -Recurse -Force }

Invoke-Checked 'Build standalone Windows x64 application with PyInstaller' {
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
        --name POWER_FAULT_ANALYZER `
        --paths src `
        --collect-all PySide6 `
        --collect-all shiboken6 `
        --collect-all numpy `
        --collect-all scipy `
        --collect-all pandas `
        --collect-all networkx `
        --collect-all pydantic `
        --collect-all pint `
        --collect-all reportlab `
        --collect-all openpyxl `
        --collect-all matplotlib `
        --collect-all pyqtgraph `
        --collect-all qtawesome `
        --collect-data power_fault_analyzer `
        --add-data "$manifest;RESEARCH" `
        --add-data "$assetRoot;assets/third_party/qelectrotech-elements" `
        --workpath $workPath `
        --specpath $specPath `
        src/power_fault_analyzer/interfaces/desktop/app.py
}
if (-not (Test-Path (Join-Path $appFolder 'POWER_FAULT_ANALYZER.exe'))) { throw 'PyInstaller completed without the expected executable.' }
Invoke-Checked 'Frozen Windows application startup smoke test' {
    & (Join-Path $PSScriptRoot 'verify_frozen_windows_app.ps1') -Executable (Join-Path $appFolder 'POWER_FAULT_ANALYZER.exe')
}

$releaseDirectory = Join-Path $RepositoryRoot $OutputDirectory
if (Test-Path $releaseDirectory) { Remove-Item $releaseDirectory -Recurse -Force }
New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null

Copy-Item $license $appFolder -Force
Copy-Item $notice $appFolder -Force
Copy-Item (Join-Path $RepositoryRoot 'README.md') $appFolder -Force
Copy-Item (Join-Path $RepositoryRoot 'docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md') $appFolder -Force
Copy-Item (Join-Path $RepositoryRoot 'docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md') (Join-Path $releaseDirectory 'THIRD_PARTY_NOTICES.md') -Force
Copy-Item (Join-Path $RepositoryRoot 'LICENSES') $appFolder -Recurse -Force

Invoke-Checked 'Generate CycloneDX dependency inventory' {
    & $Python (Join-Path $PSScriptRoot 'generate_release_sbom.py') --output (Join-Path $releaseDirectory 'SBOM.cdx.json') --version $displayVersion
}
Invoke-Checked 'Generate Python dependency license inventory' {
    & $Python (Join-Path $PSScriptRoot 'generate_python_license_report.py') --output (Join-Path $releaseDirectory 'PYTHON-DEPENDENCY-LICENSES.md')
}
Copy-Item (Join-Path $releaseDirectory 'SBOM.cdx.json') $appFolder -Force
Copy-Item (Join-Path $releaseDirectory 'PYTHON-DEPENDENCY-LICENSES.md') $appFolder -Force
$buildInfo = [ordered]@{
    product = 'POWER_FAULT_ANALYZER'
    version = $displayVersion
    release_tag = $releaseVersion
    python = (& $Python --version 2>&1 | Out-String).Trim()
    architecture = 'x64'
    license = 'GPL-3.0-or-later'
    built_utc = [DateTime]::UtcNow.ToString('o')
    repository = 'https://github.com/ValentinoAlvarado/POWER_FAULT_ANALYZER'
    artifacts = @('PFA-Setup-x64.exe','PFA-Windows-x64.zip','SHA256SUMS.txt','SBOM.cdx.json','PYTHON-DEPENDENCY-LICENSES.md')
}
$buildInfo | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $appFolder 'BUILD-INFO.json') -Encoding UTF8
$buildInfo | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $releaseDirectory 'BUILD-INFO.json') -Encoding UTF8

# Portable onedir ZIP remains available alongside the user-friendly setup EXE.
$zipPath = Join-Path $releaseDirectory 'PFA-Windows-x64.zip'
Compress-Archive -Path (Join-Path $appFolder '*') -DestinationPath $zipPath -CompressionLevel Optimal

$makensis = (Get-Command makensis.exe -ErrorAction SilentlyContinue).Source
if (-not $makensis) {
    $candidate = 'C:\Program Files (x86)\NSIS\makensis.exe'
    if (Test-Path $candidate) { $makensis = $candidate }
}
if (-not $makensis) { throw 'NSIS compiler not found. Install NSIS 3.x before building the setup executable.' }
$setupPath = Join-Path $releaseDirectory 'PFA-Setup-x64.exe'
Invoke-Checked 'Compile NSIS Windows installer' {
    & $makensis "/DAPP_VERSION=$displayVersion" "/DAPP_VERSION_RESOURCE=$versionResource" "/DAPP_SOURCE=dist\POWER_FAULT_ANALYZER" "/DOUTPUT_PATH=dist\release\PFA-Setup-x64.exe" (Join-Path $RepositoryRoot 'installer/PFA-Setup-x64.nsi')
}
if (-not (Test-Path $setupPath)) { throw 'NSIS did not create PFA-Setup-x64.exe.' }

$hashLines = @()
foreach ($fileName in @('PFA-Setup-x64.exe','PFA-Windows-x64.zip','SBOM.cdx.json','PYTHON-DEPENDENCY-LICENSES.md','THIRD_PARTY_NOTICES.md','BUILD-INFO.json')) {
    $path = Join-Path $releaseDirectory $fileName
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $hashLines += "$hash  $fileName"
}
$hashLines | Set-Content (Join-Path $releaseDirectory 'SHA256SUMS.txt') -Encoding ASCII
Copy-Item (Join-Path $releaseDirectory 'SHA256SUMS.txt') $appFolder -Force
Write-Host "Windows setup created: $setupPath" -ForegroundColor Green
Write-Host "Portable bundle created: $zipPath" -ForegroundColor Green
Write-Host 'Release artifacts and SHA-256 checksums generated.' -ForegroundColor Green
