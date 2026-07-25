# Find FName Constructor for UE4SS - Ghidra Headless Script
# @category MJOLNIR
# @description Finds FName::FName(const wchar_t*) constructor and other UE4SS-required symbols

import ghidra.program.model.symbol.*
import ghidra.program.model.listing.*
import ghidra.program.model.address.*
import ghidra.program.model.mem.*
import ghidra.app.decompiler.*
import java.io.File

outputDir = getScriptArgs()[0] if len(getScriptArgs()) > 0 else "C:\\haloce"
outputFile = File(outputDir, "ghidra_results.txt")

def log(msg):
    println(msg)
    from java.io import FileWriter, PrintWriter
    pw = PrintWriter(FileWriter(outputFile, True))
    pw.println(msg)
    pw.close()

def getBytes(addr, length):
    """Read bytes from the program at the given address."""
    mem = currentProgram.getMemory()
    buf = ghidra.program.model.mem.MemBuffer
    result = []
    for i in range(length):
        try:
            b = mem.getByte(addr.add(i))
            result.append(b & 0xFF)
        except:
            result.append(0)
    return result

def bytesToHex(byteList):
    return " ".join(["%02X" % b for b in byteList])

def findFNameToString():
    """Find FName::ToString - we know it from UE4SS logs."""
    # Search for the string "None" which FName uses as default
    # Also look for characteristic FName::ToString patterns
    listing = currentProgram.getListing()
    mem = currentProgram.getMemory()
    
    # UE4SS found FName::ToString at a specific RVA. Let's compute it.
    # From logs: FName::ToString: 0x7ff668e5d8f0
    # GameEngineTick: 0x7ff66b74d060
    # Difference: 0x7ff66b74d060 - 0x7ff668e5d8f0 = 0x28EF770
    # So FName::ToString is at imageBase + (FNameToString_RVA)
    
    imageBase = currentProgram.getImageBase()
    log("Image base: %s" % str(imageBase))
    
    # Let's look at all functions and find ones related to FName
    # Strategy: Find string references to "None" - this is the default FName value
    results = []
    
    return imageBase

def findFNameConstructor():
    """
    Find FName::FName(const wchar_t*) by searching for the characteristic pattern.
    
    In UE5.5, FName::FName(const TCHAR*) typically:
    1. Takes this (RCX) and Name (RDX) 
    2. Calls FName::Init which does the actual work
    3. FName::Init calls into FNamePool
    
    The function is often small - just a call to Init with extra params.
    """
    listing = currentProgram.getListing()
    fm = currentProgram.getFunctionManager()
    mem = currentProgram.getMemory()
    imageBase = currentProgram.getImageBase()
    
    log("=== Searching for FName Constructor ===")
    log("Total functions: %d" % fm.getFunctionCount())
    
    # Strategy 1: Find functions that reference FNamePool or name-related strings
    # Look for the string "None" which is FName(0)
    strResults = findStrings(None, 4, 1, True, True)  # find wide strings
    noneAddr = None
    
    # Search for wide string L"None" (4E 00 6F 00 6E 00 65 00 00 00)
    searchBytes = [0x4E, 0x00, 0x6F, 0x00, 0x6E, 0x00, 0x65, 0x00, 0x00, 0x00]
    textBlock = mem.getBlock(".rdata")
    if textBlock is None:
        textBlock = mem.getBlock(".data") 
    
    log("Searching for string references...")
    
    # Strategy 2: Look for small functions that:
    # - Take 2-3 parameters (this, name, findtype)
    # - Call exactly one other function (Init)
    # - Are called from MANY places (FName is constructed everywhere)
    
    candidateCount = 0
    bestCandidates = []
    
    funcs = fm.getFunctions(True)  # forward iterator
    for func in funcs:
        if monitor.isCancelled():
            break
            
        # Get function size
        body = func.getBody()
        size = body.getNumAddresses()
        
        # FName constructor is typically small (< 100 bytes) 
        if size > 200 or size < 10:
            continue
        
        # Check parameter count - should be 2-3 (this + name + optional findtype)
        paramCount = func.getParameterCount()
        
        # Count callers - FName constructor is called from thousands of places
        refs = getReferencesTo(func.getEntryPoint())
        callerCount = 0
        for ref in refs:
            if ref.getReferenceType().isCall():
                callerCount += 1
        
        if callerCount > 500:  # FName constructor should have many callers
            entryBytes = getBytes(func.getEntryPoint(), 32)
            hexStr = bytesToHex(entryBytes)
            log("HIGH-CALLER CANDIDATE: %s (size=%d, callers=%d, params=%d)" % (
                str(func.getEntryPoint()), size, callerCount, paramCount))
            log("  Bytes: %s" % hexStr)
            log("  Name: %s" % func.getName())
            bestCandidates.append((func, callerCount, size))
            candidateCount += 1
    
    log("Found %d high-caller candidates" % candidateCount)
    
    # Sort by caller count descending
    bestCandidates.sort(key=lambda x: -x[1])
    
    log("\n=== TOP CANDIDATES (by caller count) ===")
    for i, (func, callers, size) in enumerate(bestCandidates[:20]):
        entryBytes = getBytes(func.getEntryPoint(), 48)
        hexStr = bytesToHex(entryBytes)
        
        # Get the RVA
        rva = func.getEntryPoint().subtract(imageBase)
        
        log("Rank %d: addr=%s RVA=0x%X callers=%d size=%d" % (
            i+1, str(func.getEntryPoint()), rva, callers, size))
        log("  Bytes: %s" % hexStr)
        
        # Try to identify if this function takes a wchar_t* parameter
        # by looking at the decompilation or calling convention
        log("  Signature: %s" % func.getSignature().getPrototypeString())
        log("")

def findConsoleManager():
    """Find IConsoleManager singleton."""
    log("\n=== Searching for ConsoleManager Singleton ===")
    fm = currentProgram.getFunctionManager()
    mem = currentProgram.getMemory()
    
    # ConsoleManager::Get() returns a singleton
    # Look for functions that return a global pointer and are small
    candidates = []
    funcs = fm.getFunctions(True)
    for func in funcs:
        if monitor.isCancelled():
            break
        body = func.getBody()
        size = body.getNumAddresses()
        if size > 30 and size < 5:  # Very small getter
            continue
        # ... similar analysis
    
def findGUObjectArray():
    """Find GUObjectArray global."""
    log("\n=== Searching for GUObjectArray ===")
    # GUObjectArray is accessed frequently for object iteration
    # Look for a global array of UObject pointers

def main():
    log("=" * 60)
    log("MJOLNIR Ghidra Analysis - FName Constructor Finder")
    log("Binary: %s" % currentProgram.getExecutablePath())
    log("Image Base: %s" % str(currentProgram.getImageBase()))
    log("=" * 60)
    
    findFNameConstructor()

main()
