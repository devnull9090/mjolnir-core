// Headless Ghidra probe for the UE5-to-HaloSimulation loader path.
// @category MJOLNIR

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.util.DefinedDataIterator;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AnalyzeBlamLoader extends GhidraScript {
    private static final String[] TARGETS = {
        "HaloSimulation_tag_release.dll",
        "HaloSimulation",
        "tag_release",
        "CreateBlamEngineShell",
        "bDesireClangHaloSimulationDll",
        "RegisterShellOutputHandlerCallbacks",
        "BlamGameEngineVariant",
        "BlamEngineGlueOuterSubsystem",
        "MeteoriteOnlineServices"
    };

    @Override
    protected void run() throws Exception {
        String[] arguments = getScriptArgs();
        Path outputDirectory = arguments.length > 0
            ? Paths.get(arguments[0])
            : Paths.get(System.getProperty("user.dir"));
        Files.createDirectories(outputDirectory);

        FunctionManager functionManager = currentProgram.getFunctionManager();
        Map<String, Function> functions = new LinkedHashMap<>();
        List<String> stringResults = new ArrayList<>();
        Set<String> seenMatches = new HashSet<>();

        for (Data data : DefinedDataIterator.byDataInstance(
            currentProgram,
            candidate -> candidate.hasStringValue())) {
            String value = data.getDefaultValueRepresentation();
            if (!matchesTarget(value)) {
                continue;
            }

            collectMatch(data.getAddress(), value, "defined", functionManager, functions,
                stringResults, seenMatches);
        }

        for (String target : TARGETS) {
            findRawMatches(target, target.getBytes(StandardCharsets.US_ASCII), "ASCII",
                functionManager, functions, stringResults, seenMatches);
            findRawMatches(target, target.getBytes(StandardCharsets.UTF_16LE), "UTF-16LE",
                functionManager, functions, stringResults, seenMatches);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        StringBuilder output = new StringBuilder();
        appendLines(output,
            "=== MJOLNIR Blam Loader Analysis ===",
            "Program: " + currentProgram.getName(),
            "Executable path: " + currentProgram.getExecutablePath(),
            "Executable MD5: " + currentProgram.getExecutableMD5(),
            "Image base: " + currentProgram.getImageBase(),
            "Language: " + currentProgram.getLanguageID(),
            "Compiler: " + currentProgram.getCompilerSpec().getCompilerSpecID(),
            "",
            "=== Matching Strings And References (" + stringResults.size() + ") ===");
        for (String result : stringResults) {
            appendLines(output, result);
        }

        appendLines(output, "", "=== Owning Functions (" + functions.size() + ") ===");
        for (Function function : functions.values()) {
            appendLines(output,
                "",
                "=== Function " + function.getName() + " @ " + function.getEntryPoint() + " ===",
                "Signature: " + function.getSignature(),
                "Calling convention: " + function.getCallingConventionName(),
                "Direct callees: " + function.getCalledFunctions(monitor).size(),
                "",
                decompileFunction(decompiler, function));
        }

        decompiler.dispose();
        Path outputPath = outputDirectory.resolve("HaloCampaignEvolved_BlamLoader.txt");
        Files.write(outputPath, output.toString().getBytes(StandardCharsets.UTF_8));
        println("[MJOLNIR Ghidra] Wrote " + outputPath);
    }

    private void findRawMatches(
            String target,
            byte[] pattern,
            String encoding,
            FunctionManager functionManager,
            Map<String, Function> functions,
            List<String> stringResults,
            Set<String> seenMatches) throws Exception {
        Memory memory = currentProgram.getMemory();
        Address cursor = memory.getMinAddress();
        while (cursor != null) {
            Address match = memory.findBytes(cursor, pattern, null, true, monitor);
            if (match == null) {
                return;
            }
            collectMatch(match, target, encoding, functionManager, functions, stringResults,
                seenMatches);
            cursor = match.next();
        }
    }

    private void collectMatch(
            Address address,
            String value,
            String source,
            FunctionManager functionManager,
            Map<String, Function> functions,
            List<String> stringResults,
            Set<String> seenMatches) {
        String matchKey = address + "|" + value;
        if (!seenMatches.add(matchKey)) {
            return;
        }

        stringResults.add(address + " | " + source + " | " + value);
        ReferenceIterator references = currentProgram.getReferenceManager().getReferencesTo(address);
        while (references.hasNext()) {
            Reference reference = references.next();
            Function function = functionManager.getFunctionContaining(reference.getFromAddress());
            stringResults.add("  " + reference.getFromAddress() + " ("
                + reference.getReferenceType() + ") -> "
                + (function == null ? "no containing function" : function.getName()
                    + " @ " + function.getEntryPoint()));
            if (function != null) {
                functions.put(function.getEntryPoint().toString(), function);
            }
        }
    }

    private boolean matchesTarget(String value) {
        String lowerValue = value.toLowerCase();
        for (String target : TARGETS) {
            if (lowerValue.contains(target.toLowerCase())) {
                return true;
            }
        }
        return false;
    }

    private String decompileFunction(DecompInterface decompiler, Function function) {
        DecompileResults result = decompiler.decompileFunction(function, 180, monitor);
        if (!result.decompileCompleted()) {
            return "[decompile failed] " + result.getErrorMessage();
        }
        return result.getDecompiledFunction().getC();
    }

    private void appendLines(StringBuilder output, String... lines) {
        for (String line : lines) {
            output.append(line).append(System.lineSeparator());
        }
    }
}