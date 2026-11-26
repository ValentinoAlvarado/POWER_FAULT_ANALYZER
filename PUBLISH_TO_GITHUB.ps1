[CmdletBinding()]
param(
    [string]$Repository = 'ValentinoAlvarado/POWER_FAULT_ANALYZER',
    [switch]$SkipPagesSetup
)
$ErrorActionPreference = 'Stop'
$Root = (Get-Location).Path
if (-not (Test-Path (Join-Path $Root 'pyproject.toml'))) { throw 'Run this script from the public-source project root.' }
if (-not (Test-Path (Join-Path $Root 'LICENSE')) -or (Get-Item (Join-Path $Root 'LICENSE')).Length -lt 30000) { throw 'GPL license file is missing or incomplete.' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required. Install Git for Windows first.' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI is required. Install with: winget install --id GitHub.cli -e' }

gh auth status
if ($LASTEXITCODE -ne 0) { throw 'Authenticate first with: gh auth login' }
$login = (gh api user --jq .login).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Unable to identify the authenticated GitHub account.' }
if ($login -ne 'ValentinoAlvarado') { throw "Authenticated as '$login', expected 'ValentinoAlvarado'. Refusing to publish to the wrong account." }

# Do not overwrite or push into an existing repository without an explicit migration review.
# Run the expected "repository not found" probe in a child process so Windows PowerShell 5.1
# does not promote gh.exe stderr into a terminating NativeCommandError under ErrorActionPreference=Stop.
$ghPath = (Get-Command gh -ErrorAction Stop).Source
$probeOut = Join-Path $env:TEMP ("pfa-gh-repo-probe-{0}.out" -f [guid]::NewGuid().ToString('N'))
$probeErr = Join-Path $env:TEMP ("pfa-gh-repo-probe-{0}.err" -f [guid]::NewGuid().ToString('N'))
$probe = Start-Process -FilePath $ghPath `
    -ArgumentList @('repo', 'view', $Repository, '--json', 'name', '--jq', '.name') `
    -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $probeOut -RedirectStandardError $probeErr
$probeMessage = ''
if (Test-Path $probeOut) { $probeMessage += (Get-Content $probeOut -Raw -ErrorAction SilentlyContinue) }
if (Test-Path $probeErr) { $probeMessage += (Get-Content $probeErr -Raw -ErrorAction SilentlyContinue) }
Remove-Item $probeOut, $probeErr -Force -ErrorAction SilentlyContinue
if ($probe.ExitCode -eq 0) {
    throw "GitHub repository $Repository already exists. Inspect it and migrate manually; this script will not overwrite it."
}
if ($probeMessage -notmatch '(?i)could not resolve to a repository|not found|http 404|404') {
    throw "Unable to verify whether $Repository exists (gh exit code $($probe.ExitCode)): $probeMessage"
}

if (-not (Test-Path (Join-Path $Root '.git'))) {
    git init -b main
    if ($LASTEXITCODE -ne 0) { throw 'git init failed.' }
}
$branch = (git branch --show-current).Trim()
if ($branch -ne 'main') {
    git branch -M main
    if ($LASTEXITCODE -ne 0) { throw 'Could not set the initial branch to main.' }
}
$remotes = @(git remote)
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect configured Git remotes.' }
if ($remotes -contains 'origin') {
    $origin = (git remote get-url origin).Trim()
    throw "An origin remote already exists ($origin). Review it before publishing; no remote was changed."
}

$userName = git config user.name
if ([string]::IsNullOrWhiteSpace($userName)) { git config user.name 'ValentinoAlvarado' }
$userEmail = git config user.email
if ([string]::IsNullOrWhiteSpace($userEmail)) { git config user.email '147952011+ValentinoAlvarado@users.noreply.github.com' }

git add -A
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    git commit -m 'Initial public source release preparation (GPL-3.0-or-later)'
    if ($LASTEXITCODE -ne 0) { throw 'Initial commit failed.' }
}

$description = 'Open-source power-system engineering workbench and short-circuit analysis platform.'
$homepage = 'https://valentinoalvarado.github.io/POWER_FAULT_ANALYZER/'
gh repo create $Repository --public --source $Root --remote origin --push --description $description --homepage $homepage
if ($LASTEXITCODE -ne 0) { throw 'GitHub repository creation or initial push failed.' }
gh repo edit $Repository --description $description --homepage $homepage --add-topic power-systems --add-topic electrical-engineering --add-topic power-engineering --add-topic short-circuit-analysis --add-topic python --add-topic pyside6
if ($LASTEXITCODE -ne 0) { throw 'Repository metadata update failed.' }

if (-not $SkipPagesSetup) {
    gh api --method POST "repos/$Repository/pages" -f build_type=workflow | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # If Pages already exists, GET succeeds; otherwise surface the setup requirement.
        gh api "repos/$Repository/pages" --jq .html_url | Out-Host
        if ($LASTEXITCODE -ne 0) { Write-Warning 'GitHub Pages could not be enabled by API. In Settings > Pages, choose GitHub Actions as the source.' }
    }
    gh workflow run pages.yml --ref main
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Pages workflow could not be dispatched automatically; run it from the Actions tab after checking Settings > Pages.' }
}
Write-Host 'Repository pushed to GitHub.' -ForegroundColor Green
Write-Host "Source: https://github.com/$Repository"
Write-Host "Website: $homepage"
Write-Host 'The Windows installer is not available until the first tagged release workflow succeeds.' -ForegroundColor Yellow
Write-Host 'After the main branch and Pages deployment are green, publish a preview build with:'
Write-Host '  git tag -a v0.1.0-beta.1 -m "POWER_FAULT_ANALYZER preview release"'
Write-Host '  git push origin v0.1.0-beta.1'
