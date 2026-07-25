// Find the real FName constructor by tracing from FName::ToString
// @category MJOLNIR
// @description Finds FName::FName by analyzing the FNamePool

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.pcode.*;

import java.io.*;
import java.util.*;

public class FindRealFNameCtor extends GhidraScript {

    PrintWriter out;
    
    @Override
    public void run() throws Exception {
        String outDir = "C:\\haloce";
        if (getScriptArgs().length > 0) outDir = getScriptArgs()[0];
        
        out = new PrintWriter(new FileWriter(new File(outDir, "fname_analysis.txt")));
        
        FunctionManager fm = currentProgram.getFunctionManager();
        ReferenceManager rm = currentProgram.getReferenceManager();
        Memory mem = currentProgram.getMemory();
        Address imageBase = currentProgram.getImageBase();
        
        // FName::ToString is at RVA 0x36FD8F0
        Address toStringAddr = imageBase.add(0x36FD8F0L);
        Function toStringFn = fm.getFunctionAt(toStringAddr);
        log("FName::ToString at " + toStringAddr + " = " + (toStringFn != null ? toStringFn.getName() : "NOT FOUND"));
        
        // The entry lookup function called by ToString is at RVA 0x36FD080
        Address lookupAddr = imageBase.add(0x36FD080L);
        Function lookupFn = fm.getFunctionAt(lookupAddr);
        log("Entry lookup at " + lookupAddr + " = " + (lookupFn != null ? lookupFn.getName() : "NOT FOUND"));
        
        // The FNamePool global is at RVA 0xD415D80
        Address poolGlobal = imageBase.add(0xD415D80L);
        log("FNamePool global at " + poolGlobal);
        
        // Find all functions that reference the FNamePool global
        Reference[] poolRefs = getReferencesTo(poolGlobal);
        log("\nReferences to FNamePool: " + poolRefs.length);
        
        // Group by containing function
        Map<Address, Integer> funcRefCounts = new HashMap<>();
        for (Reference ref : poolRefs) {
            Function fn = fm.getFunctionContaining(ref.getFromAddress());
            if (fn != null) {
                Address entry = fn.getEntryPoint();
                funcRefCounts.put(entry, funcRefCounts.getOrDefault(entry, 0) + 1);
            }
        }
        
        log("Unique functions referencing FNamePool: " + funcRefCounts.size());
        
        // For each function that references FNamePool, count how many callers it has
        // The FName constructor should have MANY callers
        List<Map.Entry<Address, Integer>> sorted = new ArrayList<>(funcRefCounts.entrySet());
        
        log("\nFunctions referencing FNamePool (with caller counts):");
        for (Map.Entry<Address, Integer> entry : sorted) {
            if (monitor.isCancelled()) break;
            
            Address funcAddr = entry.getKey();
            Function fn = fm.getFunctionAt(funcAddr);
            if (fn == null) continue;
            
            // Count callers
            Reference[] callerRefs = getReferencesTo(funcAddr);
            int callerCount = 0;
            for (Reference cr : callerRefs) {
                if (cr.getReferenceType().isCall()) callerCount++;
            }
            
            long size = fn.getBody().getNumAddresses();
            long rva = funcAddr.subtract(imageBase);
            
            // Read first 32 bytes
            byte[] bytes = new byte[32];
            mem.getBytes(funcAddr, bytes);
            StringBuilder hexStr = new StringBuilder();
            for (byte b : bytes) hexStr.append(String.format("%02X ", b & 0xFF));
            
            log(String.format("  RVA=0x%X size=%d poolRefs=%d callers=%d name=%s",
                rva, size, entry.getValue(), callerCount, fn.getName()));
            log("    " + hexStr.toString().trim());
            
            // Also check callers of THIS function's callers (wrappers)
            if (callerCount > 100 && size < 500) {
                log("    >> HIGH-INTEREST: Many callers + references FNamePool + moderate size");
                
                // Check for small wrapper functions that call this
                for (Reference cr : callerRefs) {
                    if (!cr.getReferenceType().isCall()) continue;
                    Function wrapper = fm.getFunctionContaining(cr.getFromAddress());
                    if (wrapper == null) continue;
                    long wrapSize = wrapper.getBody().getNumAddresses();
                    if (wrapSize < 100) {
                        // Count wrapper's callers
                        Reference[] wrapperCallers = getReferencesTo(wrapper.getEntryPoint());
                        int wc = 0;
                        for (Reference wcr : wrapperCallers) {
                            if (wcr.getReferenceType().isCall()) wc++;
                        }
                        if (wc > 50) {
                            long wrva = wrapper.getEntryPoint().subtract(imageBase);
                            byte[] wb = new byte[32];
                            mem.getBytes(wrapper.getEntryPoint(), wb);
                            StringBuilder whex = new StringBuilder();
                            for (byte b : wb) whex.append(String.format("%02X ", b & 0xFF));
                            log(String.format("      Wrapper RVA=0x%X size=%d callers=%d name=%s",
                                wrva, wrapSize, wc, wrapper.getName()));
                            log("        " + whex.toString().trim());
                        }
                    }
                }
            }
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
