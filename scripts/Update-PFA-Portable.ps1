[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [Parameter(Mandatory = $true)][string]$InstallDirectory
)

$ErrorActionPreference = 'Stop'
$zip = (Resolve-Path -LiteralPath $ZipPath -ErrorAction Stop).Path
$install = [System.IO.Path]::GetFullPath($InstallDirectory).TrimEnd('\')
$parent = Split-Path -Parent $install
$name = Split-Path -Leaf $install
if (-not (Test-Path -LiteralPath $install -PathType Container)) {
    throw "Portable application directory does not exist: $install"
}
$exe = Join-Path $install 'POWER_FAULT_ANALYZER.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "The target is not a PFA portable application directory: $install"
}
$running = Get-CimInstance Win32_Process -Filter "Name='POWER_FAULT_ANALYZER.exe'" |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath -ieq $exe }
if ($running) {
    throw "Close POWER_FAULT_ANALYZER before updating. Running PID(s): $($running.ProcessId -join ', ')"
}

$token = [guid]::NewGuid().ToString('N')
$staging = Join-Path $parent ".$name.update-$token"
$backup = Join-Path $parent "$name.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
try {
    New-Item -ItemType Directory -Path $staging | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $staging -ErrorAction Stop
    $newExe = Join-Path $staging 'POWER_FAULT_ANALYZER.exe'
    $buildInfo = Join-Path $staging 'BUILD-INFO.json'
    if (-not (Test-Path -LiteralPath $newExe -PathType Leaf)) {
        throw 'Update archive does not contain POWER_FAULT_ANALYZER.exe at its root.'
    }
    if (-not (Test-Path -LiteralPath $buildInfo -PathType Leaf)) {
        throw 'Update archive does not contain BUILD-INFO.json at its root.'
    }
    $metadata = Get-Content -LiteralPath $buildInfo -Raw | ConvertFrom-Json
    if ($metadata.product -ne 'POWER_FAULT_ANALYZER' -or $metadata.architecture -ne 'x64') {
        throw 'Update archive product or architecture does not match this application.'
    }

    Move-Item -LiteralPath $install -Destination $backup
    try {
        Move-Item -LiteralPath $staging -Destination $install
    }
    catch {
        if (-not (Test-Path -LiteralPath $install) -and (Test-Path -LiteralPath $backup)) {
            Move-Item -LiteralPath $backup -Destination $install
        }
        throw
    }
    Write-Host "PFA updated to version $($metadata.version)." -ForegroundColor Green
    Write-Host "Previous application retained at: $backup" -ForegroundColor Yellow
    Write-Host 'Projects and settings outside the application directory were not modified.'
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    }
}
