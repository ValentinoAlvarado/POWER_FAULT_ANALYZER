[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RepositoryRoot,
    [Parameter(Mandatory=$true)][string]$BackupPath
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($RepositoryRoot)
$Backup = [IO.Path]::GetFullPath($BackupPath)
$BackupFiles = Join-Path $Backup 'files'
$CreatedFile = Join-Path $Backup 'created-files.txt'
if (-not (Test-Path -LiteralPath $Backup -PathType Container)) { throw "Backup not found: $Backup" }
if (Test-Path -LiteralPath $CreatedFile -PathType Leaf) {
    foreach ($relative in Get-Content -LiteralPath $CreatedFile) {
        if ([string]::IsNullOrWhiteSpace($relative)) { continue }
        $target = [IO.Path]::GetFullPath((Join-Path $Root $relative))
        $prefix = $Root.TrimEnd('\') + '\'
        if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe created path: $relative" }
        if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
    }
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
Write-Host "PFA product consolidation rollback completed from: $Backup" -ForegroundColor Yellow
