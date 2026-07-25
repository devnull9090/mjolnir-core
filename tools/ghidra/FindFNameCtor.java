// Find FName Constructor for UE4SS
// @category MJOLNIR
// @description Finds FName::FName(const wchar_t*) constructor for UE4SS
// @author MJOLNIR

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;

import java.io.*;
import java.util.*;

public class FindFNameCtor extends GhidraScript {

    PrintWriter out;
    
    @Override
    public void run() throws Exception {
        String outDir = "C:\\haloce";
        if (getScriptArgs().length > 0) outDir = getScriptArgs()[0];
        
        out = new PrintWriter(new FileWriter(new File(outDir, "ghidra_results.txt")));
        
        log("=== MJOLNIR FName Constructor Finder ===");
        log("Binary: " + currentProgram.getExecutablePath());
        log("Image base: " + currentProgram.getImageBase());
        
        FunctionManager fm = currentProgram.getFunctionManager();
        ReferenceManager rm = currentProgram.getReferenceManager();
        Memory mem = currentProgram.getMemory();
        
        log("Total functions: " + fm.getFunctionCount());
        
        // Known addresses (as RVAs from our analysis):
        // FName::Init (10455 callers): RVA 0x354BDE0
        // Candidate init func (4523 callers): RVA 0x3545FD0
        
        Address imageBase = currentProgram.getImageBase();
        
        // Look at the function at RVA 0x354BDE0 (10455 callers)
        Address initAddr = imageBase.add(0x354BDE0L);
        Function initFunc = fm.getFunctionAt(initAddr);
        log("\n=== FName::Init at " + initAddr + " ===");
        if (initFunc != null) {
            log("Name: " + initFunc.getName());
            log("Signature: " + initFunc.getSignature());
            
            // Find all callers
            Reference[] refs = getReferencesTo(initAddr);
            int callerCount = 0;
            Set<Address> callerFuncs = new HashSet<>();
            for (Reference ref : refs) {
                if (ref.getReferenceType().isCall()) {
                    callerCount++;
                    Function caller = fm.getFunctionContaining(ref.getFromAddress());
                    if (caller != null) callerFuncs.add(caller.getEntryPoint());
                }
            }
            log("Direct callers: " + callerCount);
            log("Unique calling functions: " + callerFuncs.size());
        } else {
            log("No function found at this address (might need re-analysis)");
            // Try creating function here
            log("Attempting to find function containing this address...");
            Function containing = fm.getFunctionContaining(initAddr);
            if (containing != null) {
                log("Containing function: " + containing.getName() + " at " + containing.getEntryPoint());
            }
        }
        
        // Look for wcslen calls - FName(wchar_t*) would call wcslen
        log("\n=== Searching for wcslen-related patterns ===");
        
        // In MSVC x64, wcslen is often inlined as a loop:
        // Look for functions that:
        // 1. Take 2+ params (this + wchar_t*)  
        // 2. Have a strlen-like loop
        // 3. Call into the 10455-caller Init function
        
        // Search for callers of the Init function that are "small wrapper" functions
        if (initFunc != null) {
            Reference[] refs = getReferencesTo(initAddr);
            log("\nSmall wrapper functions that call Init:");
            
            int wrapperCount = 0;
            for (Reference ref : refs) {
                if (monitor.isCancelled()) break;
                if (!ref.getReferenceType().isCall()) continue;
                
                Function caller = fm.getFunctionContaining(ref.getFromAddress());
                if (caller == null) continue;
                
                long size = caller.getBody().getNumAddresses();
                if (size > 200) continue;  // Skip large functions
                
                // Count how many callers this wrapper has
                Reference[] wrapperRefs = getReferencesTo(caller.getEntryPoint());
                int wrapperCallers = 0;
                for (Reference wr : wrapperRefs) {
                    if (wr.getReferenceType().isCall()) wrapperCallers++;
                }
                
                if (wrapperCallers > 50 || (size < 80 && wrapperCallers > 5)) {
                    // Read first 48 bytes
                    byte[] bytes = new byte[48];
                    mem.getBytes(caller.getEntryPoint(), bytes);
                    StringBuilder hexStr = new StringBuilder();
                    for (byte b : bytes) hexStr.append(String.format("%02X ", b & 0xFF));
                    
                    long rva = caller.getEntryPoint().subtract(imageBase);
                    log(String.format("  RVA=0x%X size=%d callers=%d name=%s", 
                        rva, size, wrapperCallers, caller.getName()));
                    log("    Bytes: " + hexStr.toString().trim());
                    wrapperCount++;
                }
            }
            log("Total wrapper functions found: " + wrapperCount);
        }
        
        // Also look at the 4523-caller function
        Address ctor2Addr = imageBase.add(0x3545FD0L);
        Function ctor2Func = fm.getFunctionAt(ctor2Addr);
        log("\n=== Function at RVA 0x3545FD0 (4523 callers) ===");
        if (ctor2Func != null) {
            log("Name: " + ctor2Func.getName());
            log("Signature: " + ctor2Func.getSignature());
            log("Size: " + ctor2Func.getBody().getNumAddresses());
        }
        
        // Look at 0x3555110 (4360 callers) 
        Address ctor3Addr = imageBase.add(0x3555110L);
        Function ctor3Func = fm.getFunctionAt(ctor3Addr);
        log("\n=== Function at RVA 0x3555110 (4360 callers) ===");
        if (ctor3Func != null) {
            log("Name: " + ctor3Func.getName());
            log("Signature: " + ctor3Func.getSignature());
            log("Size: " + ctor3Func.getBody().getNumAddresses());
        }
        
        log("\n=== Analysis Complete ===");
        out.close();
    }
    
    private void log(String msg) {
        println(msg);
        if (out != null) {
            out.println(msg);
            out.flush();
        }
    }
}
