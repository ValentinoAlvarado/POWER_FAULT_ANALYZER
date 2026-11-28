[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RepositoryRoot,
    [string]$BackupPath = ''
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $BackupPath) {
    $LatestFile = Join-Path $env:LOCALAPPDATA 'PFA\backups\PFA_DESIGN_003.latest'
    if (-not (Test-Path -LiteralPath $LatestFile)) {
        throw "No PFA-DESIGN-003 backup pointer found: $LatestFile"
    }
    $BackupPath = (Get-Content -LiteralPath $LatestFile -Raw).Trim()
}
$Backup = (Resolve-Path -LiteralPath $BackupPath).Path
$NewFiles = Join-Path $Backup 'new-files.txt'
if (-not (Test-Path -LiteralPath $NewFiles)) {
    throw "Backup manifest is missing: $NewFiles"
}

Get-ChildItem -LiteralPath $Backup -Recurse -File | Where-Object {
    $_.FullName -ne $NewFiles
} | ForEach-Object {
    $Relative = $_.FullName.Substring($Backup.Length).TrimStart('\','/')
    $Destination = Join-Path $Root $Relative
    $DestinationDirectory = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $Destination -Force
}

foreach ($Relative in (Get-Content -LiteralPath $NewFiles)) {
    if ([string]::IsNullOrWhiteSpace($Relative)) { continue }
    $Destination = Join-Path $Root $Relative
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        Remove-Item -LiteralPath $Destination -Force
    }
}
Write-Host "PFA-DESIGN-003 rollback completed from: $Backup"
