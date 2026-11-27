[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [int]$StartupSeconds = 6
)
$ErrorActionPreference = 'Stop'
$exe = (Resolve-Path -LiteralPath $Executable).Path
$previousPlatform = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = 'offscreen'
$process = $null
try {
    Write-Host "Launching frozen application: $exe" -ForegroundColor Cyan
    $process = Start-Process -FilePath $exe -PassThru -WorkingDirectory (Split-Path -Parent $exe)
    Start-Sleep -Seconds $StartupSeconds
    $process.Refresh()
    if ($process.HasExited) {
        throw "Frozen application exited during startup with code $($process.ExitCode)."
    }
    Write-Host "PASS frozen application remained alive for $StartupSeconds seconds." -ForegroundColor Green
}
finally {
    if ($process) {
        $process.Refresh()
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            Write-Host 'Closed the smoke-test application process.'
        }
    }
    $env:QT_QPA_PLATFORM = $previousPlatform
}
