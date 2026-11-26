[CmdletBinding()]
param(
    [string]$BranchName = 'product-reboot'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is not installed or is not available on PATH.'
}

$repositoryRoot = & git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0) {
    throw @'
No Git repository exists. Initialize and commit the verified APP-001 baseline BEFORE applying this patch:
  git init
  git add -A
  git commit -m "APP-001 verified baseline before product reboot"
  git tag app-001-verified-baseline
Then apply the patch and rerun this script.
'@
}

if ((Resolve-Path -LiteralPath $repositoryRoot).Path -ne (Resolve-Path -LiteralPath $repoRoot).Path) {
    throw "The script is running inside '$repoRoot', but Git root is '$repositoryRoot'. Run it from the repository root."
}

$tagExists = & git show-ref --verify --quiet 'refs/tags/app-001-verified-baseline'
if ($LASTEXITCODE -ne 0) {
    & git tag app-001-verified-baseline HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Could not tag the current pre-increment baseline.' }
}

$currentBranch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not determine current Git branch.' }
if ($currentBranch -eq $BranchName) {
    Write-Host "Already on branch '$BranchName'. Existing working-tree changes were preserved." -ForegroundColor Green
    exit 0
}

$branchExists = & git show-ref --verify --quiet "refs/heads/$BranchName"
if ($LASTEXITCODE -eq 0) {
    & git switch $BranchName
}
else {
    & git switch -c $BranchName
}
if ($LASTEXITCODE -ne 0) {
    throw "Could not switch to branch '$BranchName'. Resolve Git conflicts and retry."
}

Write-Host "Product reboot branch ready: $BranchName" -ForegroundColor Green
Write-Host 'The APP-001 baseline tag and any uncommitted patch changes were preserved.' -ForegroundColor Green
