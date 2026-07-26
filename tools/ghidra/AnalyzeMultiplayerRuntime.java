// Headless Ghidra probe for reflected multiplayer runtime surfaces.
// @category MJOLNIR

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AnalyzeMultiplayerRuntime extends GhidraScript {
    private static final String[] TARGETS = {
        "BlamOnlineSessionSubsystem",
        "IsReadyToPlay",
        "BlamNetworkGameStateComponent",
        "bSessionRunning",
        "BlamNetworkPlayerStateComponent",
        "BlamNetworkInChannelEndpointId",
        "BlamNetworkOutOfBandEndpointId",
        "BlamEndpointGeneration",
        "ServerSetBlamEndpointIds",
        "ServerSetPrimaryPlayerId",
        "IsNetworkCoop",
        "BlamGameEngineCampaignVariant",
        "CampaignVariantStorage",
        "SetActiveCampaign",
        "SetAndBeginCampaign"
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
        List<String> matches = new ArrayList<>();

        for (String target : TARGETS) {
            findMatches(target, target.getBytes(StandardCharsets.US_ASCII), "ASCII",
                functionManager, functions, matches);
            findMatches(target, target.getBytes(StandardCharsets.UTF_16LE), "UTF-16LE",
                functionManager, functions, matches);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        StringBuilder output = new StringBuilder();
        appendLines(output,
            "=== MJOLNIR Multiplayer Runtime Analysis ===",
            "Program: " + currentProgram.getName(),
            "Executable path: " + currentProgram.getExecutablePath(),
            "Executable MD5: " + currentProgram.getExecutableMD5(),
            "Image base: " + currentProgram.getImageBase(),
            "",
            "=== Matches And References (" + matches.size() + ") ===");
        for (String match : matches) {
            appendLines(output, match);
        }

        appendLines(output, "", "=== Owning Functions (" + functions.size() + ") ===");
        for (Function function : functions.values()) {
            appendLines(output,
                "",
                "=== Function " + function.getName() + " @ " + function.getEntryPoint() + " ===",
                "Signature: " + function.getSignature(),
                "Direct callees: " + function.getCalledFunctions(monitor).size(),
                "",
                decompileFunction(decompiler, function));
        }

        decompiler.dispose();
        Path outputPath = outputDirectory.resolve("HaloCampaignEvolved_MultiplayerRuntime.txt");
        Files.write(outputPath, output.toString().getBytes(StandardCharsets.UTF_8));
        println("[MJOLNIR Ghidra] Wrote " + outputPath);
    }

    private void findMatches(
            String target,
            byte[] pattern,
            String encoding,
            FunctionManager functionManager,
            Map<String, Function> functions,
            List<String> matches) throws Exception {
        Memory memory = currentProgram.getMemory();
        Address cursor = memory.getMinAddress();
        int matchCount = 0;
        while (cursor != null) {
            Address match = memory.findBytes(cursor, pattern, null, true, monitor);
            if (match == null) {
                break;
            }

            matchCount++;
            matches.add(target + " | " + encoding + " | " + match);
            ReferenceIterator references = currentProgram.getReferenceManager().getReferencesTo(match);
            int referenceCount = 0;
            while (references.hasNext()) {
                Reference reference = references.next();
                referenceCount++;
                Function function = functionManager.getFunctionContaining(reference.getFromAddress());
                matches.add("  " + reference.getFromAddress() + " ("
                    + reference.getReferenceType() + ") -> "
                    + (function == null ? "no containing function" : function.getName()
                        + " @ " + function.getEntryPoint()));
                if (function != null) {
                    functions.put(function.getEntryPoint().toString(), function);
                }
            }
            if (referenceCount == 0) {
                matches.add("  no references");
            }
            cursor = match.next();
        }
        if (matchCount == 0) {
            matches.add(target + " | " + encoding + " | not found");
        }
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