// Decompile functions by RVA and write each to <out>/<rva>.c.
//
// Headless use (after the program has been imported and analysed once):
//   analyzeHeadless <projectDir> <project> -process <program> -noanalysis -readOnly
//       -scriptPath tools/ghidra/scripts -postScript DecompileRvas.java <outDir> <rva> [<rva> ...]
//
// An RVA inside a function decompiles the whole containing function. The output
// is named by the requested RVA, and starts with the function's entry RVA and
// its callers, so a chain can be walked without reopening Ghidra.
//@category MJOLNIR

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

import java.io.File;
import java.io.PrintWriter;

public class DecompileRvas extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            printerr("usage: DecompileRvas.java <outDir> <rva> [<rva> ...]");
            return;
        }
        File out = new File(args[0]);
        out.mkdirs();
        Address base = currentProgram.getImageBase();

        DecompInterface decompiler = new DecompInterface();
        DecompileOptions options = new DecompileOptions();
        decompiler.setOptions(options);
        decompiler.openProgram(currentProgram);

        for (int i = 1; i < args.length; i++) {
            String rva = args[i].replaceFirst("^0x", "");
            Address at = base.add(Long.parseLong(rva, 16));
            Function function = getFunctionContaining(at);
            File file = new File(out, rva + ".c");
            try (PrintWriter writer = new PrintWriter(file, "UTF-8")) {
                if (function == null) {
                    writer.println("// no function contains " + at);
                    println("no function at " + rva);
                    continue;
                }
                long entry = function.getEntryPoint().subtract(base);
                writer.printf("// %s, entry rva 0x%x (asked 0x%s)%n", function.getName(), entry, rva);
                StringBuilder callers = new StringBuilder();
                for (Reference ref : getReferencesTo(function.getEntryPoint())) {
                    Function caller = getFunctionContaining(ref.getFromAddress());
                    callers.append(String.format(" 0x%x", ref.getFromAddress().subtract(base)));
                    if (caller != null) callers.append(String.format("(in 0x%x)", caller.getEntryPoint().subtract(base)));
                }
                writer.println("// referenced from:" + callers);
                DecompileResults results = decompiler.decompileFunction(function, 180, monitor);
                if (results.decompileCompleted()) {
                    writer.println(results.getDecompiledFunction().getC());
                } else {
                    writer.println("// decompile failed: " + results.getErrorMessage());
                }
                println(String.format("decompiled 0x%s -> %s", rva, file));
            }
        }
        decompiler.dispose();
    }
}
