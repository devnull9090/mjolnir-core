# Run a real PCG editor graph request and require a fresh successful receipt.
param([Parameter(Mandatory = $true)][string]$Request)
$ErrorActionPreference = 'Stop'
$requestFile = (Resolve-Path -LiteralPath $Request).Path
$requestDoc = Get-Content -LiteralPath $requestFile -Raw | ConvertFrom-Json
$receiptFile = [IO.Path]::ChangeExtension($requestFile, '.receipt.json')
$started = [DateTime]::UtcNow
$previousRequest = $env:MJ_PCG_REQUEST
try {
    $env:MJ_PCG_REQUEST = $requestFile
    & powershell -NoProfile -File "$PSScriptRoot/editor_cmd.ps1" -Script Scripts/build_pwr_pcg.py
    if (-not (Test-Path -LiteralPath $receiptFile)) { throw 'PCG did not produce its receipt' }
    if ((Get-Item -LiteralPath $receiptFile).LastWriteTimeUtc -lt $started) { throw 'PCG receipt is stale' }
    $receipt = Get-Content -LiteralPath $receiptFile -Raw | ConvertFrom-Json
    if (@($receipt.jobs).Count -ne @($requestDoc.jobs).Count) { throw 'PCG job count mismatch' }
    foreach ($job in $receipt.jobs) {
        if (-not (Test-Path -LiteralPath $job.output)) { throw "Missing PCG output: $($job.output)" }
        if ((Get-Item -LiteralPath $job.output).LastWriteTimeUtc -lt $started) { throw "Stale PCG output: $($job.output)" }
    }
    Write-Output "PCG completed $(@($receipt.jobs).Count) graph jobs; receipt $receiptFile"
} finally {
    $env:MJ_PCG_REQUEST = $previousRequest
}
