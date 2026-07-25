// Minimal Console Enabler for Halo Campaign Evolved (UE 5.5)
// This writes the proper UE5 config files to enable the developer console
// without injecting any DLLs or hooking any functions.
//
// Usage: dotnet run -- enable   (enables console)
//        dotnet run -- disable  (disables console)

using System;
using System.IO;

class ConsoleEnabler
{
    static void Main(string[] args)
    {
        string configDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Meteorite", "Saved", "Config", "Windows"
        );

        Directory.CreateDirectory(configDir);

        string action = args.Length > 0 ? args[0].ToLower() : "enable";

        if (action == "disable")
        {
            File.Delete(Path.Combine(configDir, "Input.ini"));
            File.Delete(Path.Combine(configDir, "Engine.ini"));
            Console.WriteLine("Console config removed.");
            return;
        }

        // UE5 reads saved config from %LOCALAPPDATA%/<ProjectName>/Saved/Config/Windows/
        // ConsoleKeys in InputSettings tells the engine which keys open the console
        string inputIni = @"[/Script/Engine.InputSettings]
ConsoleKeys=Tilde
ConsoleKeys=F10
ConsoleKeys=Grave
";
        File.WriteAllText(Path.Combine(configDir, "Input.ini"), inputIni);

        // Engine.ini - try to enable the console subsystem
        string engineIni = @"[/Script/Engine.InputSettings]
ConsoleKeys=Tilde
ConsoleKeys=F10

[ConsoleVariables]
AllowConsole=1
";
        File.WriteAllText(Path.Combine(configDir, "Engine.ini"), engineIni);

        Console.WriteLine($"Console config written to: {configDir}");
        Console.WriteLine("Engine.ini and Input.ini created with ConsoleKeys=Tilde,F10,Grave");
        Console.WriteLine("Launch the game normally through Steam - no mod injection needed.");
        Console.WriteLine("Press ~ or F10 in-game to open the console.");
    }
}
