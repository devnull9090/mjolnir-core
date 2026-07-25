# MJOLNIR Core - PowerShell Game Launcher & Mod Deployment Script

param (
    [string]$GameDir = "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Binaries\Win64",
    [string]$GameExe = "HaloCampaignEvolved.exe",
    [string]$ModSource = "C:\haloce"
)

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "        MJOLNIR CORE GAME LAUNCHER & INJECTOR    " -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# 1. Sync configuration and mod directories
Write-Host "[1/3] Deploying mod framework files to game directory..." -ForegroundColor Yellow

$filesToCopy = @("mods.json", "mods.txt", "UE4SS-settings.ini")
foreach ($file in $filesToCopy) {
    $src = Join-Path $ModSource $file
    $dest = Join-Path $GameDir $file
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $dest -Force
        Write-Host "  -> Synced $file" -ForegroundColor Green
    }
}

$srcMods = Join-Path $ModSource "Mods"
$destMods = Join-Path $GameDir "Mods"
if (Test-Path $srcMods) {
    Copy-Item -Path $srcMods -Destination $destMods -Recurse -Force
    Write-Host "  -> Synced Mods directory" -ForegroundColor Green
}

# 2. Check for running game process
Write-Host "[2/3] Checking for active Halo Campaign Evolved process..." -ForegroundColor Yellow
$proc = Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($GameExe)) -ErrorAction SilentlyContinue

if (-not $proc) {
    Write-Host "  -> Process not running. Launching game..." -ForegroundColor Yellow
    $exePath = Join-Path $GameDir $GameExe
    if (Test-Path $exePath) {
        Start-Process -FilePath $exePath -WorkingDirectory $GameDir
        Start-Sleep -Seconds 5
        $proc = Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($GameExe)) -ErrorAction SilentlyContinue
    }
}

if ($proc) {
    Write-Host "[3/3] Found Game Process: $($proc.ProcessName) (PID: $($proc.Id))" -ForegroundColor Green
    $ue4ssDll = Join-Path $GameDir "UE4SS.dll"
    if (Test-Path $ue4ssDll) {
        Write-Host "  -> Ready for UE4SS injection / proxy DLL loading into PID $($proc.Id)" -ForegroundColor Green
    } else {
        Write-Host "  -> Note: UE4SS.dll not present in $GameDir. Place UE4SS binaries in game directory." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "Error: Could not locate or start game process." -ForegroundColor Red
}

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "MJOLNIR Core deployment check complete." -ForegroundColor Cyan
