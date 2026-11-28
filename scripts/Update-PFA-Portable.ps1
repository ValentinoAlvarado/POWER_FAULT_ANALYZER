$ErrorActionPreference = 'Stop'
$zip = (Resolve-Path -LiteralPath $ZipPath -ErrorAction Stop).Path
$checksum = (Resolve-Path -LiteralPath $ChecksumPath -ErrorAction Stop).Path
$zipName = Split-Path -Leaf $zip
if ($zipName -ne 'PFA-Windows-x64.zip') {
    throw 'The update archive must be named PFA-Windows-x64.zip.'
}

$install = [System.IO.Path]::GetFullPath($InstallDirectory)
$root = [System.IO.Path]::GetPathRoot($install)
$trimChars = [char[]]@('\', '/')
$install = $install.TrimEnd($trimChars)
if ($install -ieq $root.TrimEnd($trimChars)) {
    throw "Refusing to use a filesystem root as the application directory: $install"
}
$parent = Split-Path -Parent $install
$name = Split-Path -Leaf $install
if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
    throw "Application parent directory does not exist: $parent"
}
if (-not (Test-Path -LiteralPath $install -PathType Container)) {
    throw "Portable application directory does not exist: $install"
}
$exe = Join-Path $install 'POWER_FAULT_ANALYZER.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "The target is not a PFA portable application directory: $install"
}

$token = [guid]::NewGuid().ToString('N')
$staging = Join-Path $parent ".$name.update-$token"
$backup = Join-Path $parent "$name.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')-$token"
$failedInstall = Join-Path $parent "$name.failed-$token"
$logPath = Join-Path $parent "$name-update-$token.log"
$backupMoved = $false
$previousVersion = 'unknown'
$newVersion = 'unknown'
$newCommit = 'unknown'
$actualHash = 'not-verified'
$uninstallRegistryPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\POWER_FAULT_ANALYZER'
$previousUninstallDisplayName = $null
$previousUninstallDisplayVersion = $null
$hadUninstallDisplayName = $false
$hadUninstallDisplayVersion = $false
$uninstallRegistryUpdateStarted = $false

function Write-PFAUpdateLog {
    param([string]$Status, [string]$Detail)
    $lines = @(
        "timestamp_utc=$([DateTime]::UtcNow.ToString('o'))"
        "status=$Status"
        "previous_version=$script:previousVersion"
        "new_version=$script:newVersion"
        "new_commit=$script:newCommit"
        "zip_sha256=$script:actualHash"
        "install_directory=$install"
        "backup_directory=$backup"
        "detail=$Detail"
    )
    try {
        $lines | Set-Content -LiteralPath $logPath -Encoding UTF8
    }
    catch {
        Write-Warning "Could not write update log: $($_.Exception.Message)"
    }
}

function Start-PFAApplication {
    param([string]$ApplicationPath, [string]$WorkingDirectory)
    $lastExitCode = 'unknown'
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        $started = Start-Process -FilePath $ApplicationPath -WorkingDirectory $WorkingDirectory -PassThru -ErrorAction Stop
        Start-Sleep -Seconds 8
        $started.Refresh()
        if (-not $started.HasExited) {
            return $started
        }
        $lastExitCode = $started.ExitCode
        if ($attempt -lt 2) {
            Start-Sleep -Seconds 2
        }
    }
    throw "POWER_FAULT_ANALYZER exited during both startup attempts (last exit code: $lastExitCode)."
}

try {
    if ((Get-Item -LiteralPath $zip -ErrorAction Stop).Length -le 0) {
        throw 'Update archive is empty.'
    }
    if ((Get-Item -LiteralPath $checksum -ErrorAction Stop).Length -le 0) {
        throw 'SHA256SUMS.txt is empty. The installed application was not changed.'
    }

    $expectedHash = $null
    foreach ($line in Get-Content -LiteralPath $checksum -ErrorAction Stop) {
        if ($line -match '^\s*(?<hash>[A-Fa-f0-9]{64})\s+(?<file>.+?)\s*$') {
            if ($Matches.file.Trim().TrimStart('*') -eq $zipName) {
                $expectedHash = $Matches.hash.ToLowerInvariant()
                break
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($expectedHash)) {
        throw "Checksum manifest does not contain an entry for $zipName."
    }
    $actualHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "SHA-256 mismatch for $zipName. The installed application was not changed."
    }

    if ($WaitForProcessId -gt 0) {
        $applicationProcess = Get-Process -Id $WaitForProcessId -ErrorAction SilentlyContinue
        if ($applicationProcess) {
            try {
                Wait-Process -Id $WaitForProcessId -Timeout 90 -ErrorAction Stop
            }
            catch {
                throw "Timed out waiting for POWER_FAULT_ANALYZER to close (PID $WaitForProcessId)."
            }
        }
    }

    $running = Get-CimInstance Win32_Process -Filter "Name='POWER_FAULT_ANALYZER.exe'" |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath -ieq $exe }
    if ($running) {
        throw "Close POWER_FAULT_ANALYZER before updating. Running PID(s): $($running.ProcessId -join ', ')"
    }

    if (Test-Path -LiteralPath $uninstallRegistryPath) {
        $uninstallMetadata = Get-ItemProperty -LiteralPath $uninstallRegistryPath
        if ($uninstallMetadata.PSObject.Properties.Name -contains 'DisplayName') {
            $hadUninstallDisplayName = $true
            $previousUninstallDisplayName = [string]$uninstallMetadata.DisplayName
        }
        if ($uninstallMetadata.PSObject.Properties.Name -contains 'DisplayVersion') {
            $hadUninstallDisplayVersion = $true
            $previousUninstallDisplayVersion = [string]$uninstallMetadata.DisplayVersion
        }
    }

    try {
        $oldBuildInfo = Join-Path $install 'BUILD-INFO.json'
        if (Test-Path -LiteralPath $oldBuildInfo -PathType Leaf) {
            $oldMetadata = Get-Content -LiteralPath $oldBuildInfo -Raw | ConvertFrom-Json
            if (-not [string]::IsNullOrWhiteSpace([string]$oldMetadata.version)) {
                $previousVersion = [string]$oldMetadata.version
            }
        }
    }
    catch {
        $previousVersion = 'unreadable'
    }

    New-Item -ItemType Directory -Path $staging | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $staging -ErrorAction Stop

    $newExe = Join-Path $staging 'POWER_FAULT_ANALYZER.exe'
    $buildInfo = Join-Path $staging 'BUILD-INFO.json'
    $internalDirectory = Join-Path $staging '_internal'
    if (-not (Test-Path -LiteralPath $newExe -PathType Leaf) -or
        (Get-Item -LiteralPath $newExe).Length -le 0) {
        throw 'Update archive does not contain a non-empty POWER_FAULT_ANALYZER.exe at its root.'
    }
    if (-not (Test-Path -LiteralPath $internalDirectory -PathType Container)) {
        throw 'Update archive does not contain the PyInstaller onedir _internal directory.'
    }
    if (-not (Test-Path -LiteralPath $buildInfo -PathType Leaf)) {
        throw 'Update archive does not contain BUILD-INFO.json at its root.'
    }

    $metadata = Get-Content -LiteralPath $buildInfo -Raw | ConvertFrom-Json
    if ($metadata.product -ne 'POWER_FAULT_ANALYZER' -or $metadata.architecture -ne 'x64') {
        throw 'Update archive product or architecture does not match this application.'
    }
    if ([string]::IsNullOrWhiteSpace([string]$metadata.version) -or
        [string]::IsNullOrWhiteSpace([string]$metadata.git_commit)) {
        throw 'Update archive BUILD-INFO.json is missing version or source commit metadata.'
    }
    $newVersion = [string]$metadata.version
    $newCommit = [string]$metadata.git_commit

    Move-Item -LiteralPath $install -Destination $backup -ErrorAction Stop
    $backupMoved = $true

    # Preserve project documents that older builds may have saved in the install
    # directory. New Save/Open dialogs default to Documents instead.
    if ([string]::IsNullOrWhiteSpace($UserProjectsDirectory)) {
        $documentsDirectory = [Environment]::GetFolderPath('MyDocuments')
        if ([string]::IsNullOrWhiteSpace($documentsDirectory)) {
            $documentsDirectory = Join-Path $env:USERPROFILE 'Documents'
        }
        $UserProjectsDirectory = Join-Path $documentsDirectory 'POWER_FAULT_ANALYZER\Projects'
    }
    $userProjectsRoot = [System.IO.Path]::GetFullPath($UserProjectsDirectory)
    $projectDocuments = @(
        Get-ChildItem -LiteralPath $backup -Filter '*.pfa' -File -Recurse -ErrorAction Stop
    )
    $migratedProjectCount = 0
    foreach ($projectDocument in $projectDocuments) {
        $relativeProjectPath = $projectDocument.FullName.Substring($backup.Length).TrimStart($trimChars)
        $destinationProject = Join-Path $userProjectsRoot $relativeProjectPath
        $destinationDirectory = Split-Path -Parent $destinationProject
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null

        if ((Test-Path -LiteralPath $destinationProject) -or (Test-Path -LiteralPath "$destinationProject.network.json")) {
            $destinationName = [System.IO.Path]::GetFileNameWithoutExtension($destinationProject)
            $destinationExtension = [System.IO.Path]::GetExtension($destinationProject)
            $suffix = 2
            do {
                $candidateName = "$destinationName (migrated $suffix)$destinationExtension"
                $candidatePath = Join-Path $destinationDirectory $candidateName
                $candidateSidecar = "$candidatePath.network.json"
                $suffix++
            } while ((Test-Path -LiteralPath $candidatePath) -or (Test-Path -LiteralPath $candidateSidecar))
            $destinationProject = $candidatePath
        }

        Copy-Item -LiteralPath $projectDocument.FullName -Destination $destinationProject -ErrorAction Stop
        $sourceSidecar = "$($projectDocument.FullName).network.json"
        if (Test-Path -LiteralPath $sourceSidecar -PathType Leaf) {
            Copy-Item -LiteralPath $sourceSidecar -Destination "$destinationProject.network.json" -ErrorAction Stop
        }
        $migratedProjectCount++
    }

    $previousUninstaller = Join-Path $backup 'Uninstall.exe'
    $preserveUninstaller = Test-Path -LiteralPath $previousUninstaller -PathType Leaf
    if ($preserveUninstaller) {
        Copy-Item -LiteralPath $previousUninstaller -Destination (Join-Path $staging 'Uninstall.exe') -Force -ErrorAction Stop
    }

    Move-Item -LiteralPath $staging -Destination $install -ErrorAction Stop

    $installedExe = Join-Path $install 'POWER_FAULT_ANALYZER.exe'
    $installedInfo = Join-Path $install 'BUILD-INFO.json'
    if (-not (Test-Path -LiteralPath $installedExe -PathType Leaf) -or
        -not (Test-Path -LiteralPath $installedInfo -PathType Leaf)) {
        throw 'The promoted application failed post-replacement verification.'
    }
    if ($preserveUninstaller -and -not (Test-Path -LiteralPath (Join-Path $install 'Uninstall.exe') -PathType Leaf)) {
        throw 'The NSIS uninstaller was not preserved in the updated application directory.'
    }
    if ($preserveUninstaller -and (Test-Path -LiteralPath $uninstallRegistryPath)) {
        $uninstallRegistryUpdateStarted = $true
        Set-ItemProperty -LiteralPath $uninstallRegistryPath -Name 'DisplayName' -Value "POWER_FAULT_ANALYZER $newVersion" -ErrorAction Stop
        Set-ItemProperty -LiteralPath $uninstallRegistryPath -Name 'DisplayVersion' -Value $newVersion -ErrorAction Stop
    }

    # Keep the backup after success. It is the operator's rollback copy.
    $backupMoved = $false
    $restartDetail = 'automatic restart was not requested'
    if ($Restart) {
        try {
            $restartedProcess = Start-PFAApplication -ApplicationPath (Join-Path $install 'POWER_FAULT_ANALYZER.exe') -WorkingDirectory $install
            $restartDetail = "automatic restart confirmed; process_id=$($restartedProcess.Id)"
        }
        catch {
            $restartDetail = "automatic restart failed: $($_.Exception.Message)"
            Write-Warning "The update succeeded, but the new application did not remain running: $($_.Exception.Message)"
        }
    }
    Write-PFAUpdateLog -Status 'success' -Detail "New application promoted and verified; previous application retained; migrated $migratedProjectCount project document(s) to $userProjectsRoot; $restartDetail."
    Write-Host "PFA updated to version $newVersion." -ForegroundColor Green
    Write-Host "Previous application retained at: $backup" -ForegroundColor Yellow
    Write-Host "Update record: $logPath"
    Write-Host "Migrated project documents found inside the old installation: $migratedProjectCount"
    Write-Host "Project folder: $userProjectsRoot"
    Write-Host 'Projects and Qt preferences outside the application directory were not modified.'
}
catch {
    $updateError = $_
    $rollbackDetail = 'not required'
    if ($backupMoved -and (Test-Path -LiteralPath $backup -PathType Container)) {
        try {
            if (Test-Path -LiteralPath $install) {
                Move-Item -LiteralPath $install -Destination $failedInstall -ErrorAction Stop
                $rollbackDetail = "failed replacement quarantined at $failedInstall"
            }
            Move-Item -LiteralPath $backup -Destination $install -ErrorAction Stop
            $backupMoved = $false
            $rollbackDetail = "previous version $previousVersion restored"
        }
        catch {
            $rollbackDetail = "ROLLBACK FAILED. Previous application remains at $backup. $($_.Exception.Message)"
        }
    }
    if ($uninstallRegistryUpdateStarted -and (Test-Path -LiteralPath $uninstallRegistryPath)) {
        if ($hadUninstallDisplayName) {
            Set-ItemProperty -LiteralPath $uninstallRegistryPath -Name 'DisplayName' -Value $previousUninstallDisplayName -ErrorAction SilentlyContinue
        }
        else {
            Remove-ItemProperty -LiteralPath $uninstallRegistryPath -Name 'DisplayName' -ErrorAction SilentlyContinue
        }
        if ($hadUninstallDisplayVersion) {
            Set-ItemProperty -LiteralPath $uninstallRegistryPath -Name 'DisplayVersion' -Value $previousUninstallDisplayVersion -ErrorAction SilentlyContinue
        }
        else {
            Remove-ItemProperty -LiteralPath $uninstallRegistryPath -Name 'DisplayVersion' -ErrorAction SilentlyContinue
        }
    }
    Write-PFAUpdateLog -Status 'failure' -Detail "$($updateError.Exception.Message); $rollbackDetail"
    if ($Restart -and (Test-Path -LiteralPath (Join-Path $install 'POWER_FAULT_ANALYZER.exe') -PathType Leaf)) {
        try {
            if ($WaitForProcessId -gt 0) {
                try {
                    Wait-Process -Id $WaitForProcessId -Timeout 90 -ErrorAction Stop
                }
                catch {
                    $stillRunning = Get-Process -Id $WaitForProcessId -ErrorAction SilentlyContinue
                    if ($stillRunning) {
                        throw "Original PFA process $WaitForProcessId is still running; refusing to launch a duplicate instance."
                    }
                }
            }
            $restoredProcess = Start-PFAApplication -ApplicationPath (Join-Path $install 'POWER_FAULT_ANALYZER.exe') -WorkingDirectory $install
            Write-Warning "The previous application was restored and restarted (PID $($restoredProcess.Id))."
        }
        catch {
            Write-Warning "The previous application was restored but could not be restarted automatically: $($_.Exception.Message)"
        }
    }
    throw "PFA update failed: $($updateError.Exception.Message). $rollbackDetail. Update record: $logPath"
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not [string]::IsNullOrWhiteSpace($CleanupDirectory)) {
        try {
            $cleanupFullPath = [System.IO.Path]::GetFullPath($CleanupDirectory)
            $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
            if ($cleanupFullPath.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                $escapedCleanupPath = $cleanupFullPath.Replace("'", "''")
                $cleanupCommand = "Start-Sleep -Seconds 8; Remove-Item -LiteralPath '$escapedCleanupPath' -Recurse -Force -ErrorAction SilentlyContinue"
                $encodedCleanupCommand = [Convert]::ToBase64String(
                    [System.Text.Encoding]::Unicode.GetBytes($cleanupCommand)
                )
                $cleanupPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
                Start-Process -FilePath $cleanupPowerShell -ArgumentList @(
                    '-NoLogo', '-NoProfile', '-WindowStyle', 'Hidden',
                    '-EncodedCommand', $encodedCleanupCommand
                ) -WindowStyle Hidden | Out-Null
            }
        }
        catch {
            Write-Warning "Could not schedule temporary update download cleanup: $($_.Exception.Message)"
        }
    }
}
