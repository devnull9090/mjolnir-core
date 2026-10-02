// Decompile a list of functions (by image-relative offset) and write each to a
// text file. Headless usage:
//
//   analyzeHeadless <proj dir> <proj> -process HaloSimulation_tag_release.dll -noanalysis \
//       -scriptPath <this dir> -postScript DecompileList.java <out dir> <rva>...
//
// RVAs are image-relative (as our probes print them); the script adds the
// program's image base.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import java.io.File;
import java.io.PrintWriter;

public class DecompileList extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            println("usage: DecompileList <out dir> <rva>...");
            return;
        }
        File out = new File(args[0]);
        out.mkdirs();
        long base = currentProgram.getImageBase().getOffset();
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        decomp.setOptions(new ghidra.app.decompiler.DecompileOptions());
        for (int i = 1; i < args.length; i++) {
            long rva = Long.parseLong(args[i].replace("0x", ""), 16);
            Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(base + rva);
            Function f = getFunctionContaining(addr);
            if (f == null) {
                f = createFunction(addr, null);
            }
            if (f == null) {
                println("no function at " + addr);
                continue;
            }
            DecompileResults r = decomp.decompileFunction(f, 120, monitor);
            String name = String.format("fn_%x", f.getEntryPoint().getOffset() - base);
            try (PrintWriter w = new PrintWriter(new File(out, name + ".c"))) {
                w.println("// " + f.getName() + " at " + f.getEntryPoint() + " (rva 0x" + Long.toHexString(f.getEntryPoint().getOffset() - base) + ")");
                if (r.decompileCompleted()) {
                    w.println(r.getDecompiledFunction().getC());
                } else {
                    w.println("// decompile failed: " + r.getErrorMessage());
                }
            }
            println("wrote " + name);
        }
        decomp.dispose();
    }
}
