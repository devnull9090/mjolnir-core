using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace MJOLNIR.Launcher
{
    public class Program
    {
        private const string GAME_DIR = @"C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Binaries\Win64";
        private const string GAME_EXE = "HaloCampaignEvolved.exe";
        private const string MOD_SOURCE_DIR = @"C:\haloce";

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr VirtualAllocEx(IntPtr hProcess, IntPtr lpAddress, uint dwSize, uint flAllocationType, uint flProtect);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool WriteProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, byte[] lpBuffer, uint nSize, out IntPtr lpNumberOfBytesWritten);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr CreateRemoteThread(IntPtr hProcess, IntPtr lpThreadAttributes, uint dwStackSize, IntPtr lpStartAddress, IntPtr lpParameter, uint dwCreationFlags, out IntPtr lpThreadId);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr GetProcAddress(IntPtr hModule, string lpProcName);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr GetModuleHandle(string lpModuleName);

        private const uint PROCESS_ALL_ACCESS = 0x1F0FFF;
        private const uint MEM_COMMIT = 0x1000;
        private const uint MEM_RESERVE = 0x2000;
        private const uint PAGE_READWRITE = 0x04;

        public static void Main(string[] args)
        {
            Console.WriteLine("=================================================");
            Console.WriteLine("        MJOLNIR CORE GAME LAUNCHER & INJECTOR    ");
            Console.WriteLine("=================================================");

            DeployModFiles();

            Process gameProcess = FindOrStartGameProcess();
            if (gameProcess == null)
            {
                Console.WriteLine("[MJOLNIR Launcher] Error: Could not locate or start game process.");
                return;
            }

            Console.WriteLine(string.Format("[MJOLNIR Launcher] Target Process Found: {0} (PID: {1})", gameProcess.ProcessName, gameProcess.Id));

            string ue4ssDllPath = Path.Combine(GAME_DIR, "UE4SS.dll");
            if (File.Exists(ue4ssDllPath))
            {
                Console.WriteLine("[MJOLNIR Launcher] Injecting UE4SS.dll into running process...");
                bool injected = InjectDll(gameProcess.Id, ue4ssDllPath);
                if (injected)
                {
                    Console.WriteLine("[MJOLNIR Launcher] SUCCESS: MJOLNIR Core injected successfully into Halo Campaign Evolved!");
                }
                else
                {
                    Console.WriteLine("[MJOLNIR Launcher] Runtime injection returned false.");
                }
            }
            else
            {
                Console.WriteLine(string.Format("[MJOLNIR Launcher] Note: {0} not found.", ue4ssDllPath));
            }
        }

        private static void DeployModFiles()
        {
            try
            {
                Console.WriteLine("[MJOLNIR Launcher] Syncing mod framework files...");
                string[] filesToSync = new string[] { "mods.json", "mods.txt", "UE4SS-settings.ini" };
                foreach (string file in filesToSync)
                {
                    string src = Path.Combine(MOD_SOURCE_DIR, file);
                    string dest = Path.Combine(GAME_DIR, file);
                    if (File.Exists(src))
                    {
                        File.Copy(src, dest, true);
                        Console.WriteLine(string.Format("  -> Synced {0}", file));
                    }
                }

                string srcMods = Path.Combine(MOD_SOURCE_DIR, "Mods");
                string destMods = Path.Combine(GAME_DIR, "Mods");
                if (Directory.Exists(srcMods))
                {
                    CopyDirectory(srcMods, destMods);
                    Console.WriteLine("  -> Synced Mods directory");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine(string.Format("[MJOLNIR Launcher] Deploy Warning: {0}", ex.Message));
            }
        }

        private static void CopyDirectory(string sourceDir, string destinationDir)
        {
            Directory.CreateDirectory(destinationDir);
            foreach (string file in Directory.GetFiles(sourceDir))
            {
                string dest = Path.Combine(destinationDir, Path.GetFileName(file));
                File.Copy(file, dest, true);
            }
            foreach (string subDir in Directory.GetDirectories(sourceDir))
            {
                string dest = Path.Combine(destinationDir, Path.GetFileName(subDir));
                CopyDirectory(subDir, dest);
            }
        }

        private static Process FindOrStartGameProcess()
        {
            Process[] processes = Process.GetProcessesByName(Path.GetFileNameWithoutExtension(GAME_EXE));
            if (processes.Length > 0)
            {
                return processes[0];
            }

            Console.WriteLine("[MJOLNIR Launcher] Game process not running.");
            return null;
        }

        public static bool InjectDll(int processId, string dllPath)
        {
            IntPtr hProcess = OpenProcess(PROCESS_ALL_ACCESS, false, processId);
            if (hProcess == IntPtr.Zero) return false;

            IntPtr loadLibraryAddr = GetProcAddress(GetModuleHandle("kernel32.dll"), "LoadLibraryW");
            if (loadLibraryAddr == IntPtr.Zero) return false;

            uint size = (uint)((dllPath.Length + 1) * sizeof(char));
            IntPtr allocMemAddress = VirtualAllocEx(hProcess, IntPtr.Zero, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
            if (allocMemAddress == IntPtr.Zero) return false;

            byte[] bytes = Encoding.Unicode.GetBytes(dllPath);
            IntPtr bytesWritten;
            if (!WriteProcessMemory(hProcess, allocMemAddress, bytes, (uint)bytes.Length, out bytesWritten)) return false;

            IntPtr threadId;
            IntPtr hThread = CreateRemoteThread(hProcess, IntPtr.Zero, 0, loadLibraryAddr, allocMemAddress, 0, out threadId);
            return hThread != IntPtr.Zero;
        }
    }
}
