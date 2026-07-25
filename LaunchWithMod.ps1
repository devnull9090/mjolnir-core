# MJOLNIR Framework Launcher for Halo Campaign Evolved
# Injects MJOLNIRTrampoline.dll first (creates FName constructor), then UE4SS.dll
$gameDir = "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Binaries\Win64"
$exePath = Join-Path $gameDir "HaloCampaignEvolved.exe"
$trampolineDll = Join-Path $gameDir "MJOLNIRTrampoline.dll"
$ue4ssDll = Join-Path $gameDir "UE4SS.dll"

# Remove fake dwmapi.dll if present
$dwmPath = Join-Path $gameDir "dwmapi.dll"
if (Test-Path $dwmPath) { Remove-Item $dwmPath -Force }

Write-Host "Launching Halo Campaign Evolved..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $exePath -PassThru

Write-Host "Waiting 5 seconds for game initialization..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

if ($proc -and -not $proc.HasExited) {
    $injectorCode = @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public class MJOLNIRInjector {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr OpenProcess(uint processAccess, bool bInheritHandle, int processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr VirtualAllocEx(IntPtr hProcess, IntPtr lpAddress, uint dwSize, uint flAllocationType, uint flProtect);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool WriteProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, byte[] lpBuffer, uint nSize, out IntPtr lpNumberOfBytesWritten);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr GetProcAddress(IntPtr hModule, string lpProcName);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr GetModuleHandle(string lpModuleName);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr CreateRemoteThread(IntPtr hProcess, IntPtr lpThreadAttributes, uint dwStackSize, IntPtr lpStartAddress, IntPtr lpParameter, uint dwCreationFlags, IntPtr lpThreadId);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint WaitForSingleObject(IntPtr hHandle, uint dwMilliseconds);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool CloseHandle(IntPtr hObject);

    public static bool Inject(int pid, string dllPath, bool waitComplete) {
        IntPtr hProcess = OpenProcess(0x1F0FFF, false, pid);
        if (hProcess == IntPtr.Zero) return false;

        byte[] bytes = Encoding.Unicode.GetBytes(dllPath + "\0");
        IntPtr allocAddr = VirtualAllocEx(hProcess, IntPtr.Zero, (uint)bytes.Length, 0x3000, 0x40);
        if (allocAddr == IntPtr.Zero) return false;

        IntPtr outBytes;
        if (!WriteProcessMemory(hProcess, allocAddr, bytes, (uint)bytes.Length, out outBytes)) return false;

        IntPtr loadLibAddr = GetProcAddress(GetModuleHandle("kernel32.dll"), "LoadLibraryW");
        if (loadLibAddr == IntPtr.Zero) return false;

        IntPtr hThread = CreateRemoteThread(hProcess, IntPtr.Zero, 0, loadLibAddr, allocAddr, 0, IntPtr.Zero);
        if (hThread == IntPtr.Zero) return false;

        if (waitComplete) {
            WaitForSingleObject(hThread, 10000); // Wait up to 10s for DLL to load
            CloseHandle(hThread);
        }

        return true;
    }
}
"@
    if (-not ([System.Management.Automation.PSTypeName]'MJOLNIRInjector').Type) {
        Add-Type -TypeDefinition $injectorCode -Language CSharp
    }

    # Step 1: Inject trampoline DLL first (creates FName constructor)
    Write-Host "Injecting MJOLNIR Trampoline DLL..." -ForegroundColor Cyan
    $result1 = [MJOLNIRInjector]::Inject($proc.Id, $trampolineDll, $true)
    if ($result1) {
        Write-Host "Trampoline DLL injected! FName constructor created." -ForegroundColor Green
    } else {
        Write-Host "Failed to inject trampoline DLL." -ForegroundColor Red
        exit 1
    }

    # Wait a moment for the trampoline to write its address file
    Start-Sleep -Seconds 1

    # Step 2: Inject UE4SS
    Write-Host "Injecting UE4SS Mod Loader..." -ForegroundColor Cyan
    $result2 = [MJOLNIRInjector]::Inject($proc.Id, $ue4ssDll, $false)
    if ($result2) {
        Write-Host "UE4SS injected! Mods should now load." -ForegroundColor Green
    } else {
        Write-Host "Failed to inject UE4SS." -ForegroundColor Red
    }
} else {
    Write-Host "Game process failed to start." -ForegroundColor Red
}
