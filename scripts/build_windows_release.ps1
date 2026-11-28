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

$BootstrapPython = $env:pythonLocation
if (-not [string]::IsNullOrWhiteSpace($BootstrapPython)) {
    $BootstrapPython = Join-Path $BootstrapPython 'python.exe'
    if (-not (Test-Path -LiteralPath $BootstrapPython -PathType Leaf)) {
        throw "setup-python interpreter not found: $BootstrapPython"
    }
}
else {
    $BootstrapPython = (Get-Command python -ErrorAction Stop).Source
}

$Python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    Write-Host 'Creating isolated release virtual environment...'
    & $BootstrapPython -m venv (Join-Path $RepositoryRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the release virtual environment.' }
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Release interpreter missing: $Python"
}
$pythonVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne '3.13') {
    throw "Release requires Python 3.13; detected $pythonVersion."
}
$pythonArch = & $Python -c "import struct; print(struct.calcsize('P') * 8)"
if ($LASTEXITCODE -ne 0 -or $pythonArch -ne '64') {
    throw "Release requires 64-bit Python; detected $pythonArch-bit."
}

$license = Join-Path $RepositoryRoot 'LICENSE'
$notice = Join-Path $RepositoryRoot 'NOTICE.md'
$licenseDirectory = Join-Path $RepositoryRoot 'LICENSES'
$manifest = Join-Path $RepositoryRoot 'RESEARCH\qelectrotech-symbol-candidates.csv'
$assetRoot = Join-Path $RepositoryRoot 'assets\third_party\qelectrotech-elements'
foreach ($required in @($license, $notice, $manifest)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required release input is missing: $required"
    }
}
if ((Get-Item -LiteralPath $license).Length -lt 30000) {
    throw 'Root LICENSE is incomplete; expected the complete GPL-3.0 text and project notice.'
}
if (-not (Test-Path -LiteralPath $licenseDirectory -PathType Container)) {
    throw 'LICENSES directory is required for third-party redistribution notices.'
}
if (-not (Test-Path -LiteralPath (Join-Path $assetRoot 'ELEMENTS.LICENSE'))) {
    # The acquisition script reports failures with terminating PowerShell errors.
    # LASTEXITCODE is only meaningful after a native executable has run.
    & (Join-Path $PSScriptRoot 'Acquire-QElectroTechSymbolSeed.ps1') -RepositoryRoot $RepositoryRoot
}

$releaseVersion = $env:PFA_RELEASE_VERSION
if ([string]::IsNullOrWhiteSpace($releaseVersion)) {
    $toml = Get-Content (Join-Path $RepositoryRoot 'pyproject.toml') -Raw
    $match = [regex]::Match($toml, '(?m)^version\s*=\s*(?:"([^"]+)"|''([^'']+)'')\s*$')
    if (-not $match.Success) { throw 'Could not read project version from pyproject.toml.' }
    $parsedVersion = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
    $releaseVersion = "v$parsedVersion"
}
$displayVersion = $releaseVersion.Trim()
if ($displayVersion.StartsWith('v')) { $displayVersion = $displayVersion.Substring(1) }

Invoke-Checked 'Install exact project release dependencies' {
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
    & $Python -m pip install -e '.[dev,desktop,reports,release]'
}

if (-not $SkipTests) {
    Invoke-Checked 'Ruff source and test checks' {
        & $Python -m ruff check src tests examples
    }
    Invoke-Checked 'Compile source, tests, examples and scripts' {
        & $Python -m compileall -q src tests examples scripts
    }
    Invoke-Checked 'Complete pytest suite' {
        & $Python -m pytest -q
    }
    Write-Host '== APP-REBOOT-005 desktop, QElectroTech and Qt acceptance ==' -ForegroundColor Cyan
    # The verifier is a PowerShell script that owns its native-command exit checks.
    & (Join-Path $PSScriptRoot 'verify_app_reboot_005.ps1')
}

$distRoot = Join-Path $RepositoryRoot 'dist'
$appFolder = Join-Path $distRoot 'POWER_FAULT_ANALYZER'
$workPath = Join-Path $distRoot 'pyinstaller-work'
$specPath = Join-Path $distRoot 'pyinstaller-spec'
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
foreach ($generated in @($appFolder, $workPath, $specPath)) {
    if (Test-Path -LiteralPath $generated) {
        Remove-Item -LiteralPath $generated -Recurse -Force
    }
}

Invoke-Checked 'Build standalone Windows x64 desktop application' {
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
        --collect-all cairosvg `
        --collect-all cairocffi `
        --collect-data power_fault_analyzer `
        --add-data "$manifest;RESEARCH" `
        --add-data "$assetRoot;assets/third_party/qelectrotech-elements" `
        --workpath $workPath `
        --specpath $specPath `
        src/power_fault_analyzer/interfaces/desktop/app.py
}

$executable = Join-Path $appFolder 'POWER_FAULT_ANALYZER.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw 'PyInstaller completed without POWER_FAULT_ANALYZER.exe.'
}
if (-not $SkipTests) {
    Write-Host '== Frozen Windows executable startup acceptance ==' -ForegroundColor Cyan
    # The verifier throws if the frozen process exits during the startup window.
    & (Join-Path $PSScriptRoot 'verify_frozen_windows_app.ps1') -Executable $executable
    & (Join-Path $PSScriptRoot 'verify_frozen_script_worker.ps1') -Executable $executable
}

Copy-Item -LiteralPath $license -Destination $appFolder -Force
Copy-Item -LiteralPath $notice -Destination $appFolder -Force
Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'README.md') -Destination $appFolder -Force
Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md') -Destination $appFolder -Force
$packagedLicenseDirectory = Join-Path $appFolder 'LICENSES'
New-Item -ItemType Directory -Force -Path $packagedLicenseDirectory | Out-Null
Copy-Item -Path (Join-Path $licenseDirectory '*') -Destination $packagedLicenseDirectory -Recurse -Force

$releaseDirectory = Join-Path $RepositoryRoot $OutputDirectory
New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
$thirdPartyNotices = Join-Path $releaseDirectory 'THIRD_PARTY_NOTICES.md'
Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md') -Destination $thirdPartyNotices -Force
$updater = Join-Path $releaseDirectory 'Update-PFA-Portable.ps1'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Update-PFA-Portable.ps1') -Destination $updater -Force

Invoke-Checked 'Generate CycloneDX dependency inventory' {
    & $Python (Join-Path $PSScriptRoot 'generate_release_sbom.py') --output (Join-Path $releaseDirectory 'SBOM.cdx.json') --version $displayVersion
}
Invoke-Checked 'Generate exact Python dependency license inventory' {
    & $Python (Join-Path $PSScriptRoot 'generate_python_license_report.py') --output (Join-Path $releaseDirectory 'PYTHON-DEPENDENCY-LICENSES.md')
}
Copy-Item -LiteralPath (Join-Path $releaseDirectory 'SBOM.cdx.json') -Destination $appFolder -Force
Copy-Item -LiteralPath (Join-Path $releaseDirectory 'PYTHON-DEPENDENCY-LICENSES.md') -Destination $appFolder -Force
Copy-Item -LiteralPath $thirdPartyNotices -Destination $appFolder -Force

$gitCommit = 'unknown'
$gitOutput = & git -C $RepositoryRoot rev-parse HEAD 2>$null
if ($LASTEXITCODE -eq 0 -and $gitOutput) { $gitCommit = ([string]$gitOutput).Trim() }
$buildInfo = [ordered]@{
    product = 'POWER_FAULT_ANALYZER'
    version = $displayVersion
    python = (& $Python --version 2>&1 | Out-String).Trim()
    architecture = 'x64'
    license = 'GPL-3.0-or-later'
    git_commit = $gitCommit
    built_utc = [DateTime]::UtcNow.ToString('o')
    repository = 'https://github.com/ValentinoAlvarado/POWER_FAULT_ANALYZER'
    distribution = 'Windows x64 PyInstaller onedir package with per-user NSIS installer; in-app updates replace the installed application in place'
    artifacts = @('PFA-Setup-x64.exe', 'PFA-Windows-x64.zip', 'SHA256SUMS.txt', 'SBOM.cdx.json', 'PYTHON-DEPENDENCY-LICENSES.md', 'THIRD_PARTY_NOTICES.md', 'BUILD-INFO.json', 'Update-PFA-Portable.ps1')
}
$buildInfoPath = Join-Path $releaseDirectory 'BUILD-INFO.json'
$buildInfo | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $buildInfoPath -Encoding UTF8
Copy-Item -LiteralPath $buildInfoPath -Destination $appFolder -Force

$zipPath = Join-Path $releaseDirectory 'PFA-Windows-x64.zip'
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -Path (Join-Path $appFolder '*') -DestinationPath $zipPath -CompressionLevel Optimal
if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf) -or (Get-Item -LiteralPath $zipPath).Length -le 0) {
    throw 'Portable Windows ZIP was not created or is empty.'
}

# Build a per-user setup executable from the same verified onedir payload.
# The portable ZIP remains the payload used by the in-app updater.
$makensis = $env:PFA_MAKENSIS_PATH
if ([string]::IsNullOrWhiteSpace($makensis) -or -not (Test-Path -LiteralPath $makensis -PathType Leaf)) {
    $command = Get-Command makensis.exe -ErrorAction SilentlyContinue
    if ($command) { $makensis = $command.Source }
}
if ([string]::IsNullOrWhiteSpace($makensis) -or -not (Test-Path -LiteralPath $makensis -PathType Leaf)) {
    $programFilesX86 = [Environment]::GetFolderPath('ProgramFilesX86')
    $nsisCandidates = @(
        (Join-Path $programFilesX86 'NSIS\makensis.exe'),
        (Join-Path $env:ProgramFiles 'NSIS\makensis.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    if ($nsisCandidates) { $makensis = $nsisCandidates[0] }
}
if ([string]::IsNullOrWhiteSpace($makensis) -or -not (Test-Path -LiteralPath $makensis -PathType Leaf)) {
    throw 'NSIS makensis.exe is required to build PFA-Setup-x64.exe.'
}

$resourceMatch = [regex]::Match(
    $displayVersion,
    '^(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)(?:(?<pre>a|b|rc)(?<number>\d+))?$'
)
if (-not $resourceMatch.Success) {
    throw "Version '$displayVersion' cannot be represented in the Windows four-part file version."
}
$resourceRevision = 0
if ($resourceMatch.Groups['number'].Success) {
    $preNumber = [int]$resourceMatch.Groups['number'].Value
    $resourceRevision = switch ($resourceMatch.Groups['pre'].Value) {
        'a'  { 1000 + $preNumber }
        'b'  { 20000 + $preNumber }
        'rc' { 40000 + $preNumber }
    }
}
if ($resourceRevision -gt 65535) { throw 'Pre-release sequence exceeds Windows file-version limits.' }
$versionParts = @([int]$resourceMatch.Groups['major'].Value, [int]$resourceMatch.Groups['minor'].Value, [int]$resourceMatch.Groups['patch'].Value, [int]$resourceRevision)
if ($versionParts | Where-Object { $_ -gt 65535 }) { throw 'Version component exceeds Windows file-version limits.' }
$resourceVersion = '{0}.{1}.{2}.{3}' -f $resourceMatch.Groups['major'].Value, $resourceMatch.Groups['minor'].Value, $resourceMatch.Groups['patch'].Value, $resourceRevision
$setupPath = Join-Path $releaseDirectory 'PFA-Setup-x64.exe'
if (Test-Path -LiteralPath $setupPath) { Remove-Item -LiteralPath $setupPath -Force }
$nsisArgs = @(
    "/DAPP_VERSION=$displayVersion",
    "/DAPP_VERSION_RESOURCE=$resourceVersion",
    "/DAPP_SOURCE=$appFolder",
    "/DOUTPUT_PATH=$setupPath"
)
Write-Host '== Build per-user Windows installer with NSIS ==' -ForegroundColor Cyan
& $makensis @nsisArgs (Join-Path $RepositoryRoot 'installer/PFA-Setup-x64.nsi')
if ($LASTEXITCODE -ne 0) { throw "NSIS installer build failed with exit code $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf) -or (Get-Item -LiteralPath $setupPath).Length -le 0) {
    throw 'NSIS did not produce a non-empty PFA-Setup-x64.exe.'
}

# Smoke-test a silent first-time install and uninstall on the Windows runner.
$installerSmokeRoot = Join-Path $env:SystemDrive ("PFA-Installer-Acceptance-" + [guid]::NewGuid().ToString('N'))
try {
    $installerProcess = Start-Process -FilePath $setupPath -ArgumentList @('/S', "/D=$installerSmokeRoot") -Wait -PassThru
    if ($installerProcess.ExitCode -ne 0) { throw "Silent NSIS install failed with exit code $($installerProcess.ExitCode)." }
    $installedExe = Join-Path $installerSmokeRoot 'POWER_FAULT_ANALYZER.exe'
    $installedInfoPath = Join-Path $installerSmokeRoot 'BUILD-INFO.json'
    if (-not (Test-Path -LiteralPath $installedExe -PathType Leaf) -or -not (Test-Path -LiteralPath $installedInfoPath -PathType Leaf)) {
        throw 'NSIS installation did not deploy the executable and build metadata.'
    }
    $installedInfo = Get-Content -LiteralPath $installedInfoPath -Raw | ConvertFrom-Json
    if ($installedInfo.product -ne 'POWER_FAULT_ANALYZER' -or $installedInfo.version -ne $displayVersion -or $installedInfo.architecture -ne 'x64') {
        throw 'NSIS installation deployed unexpected product/version/architecture metadata.'
    }
    $uninstaller = Join-Path $installerSmokeRoot 'Uninstall.exe'
    if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) { throw 'NSIS installation did not create its uninstaller.' }
    $uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList '/S' -Wait -PassThru
    if ($uninstallProcess.ExitCode -ne 0) { throw "Silent NSIS uninstall failed with exit code $($uninstallProcess.ExitCode)." }
    if (Test-Path -LiteralPath $installedExe) { throw 'NSIS uninstaller left POWER_FAULT_ANALYZER.exe behind.' }
    Write-Host 'PASS NSIS installer deployed the expected application and uninstaller removed it.' -ForegroundColor Green
}
finally {
    if (Test-Path -LiteralPath $installerSmokeRoot) {
        Remove-Item -LiteralPath $installerSmokeRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$hashLines = @()
foreach ($fileName in @('PFA-Setup-x64.exe', 'PFA-Windows-x64.zip', 'SBOM.cdx.json', 'PYTHON-DEPENDENCY-LICENSES.md', 'THIRD_PARTY_NOTICES.md', 'BUILD-INFO.json', 'Update-PFA-Portable.ps1')) {
    $path = Join-Path $releaseDirectory $fileName
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required release sidecar missing: $path" }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $hashLines += "$hash  $fileName"
}
$checksumPath = Join-Path $releaseDirectory 'SHA256SUMS.txt'
$hashLines | Set-Content -LiteralPath $checksumPath -Encoding ASCII

if (-not $SkipTests) {
    Write-Host '== Portable updater success, checksum and rollback acceptance ==' -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'verify_portable_updater.ps1') `
        -UpdaterScript $updater `
        -ZipPath $zipPath `
        -ChecksumPath $checksumPath
}

Write-Host "Portable Windows package: $zipPath" -ForegroundColor Green
Write-Host "Release sidecars: $releaseDirectory" -ForegroundColor Green
Write-Host 'No NSIS installer is generated by this portable-ZIP release workflow.' -ForegroundColor Yellow