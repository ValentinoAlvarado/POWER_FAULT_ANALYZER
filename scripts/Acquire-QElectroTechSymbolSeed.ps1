[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$commit = '661f5e9ce5caa76277cafd3ebf0e0320fc4af229'
$repository = 'qelectrotech/qelectrotech-elements'
$assetRoot = Join-Path $RepositoryRoot 'assets\third_party\qelectrotech-elements'
$manifestRoot = Join-Path $PSScriptRoot '..\RESEARCH'
$manifestPath = Join-Path $manifestRoot 'qelectrotech-symbol-candidates.csv'

if (-not (Test-Path (Join-Path $RepositoryRoot 'pyproject.toml'))) {
    throw "RepositoryRoot does not contain pyproject.toml: $RepositoryRoot"
}
if (-not (Test-Path $manifestPath)) {
    throw "Symbol candidate manifest not found: $manifestPath. Copy the RESEARCH folder from this package to the repository root."
}

function Get-GitBlobSha1 {
    param([byte[]]$Bytes)
    $prefix = [System.Text.Encoding]::ASCII.GetBytes("blob $($Bytes.Length)`0")
    $payload = New-Object byte[] ($prefix.Length + $Bytes.Length)
    [System.Buffer]::BlockCopy($prefix, 0, $payload, 0, $prefix.Length)
    [System.Buffer]::BlockCopy($Bytes, 0, $payload, $prefix.Length, $Bytes.Length)
    $sha = [System.Security.Cryptography.SHA1]::Create()
    try {
        $digest = $sha.ComputeHash($payload)
        return (($digest | ForEach-Object { $_.ToString('x2') }) -join '')
    }
    finally {
        $sha.Dispose()
    }
}

$manifest = Import-Csv -LiteralPath $manifestPath
New-Item -ItemType Directory -Force -Path $assetRoot | Out-Null
$records = New-Object System.Collections.Generic.List[object]

foreach ($entry in $manifest) {
    $relativePath = $entry.qet_path.Replace('/', '\')
    $destination = Join-Path $assetRoot $relativePath
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null

    $uri = "https://raw.githubusercontent.com/$repository/$commit/$($entry.qet_path)"
    Write-Host "Downloading $($entry.asset_id)" -ForegroundColor Cyan
    Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile $destination

    $bytes = [System.IO.File]::ReadAllBytes($destination)
    $actualGitSha = Get-GitBlobSha1 -Bytes $bytes
    if ($actualGitSha -ne $entry.qet_git_blob_sha1) {
        Remove-Item -LiteralPath $destination -Force
        throw "Git blob SHA mismatch for $($entry.qet_path). Expected $($entry.qet_git_blob_sha1), got $actualGitSha."
    }

    $records.Add([pscustomobject]@{
        asset_id = $entry.asset_id
        qet_path = $entry.qet_path
        git_blob_sha1 = $actualGitSha
        sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        byte_length = $bytes.Length
        source_commit = $commit
        license = 'CC-BY-3.0'
        normative_status = $entry.normative_status
    })
}

$licenseDestination = Join-Path $assetRoot 'ELEMENTS.LICENSE'
$licenseUri = "https://raw.githubusercontent.com/$repository/$commit/ELEMENTS.LICENSE"
Invoke-WebRequest -UseBasicParsing -Uri $licenseUri -OutFile $licenseDestination
$licenseBytes = [System.IO.File]::ReadAllBytes($licenseDestination)
$expectedLicenseGitSha = 'ed97f9c283ae6353c78e0cc5b3c798ea732f2d3b'
$actualLicenseGitSha = Get-GitBlobSha1 -Bytes $licenseBytes
if ($actualLicenseGitSha -ne $expectedLicenseGitSha) {
    Remove-Item -LiteralPath $licenseDestination -Force
    throw "Pinned ELEMENTS.LICENSE Git blob SHA mismatch: $actualLicenseGitSha"
}

$records | Export-Csv -LiteralPath (Join-Path $assetRoot 'ACQUIRED-ASSET-MANIFEST.csv') -NoTypeInformation -Encoding UTF8
$licenseSha256 = (Get-FileHash -LiteralPath $licenseDestination -Algorithm SHA256).Hash.ToLowerInvariant()
@"
QElectroTech Elements seed acquired from $repository
Pinned commit: $commit
Attribution: The QElectroTech team
License: CC BY 3.0 — see ELEMENTS.LICENSE and https://creativecommons.org/licenses/by/3.0/
License Git blob SHA-1: $actualLicenseGitSha
License SHA-256: $licenseSha256

The downloaded assets are unmodified originals. QET's license permits use, modification and integration into electrical diagrams. If redistributing all or part of the collection outside an electrical diagram, follow CC BY 3.0 attribution conditions. The license prohibits using the collection files as sample data for building ML models.

All assets remain candidate symbols until their exact normative reference, edition and intended diagram context are verified. The folder key en_60617_XX_XX_XX is a QET collection path, not by itself a claim that the item has been cross-checked against IEC 60617:2026 DB.
"@ | Set-Content -LiteralPath (Join-Path $assetRoot 'THIRD_PARTY_NOTICES.md') -Encoding UTF8

Write-Host "Downloaded and verified $($records.Count) symbol assets and ELEMENTS.LICENSE." -ForegroundColor Green
Write-Host "Assets: $assetRoot"
Write-Host 'No application code, electrical model, solver or dependency has been modified.' -ForegroundColor Yellow
