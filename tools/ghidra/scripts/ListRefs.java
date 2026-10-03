// List every reference to each RVA (data or code), with the referring function,
// into <out>/refs-<rva>.txt. Companion to DecompileRvas.java.
//
//   analyzeHeadless <projectDir> <project> -process <program> -noanalysis -readOnly
//       -scriptPath tools/ghidra/scripts -postScript ListRefs.java <outDir> <rva> [<rva> ...]
//@category MJOLNIR

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

import java.io.File;
import java.io.PrintWriter;

public class ListRefs extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        File out = new File(args[0]);
        out.mkdirs();
        Address base = currentProgram.getImageBase();
        for (int i = 1; i < args.length; i++) {
            String rva = args[i].replaceFirst("^0x", "");
            Address at = base.add(Long.parseLong(rva, 16));
            try (PrintWriter writer = new PrintWriter(new File(out, "refs-" + rva + ".txt"), "UTF-8")) {
                for (Reference ref : getReferencesTo(at)) {
                    Function f = getFunctionContaining(ref.getFromAddress());
                    writer.printf("0x%x %s %s%n", ref.getFromAddress().subtract(base), ref.getReferenceType(),
                        f == null ? "-" : String.format("in %s 0x%x", f.getName(), f.getEntryPoint().subtract(base)));
                }
            }
            println("refs to 0x" + rva + " written");
        }
    }
}
