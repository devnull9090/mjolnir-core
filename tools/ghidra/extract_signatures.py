# Headless Ghidra Script: MJOLNIR Deep Symbol & Signature Extractor
# Targets: HaloCampaignEvolved.exe & HaloSimulation_tag_release.dll
# Run via: C:\tools\ghidra_12.1.2_PUBLIC\support\analyzeHeadless.bat ...

from ghidra.program.model.symbol import SymbolType
import os

print("==========================================")
print("[MJOLNIR Ghidra] Starting Deep Symbol Dump")
print("Target Program: " + currentProgram.getName())
print("==========================================")

output_file = os.path.join(getScriptArgs()[0] if len(getScriptArgs()) > 0 else ".", "MJOLNIR_GhidraDump_" + currentProgram.getName() + ".txt")

symbolTable = currentProgram.getSymbolTable()
symbols = symbolTable.getAllSymbols(True)

target_keywords = [
    "Console", "ViewportConsole", "GameViewport", "InputSettings",
    "ServerTravel", "ClientTravel", "HostSession", "HaloSimulation",
    "CheatManager", "PlayerController", "GameMode"
]

extracted_lines = []

for symbol in symbols:
    name = symbol.getName()
    for kw in target_keywords:
        if kw.lower() in name.lower():
            addr = symbol.getAddress()
            line = "[SYMBOL] %-50s @ 0x%s" % (name, addr.toString())
            extracted_lines.append(line)
            print(line)

print("[MJOLNIR Ghidra] Found %d matching symbols." % len(extracted_lines))
