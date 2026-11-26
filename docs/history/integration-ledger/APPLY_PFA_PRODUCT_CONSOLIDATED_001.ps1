[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RepositoryRoot)
$ErrorActionPreference = 'Stop'
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = [IO.Path]::GetFullPath($RepositoryRoot)
$RootPrefix = $Root.TrimEnd('\') + '\'
$BackupRoot = Join-Path $env:LOCALAPPDATA 'PFA\backups'
$WorkbenchMarker = Join-Path $Root 'docs\architecture\PFA-WORKBENCH-004.2.3.1-QT-OFFSCREEN-TEARDOWN.md'
$DesignMarker = Join-Path $Root 'docs\engineering\PFA-DESIGN-003-composition-and-symbols.md'
if (-not (Test-Path -LiteralPath $WorkbenchMarker -PathType Leaf)) { throw 'Verified 004.2.3.1 baseline marker not found; refusing to apply.' }
if ((Get-Content -LiteralPath $WorkbenchMarker -Raw) -notmatch 'PFA-WORKBENCH-004\.2\.3\.1') { throw 'Repository is not the verified 004.2.3.1 baseline.' }
if (-not (Test-Path -LiteralPath $DesignMarker -PathType Leaf)) { throw 'PFA-DESIGN-003 baseline marker not found; refusing to apply.' }

function Read-HashManifest([string]$Path) {
    $result = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split '\s+', 2
        if ($parts.Count -ne 2) { throw "Malformed SHA-256 manifest line: $line" }
        $relative = $parts[1].TrimStart('*').Replace('/', '\')
        if ($result.ContainsKey($relative)) { throw "Duplicate manifest entry: $relative" }
        $result[$relative] = $parts[0].ToUpperInvariant()
    }
    return $result
}
function Assert-PackageManifest([string]$Base, [string]$Manifest) {
    $entries = Read-HashManifest $Manifest
    foreach ($relative in $entries.Keys) {
        $file = Join-Path $Base $relative
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Package file missing: $relative" }
        $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actual -ne $entries[$relative]) { throw "Package SHA-256 mismatch: $relative" }
    }
}
$PackageManifest = Join-Path $PackageRoot 'MANIFEST_SHA256.txt'
$PayloadManifest = Join-Path $PackageRoot 'PAYLOAD_SHA256.txt'
if (-not (Test-Path $PackageManifest) -or -not (Test-Path $PayloadManifest)) { throw 'Package manifests are missing.' }
Assert-PackageManifest $PackageRoot $PackageManifest
$PayloadEntries = Read-HashManifest $PayloadManifest
foreach ($manifestRelative in $PayloadEntries.Keys) {
    if (-not $manifestRelative.StartsWith('payload\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Payload manifest entry outside payload/: $manifestRelative"
    }
    $packageFile = Join-Path $PackageRoot $manifestRelative
    if (-not (Test-Path -LiteralPath $packageFile -PathType Leaf)) { throw "Payload file missing: $manifestRelative" }
    $actual = (Get-FileHash -LiteralPath $packageFile -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actual -ne $PayloadEntries[$manifestRelative]) { throw "Payload SHA-256 mismatch: $manifestRelative" }
}
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$Backup = Join-Path $BackupRoot "PFA_PRODUCT_CONSOLIDATED_001_$Stamp"
$BackupFiles = Join-Path $Backup 'files'
New-Item -ItemType Directory -Path $BackupFiles -Force | Out-Null
$Created = New-Object System.Collections.Generic.List[string]
try {
    foreach ($manifestRelative in ($PayloadEntries.Keys | Sort-Object)) {
        $relative = $manifestRelative.Substring('payload\'.Length)
        if ([string]::IsNullOrWhiteSpace($relative)) { throw "Invalid payload target: $manifestRelative" }
        $Source = Join-Path $PackageRoot $manifestRelative
        $Target = [IO.Path]::GetFullPath((Join-Path $Root $relative))
        if (-not $Target.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe payload path: $relative" }
        $Parent = Split-Path -Parent $Target
        if (-not (Test-Path -LiteralPath $Parent -PathType Container)) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
        if (Test-Path -LiteralPath $Target -PathType Leaf) {
            $BackupFile = Join-Path $BackupFiles $relative
            $BackupParent = Split-Path -Parent $BackupFile
            if (-not (Test-Path -LiteralPath $BackupParent -PathType Container)) { New-Item -ItemType Directory -Path $BackupParent -Force | Out-Null }
            Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
        } else {
            $Created.Add($relative)
        }
        Copy-Item -LiteralPath $Source -Destination $Target -Force
    }
    $Created | Set-Content -LiteralPath (Join-Path $Backup 'created-files.txt') -Encoding UTF8
    $Backup | Set-Content -LiteralPath (Join-Path $BackupRoot 'PFA_PRODUCT_CONSOLIDATED_001.latest') -Encoding UTF8
    Write-Host 'PFA product consolidation applied. Running full Windows acceptance...'
    & (Join-Path $PackageRoot 'scripts\VERIFY_PFA_PRODUCT_CONSOLIDATED_001.ps1') -RepositoryRoot $Root
    if ($LASTEXITCODE -ne 0) { throw 'PFA product consolidation verification failed.' }
    Write-Host "PFA product consolidation applied and verified. Backup: $Backup" -ForegroundColor Green
    Write-Host 'No Git branch, commit, reset or history operation was performed.'
}
catch {
    Write-Warning $_
    Write-Warning 'Rolling back product consolidation.'
    foreach ($relative in $Created) {
        $target = Join-Path $Root $relative
        if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
    }
    if (Test-Path -LiteralPath $BackupFiles -PathType Container) {
        Get-ChildItem -LiteralPath $BackupFiles -File -Recurse | ForEach-Object {
            $relative = $_.FullName.Substring($BackupFiles.Length).TrimStart('\')
            $target = Join-Path $Root $relative
            $parent = Split-Path -Parent $target
            if (-not (Test-Path -LiteralPath $parent -PathType Container)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
    throw
}
