[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Executable
)
$ErrorActionPreference = 'Stop'
$exe = (Resolve-Path -LiteralPath $Executable).Path
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("pfa-frozen-worker-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
$request = Join-Path $temp 'request.json'
$response = Join-Path $temp 'response.json'
$source = @'
project = ScriptProject("Frozen portable worker acceptance")
bus = project.add_bus("BUS-13K8-01", voltage_kv=13.8)
project.assert_valid()
workspace = project.render()
'@
@{ source = $source } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $request -Encoding UTF8
try {
    Write-Host '== Frozen automation worker acceptance ==' -ForegroundColor Cyan
    $arguments = @('--pfa-script-worker', ('"' + $request + '"'), ('"' + $response + '"'))
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $exe) -PassThru -Wait
    if ($process.ExitCode -ne 0) {
        throw "Frozen automation worker exited with code $($process.ExitCode)."
    }
    if (-not (Test-Path -LiteralPath $response -PathType Leaf)) {
        throw 'Frozen automation worker did not create its JSON response.'
    }
    $result = Get-Content -LiteralPath $response -Raw | ConvertFrom-Json
    if (-not $result.ok) {
        throw "Frozen automation worker reported $($result.error_type): $($result.error)"
    }
    if ($result.project_name -ne 'Frozen portable worker acceptance') {
        throw 'Frozen automation worker returned an unexpected project name.'
    }
    if (@($result.document.network.buses).Count -ne 1) {
        throw 'Frozen automation worker returned an unexpected bus count.'
    }
    Write-Host 'PASS frozen automation worker produced a valid one-bus workspace.' -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
