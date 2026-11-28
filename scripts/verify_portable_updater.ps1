[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UpdaterScript,
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [Parameter(Mandatory = $true)][string]$ChecksumPath
)

$ErrorActionPreference = 'Stop'
$updater = (Resolve-Path -LiteralPath $UpdaterScript -ErrorAction Stop).Path
$zip = (Resolve-Path -LiteralPath $ZipPath -ErrorAction Stop).Path
$checksum = (Resolve-Path -LiteralPath $ChecksumPath -ErrorAction Stop).Path
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("PFA portable updater acceptance-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null

function New-TestInstall {
    param([string]$Directory, [string]$Version)
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $Directory 'POWER_FAULT_ANALYZER.exe') -Value "old-$Version" -Encoding ASCII
    $metadata = [ordered]@{
        product = 'POWER_FAULT_ANALYZER'
        version = $Version
        architecture = 'x64'
        git_commit = ('b' * 40)
    }
    $metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $Directory 'BUILD-INFO.json') -Encoding UTF8
}

try {
    # An empty manifest must be logged and rejected before touching the installation.
    $emptyRoot = Join-Path $testRoot 'empty checksum manifest'
    $emptyInstall = Join-Path $emptyRoot 'application'
    New-Item -ItemType Directory -Path $emptyRoot | Out-Null
    New-TestInstall -Directory $emptyInstall -Version 'old-empty-manifest-test'
    $emptyManifest = Join-Path $emptyRoot 'SHA256SUMS.txt'
    $emptyStatusPath = Join-Path $emptyRoot 'updater.status'
    [System.IO.File]::WriteAllText($emptyManifest, [string]::Empty)
    $emptyRejected = $false
    try {
        & $updater -ZipPath $zip -ChecksumPath $emptyManifest -InstallDirectory $emptyInstall -StatusPath $emptyStatusPath
    }
    catch {
        if ($_.Exception.Message -like '*SHA256SUMS.txt is empty*') {
            $emptyRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $emptyRejected) { throw 'An empty checksum manifest was not rejected.' }
    if ((Get-Content -LiteralPath (Join-Path $emptyInstall 'POWER_FAULT_ANALYZER.exe') -Raw).Trim() -ne 'old-old-empty-manifest-test') {
        throw 'An empty checksum manifest modified the existing installation.'
    }
    $emptyLog = Get-ChildItem -LiteralPath $emptyRoot -Filter 'application-update-*.log' -File |
        Select-Object -First 1
    if (-not $emptyLog) { throw 'An empty checksum manifest failure did not produce an update log.' }
    if ((Get-Content -LiteralPath $emptyStatusPath -TotalCount 1) -ne 'failed') {
        throw 'An empty checksum manifest failure did not report a failed handoff status.'
    }
    $emptyLogText = Get-Content -LiteralPath $emptyLog.FullName -Raw
    if (-not $emptyLogText.Contains('status=failure') -or
        -not $emptyLogText.Contains('SHA256SUMS.txt is empty')) {
        throw 'The preflight update log did not record the empty-manifest failure.'
    }

    # The updater must not mutate the installation until the desktop acknowledges
    # that it has received the ready state and is closing.
    $noAckRoot = Join-Path $testRoot 'handoff acknowledgement missing'
    $noAckInstall = Join-Path $noAckRoot 'application'
    New-Item -ItemType Directory -Path $noAckRoot | Out-Null
    New-TestInstall -Directory $noAckInstall -Version 'old-no-ack-test'
    $noAckStatusPath = Join-Path $noAckRoot 'updater.status'
    $noAckRejected = $false
    try {
        & $updater -ZipPath $zip -ChecksumPath $checksum -InstallDirectory $noAckInstall -WaitForProcessId 2147483647 -StatusPath $noAckStatusPath
    }
    catch {
        if ($_.Exception.Message -like '*did not acknowledge the updater handoff*') {
            $noAckRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $noAckRejected) { throw 'Updater did not reject a handoff without desktop acknowledgement.' }
    $noAckInfo = Get-Content -LiteralPath (Join-Path $noAckInstall 'BUILD-INFO.json') -Raw | ConvertFrom-Json
    if ($noAckInfo.version -ne 'old-no-ack-test') {
        throw 'Updater changed the installation before receiving the desktop acknowledgement.'
    }
    if ((Get-Content -LiteralPath $noAckStatusPath -TotalCount 1) -ne 'failed') {
        throw 'Missing handoff acknowledgement did not report a failed updater state.'
    }

    # A checksum mismatch must fail before the existing installation is moved.
    $badRoot = Join-Path $testRoot 'checksum failure'
    $badInstall = Join-Path $badRoot 'application'
    New-Item -ItemType Directory -Path $badRoot | Out-Null
    New-TestInstall -Directory $badInstall -Version 'old-checksum-test'
    $badManifest = Join-Path $badRoot 'SHA256SUMS.txt'
    ('{0}  PFA-Windows-x64.zip' -f ('0' * 64)) |
        Set-Content -LiteralPath $badManifest -Encoding ASCII
    $hashRejected = $false
    try {
        & $updater -ZipPath $zip -ChecksumPath $badManifest -InstallDirectory $badInstall
    }
    catch {
        if ($_.Exception.Message -like '*SHA-256 mismatch*') {
            $hashRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $hashRejected) { throw 'Checksum mismatch was not rejected.' }
    if ((Get-Content -LiteralPath (Join-Path $badInstall 'POWER_FAULT_ANALYZER.exe') -Raw).Trim() -ne 'old-old-checksum-test') {
        throw 'Checksum rejection modified the existing installation.'
    }

    # A replacement that cannot launch must roll back to the previous application.
    $startupRoot = Join-Path $testRoot 'startup failure rollback'
    $startupInstall = Join-Path $startupRoot 'application'
    New-Item -ItemType Directory -Path $startupRoot | Out-Null
    New-TestInstall -Directory $startupInstall -Version 'old-startup-failure-test'
    $startupStatusPath = Join-Path $startupRoot 'updater.status'
    function global:Start-Process {
        [CmdletBinding()]
        param(
            [string]$FilePath,
            [string]$WorkingDirectory,
            [switch]$PassThru
        )
        throw 'Simulated application startup failure.'
    }
    $startupFailureObserved = $false
    try {
        & $updater -ZipPath $zip -ChecksumPath $checksum -InstallDirectory $startupInstall -Restart -StatusPath $startupStatusPath
    }
    catch {
        if ($_.Exception.Message -like '*PFA update failed*') {
            $startupFailureObserved = $true
        }
        else {
            throw
        }
    }
    finally {
        Remove-Item Function:\global:Start-Process -ErrorAction SilentlyContinue
    }
    if (-not $startupFailureObserved) {
        throw 'An application startup failure did not fail the update transaction.'
    }
    $startupRestoredInfo = Get-Content -LiteralPath (Join-Path $startupInstall 'BUILD-INFO.json') -Raw | ConvertFrom-Json
    if ($startupRestoredInfo.version -ne 'old-startup-failure-test') {
        throw 'Failed application startup did not restore the previous installation.'
    }
    $startupFailedPackage = Get-ChildItem -LiteralPath $startupRoot -Directory |
        Where-Object { $_.Name -like 'application.failed-*' } |
        Select-Object -First 1
    if (-not $startupFailedPackage) {
        throw 'Failed replacement package was not quarantined after startup rollback.'
    }
    if ((Get-Content -LiteralPath $startupStatusPath -TotalCount 1) -ne 'rollback_restart_failed') {
        throw 'Failed startup did not report the rollback/restart outcome.'
    }

    # A normal promotion must retain the old application and outside user data.
    $successRoot = Join-Path $testRoot 'successful update'
    $successInstall = Join-Path $successRoot 'application'
    New-Item -ItemType Directory -Path $successRoot | Out-Null
    New-TestInstall -Directory $successInstall -Version 'old-success-test'
    Set-Content -LiteralPath (Join-Path $successInstall 'Uninstall.exe') -Value 'NSIS uninstaller sentinel' -Encoding ASCII
    $uninstallRegistryPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\POWER_FAULT_ANALYZER'
    if (Test-Path -LiteralPath $uninstallRegistryPath) {
        throw 'PFA uninstall registry key unexpectedly exists before the isolated updater test.'
    }
    New-Item -Path $uninstallRegistryPath -Force | Out-Null
    Set-ItemProperty -LiteralPath $uninstallRegistryPath -Name 'DisplayName' -Value 'POWER_FAULT_ANALYZER old-success-test'
    Set-ItemProperty -LiteralPath $uninstallRegistryPath -Name 'DisplayVersion' -Value 'old-success-test'
    $legacyProjectPath = Join-Path $successInstall 'Legacy Project.pfa'
    Set-Content -LiteralPath $legacyProjectPath -Value '{"project":"legacy"}' -Encoding UTF8
    Set-Content -LiteralPath "$legacyProjectPath.network.json" -Value '{"network":"legacy"}' -Encoding UTF8
    $sidecarCollisionProject = Join-Path $successInstall 'Sidecar Collision.pfa'
    Set-Content -LiteralPath $sidecarCollisionProject -Value '{"project":"sidecar-collision"}' -Encoding UTF8
    $projectDirectory = Join-Path $testRoot 'User Documents\POWER_FAULT_ANALYZER\Projects'
    New-Item -ItemType Directory -Path $projectDirectory -Force | Out-Null
    $externalProjectPath = Join-Path $projectDirectory 'Keep.pfa'
    Set-Content -LiteralPath $externalProjectPath -Value '{"project":"preserve"}' -Encoding UTF8
    $collisionProjectPath = Join-Path $projectDirectory 'Legacy Project.pfa'
    Set-Content -LiteralPath $collisionProjectPath -Value '{"project":"existing"}' -Encoding UTF8
    Set-Content -LiteralPath "$collisionProjectPath.network.json" -Value '{"network":"existing"}' -Encoding UTF8
    $sidecarOnlyPath = Join-Path $projectDirectory 'Sidecar Collision.pfa.network.json'
    Set-Content -LiteralPath $sidecarOnlyPath -Value '{"network":"existing-only-sidecar"}' -Encoding UTF8

    $successStatusPath = Join-Path $successRoot 'updater.status'
    $ackJob = Start-Job -ScriptBlock {
        param($StatusFile)
        Start-Sleep -Milliseconds 400
        [System.IO.File]::WriteAllText($StatusFile, 'accepted')
    } -ArgumentList $successStatusPath
    $global:PFA_UpdaterStartProcessCount = 0
    function global:Start-Process {
        [CmdletBinding()]
        param(
            [string]$FilePath,
            [string]$WorkingDirectory,
            [switch]$PassThru
        )
        if ($PassThru) {
            $global:PFA_UpdaterStartProcessCount++
            $fakeProcess = [pscustomobject]@{
                Id = 424242
                HasExited = $false
                ExitCode = 0
            }
            $fakeProcess | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
            return $fakeProcess
        }
    }
    try {
        & $updater -ZipPath $zip -ChecksumPath $checksum -InstallDirectory $successInstall -UserProjectsDirectory $projectDirectory -WaitForProcessId 2147483646 -Restart -StatusPath $successStatusPath
    }
    finally {
        Remove-Item Function:\global:Start-Process -ErrorAction SilentlyContinue
    }
    Wait-Job -Job $ackJob | Out-Null
    Receive-Job -Job $ackJob -ErrorAction Stop | Out-Null
    Remove-Job -Job $ackJob -Force
    if ($global:PFA_UpdaterStartProcessCount -ne 1) {
        throw "Successful update did not launch exactly one replacement application (count: $global:PFA_UpdaterStartProcessCount)."
    }
    Remove-Variable PFA_UpdaterStartProcessCount -Scope Global -ErrorAction SilentlyContinue
    $successStatus = Get-Content -LiteralPath $successStatusPath -Raw
    if (-not $successStatus.StartsWith('success' + [Environment]::NewLine) -or
        $successStatus -notmatch 'automatic restart confirmed') {
        throw "Successful update did not confirm automatic restart: $successStatus"
    }
    $newInfo = Get-Content -LiteralPath (Join-Path $successInstall 'BUILD-INFO.json') -Raw | ConvertFrom-Json
    if ($newInfo.product -ne 'POWER_FAULT_ANALYZER' -or $newInfo.architecture -ne 'x64') {
        throw 'Successful update did not install the expected PFA build.'
    }
    $successBackup = Get-ChildItem -LiteralPath $successRoot -Directory |
        Where-Object { $_.Name -like 'application.backup-*' } |
        Select-Object -First 1
    if (-not $successBackup) { throw 'Successful update did not retain the previous application backup.' }
    if (-not (Test-Path -LiteralPath (Join-Path $successBackup.FullName 'POWER_FAULT_ANALYZER.exe'))) {
        throw 'Previous application backup is incomplete.'
    }
    $updatedUninstaller = Join-Path $successInstall 'Uninstall.exe'
    if (-not (Test-Path -LiteralPath $updatedUninstaller -PathType Leaf)) {
        throw 'In-place update removed the NSIS uninstaller.'
    }
    if ((Get-Content -LiteralPath $updatedUninstaller -Raw).Trim() -ne 'NSIS uninstaller sentinel') {
        throw 'In-place update changed the preserved NSIS uninstaller.'
    }
    $updatedUninstallMetadata = Get-ItemProperty -LiteralPath $uninstallRegistryPath
    if ($updatedUninstallMetadata.DisplayVersion -ne $newInfo.version) {
        throw 'Windows uninstall registry still reports the previous PFA version.'
    }
    if ($updatedUninstallMetadata.DisplayName -ne "POWER_FAULT_ANALYZER $($newInfo.version)") {
        throw 'Windows uninstall display name was not updated to the new PFA version.'
    }
    if (-not (Test-Path -LiteralPath $externalProjectPath -PathType Leaf)) {
        throw 'Update changed a project stored outside the application directory.'
    }
    if ((Get-Content -LiteralPath $collisionProjectPath -Raw).Trim() -ne '{"project":"existing"}') {
        throw 'Migrating legacy projects overwrote an existing user project.'
    }
    if ((Get-Content -LiteralPath "$collisionProjectPath.network.json" -Raw).Trim() -ne '{"network":"existing"}') {
        throw 'Migrating legacy projects overwrote an existing user network sidecar.'
    }
    $migratedProjectPath = Join-Path $projectDirectory 'Legacy Project (migrated 2).pfa'
    if (-not (Test-Path -LiteralPath $migratedProjectPath -PathType Leaf)) {
        throw 'Update did not migrate a project that was stored inside the old application directory.'
    }
    if (-not (Test-Path -LiteralPath "$migratedProjectPath.network.json" -PathType Leaf)) {
        throw 'Update did not migrate the project network sidecar with its project document.'
    }
    $migratedSidecarCollision = Join-Path $projectDirectory 'Sidecar Collision (migrated 2).pfa'
    if (-not (Test-Path -LiteralPath $migratedSidecarCollision -PathType Leaf)) {
        throw 'Update did not migrate a legacy project when only its destination sidecar name was occupied.'
    }
    if ((Get-Content -LiteralPath $migratedSidecarCollision -Raw).Trim() -ne '{"project":"sidecar-collision"}') {
        throw 'Migrated project content changed when avoiding a destination sidecar collision.'
    }
    if ((Get-Content -LiteralPath $sidecarOnlyPath -Raw).Trim() -ne '{"network":"existing-only-sidecar"}') {
        throw 'Migrating a legacy project overwrote a pre-existing orphan network sidecar.'
    }

    # Inject failure on the staging-to-install rename. The third move is rollback.
    $rollbackRoot = Join-Path $testRoot 'rollback update'
    $rollbackInstall = Join-Path $rollbackRoot 'application'
    New-Item -ItemType Directory -Path $rollbackRoot | Out-Null
    New-TestInstall -Directory $rollbackInstall -Version 'old-rollback-test'
    $global:PFA_UpdaterMoveCallCount = 0
    function global:Move-Item {
        [CmdletBinding()]
        param(
            [Parameter(Mandatory = $true)][string]$LiteralPath,
            [Parameter(Mandatory = $true)][string]$Destination,
            [switch]$Force
        )
        $global:PFA_UpdaterMoveCallCount++
        if ($global:PFA_UpdaterMoveCallCount -eq 2) {
            throw 'Simulated promotion failure for rollback acceptance.'
        }
        Microsoft.PowerShell.Management\Move-Item @PSBoundParameters
    }

    $rollbackObserved = $false
    try {
        & $updater -ZipPath $zip -ChecksumPath $checksum -InstallDirectory $rollbackInstall
    }
    catch {
        if ($_.Exception.Message -like '*Simulated promotion failure for rollback acceptance*') {
            $rollbackObserved = $true
        }
        else {
            throw
        }
    }
    finally {
        Remove-Item Function:\global:Move-Item -ErrorAction SilentlyContinue
        Remove-Variable PFA_UpdaterMoveCallCount -Scope Global -ErrorAction SilentlyContinue
    }
    if (-not $rollbackObserved) {
        throw 'Injected promotion failure did not reach the rollback path.'
    }
    $restoredInfo = Get-Content -LiteralPath (Join-Path $rollbackInstall 'BUILD-INFO.json') -Raw | ConvertFrom-Json
    if ($restoredInfo.version -ne 'old-rollback-test') {
        throw 'Rollback did not restore the original application version.'
    }
    $restoredExe = Get-Content -LiteralPath (Join-Path $rollbackInstall 'POWER_FAULT_ANALYZER.exe') -Raw
    if ($restoredExe.Trim() -ne 'old-old-rollback-test') {
        throw 'Rollback did not restore the original executable.'
    }

    Write-Host 'PASS updater rejected checksum mismatch without modifying the installation.' -ForegroundColor Green
    Write-Host 'PASS updater rolled back automatically when the replacement application failed to start.' -ForegroundColor Green
    Write-Host 'PASS updater relaunched the replacement application and confirmed it remained running.' -ForegroundColor Green
    Write-Host 'PASS updater status handshake rejected missing desktop acknowledgement without modifying the installation.' -ForegroundColor Green
    Write-Host 'PASS updater status handshake reported ready and accepted states before applying the replacement.' -ForegroundColor Green
    Write-Host 'PASS updater promoted the new package and retained the previous application.' -ForegroundColor Green
    Write-Host 'PASS NSIS uninstaller and Windows uninstall registry metadata survived the in-place update.' -ForegroundColor Green
    Write-Host 'PASS injected promotion failure restored the original application.' -ForegroundColor Green
    Write-Host 'PASS project documents outside the application directory remained intact.' -ForegroundColor Green
    Write-Host 'PASS legacy project documents and network sidecars inside the old install were migrated to Documents.' -ForegroundColor Green
}
finally {
    Remove-Item Function:\global:Move-Item -ErrorAction SilentlyContinue
    Remove-Variable PFA_UpdaterMoveCallCount -Scope Global -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\POWER_FAULT_ANALYZER' -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
