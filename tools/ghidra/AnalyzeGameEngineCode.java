// Headless Ghidra probe: does the simulation DLL still hold executable game-engine
// code for the competitive modes, or only tag definition tables?
//
// The discriminator is where a string is referenced FROM. A tag definition table is
// data describing a layout: its name strings are reached from other data. Running
// game-engine code reaches its strings from instructions. This script classifies
// every reference to a set of probe strings as CODE or DATA and reports the owning
// functions, so the two cases can be told apart rather than guessed at.
//
// @category MJOLNIR

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AnalyzeGameEngineCode extends GhidraScript {

    /**
     * Probe strings, grouped so the report can compare groups against each other.
     *
     * CONTROL_DEFINITION exists to calibrate: these are known tag-definition field
     * names, so whatever reference shape they show is what "definitions only" looks
     * like in this binary. CONTROL_CODE is the opposite calibration — console command
     * names must be registered by code, so they show what a real code reference looks
     * like. The mode groups are then read against those two baselines.
     */
    private static final String[][] GROUPS = {
        {"CONTROL_DEFINITION",
            "game_engine_respawn_options_block",
            "game_engine_team_options_block",
            "game_engine_player_traits_block",
            "megalogamengine_sounds_struct_definition",
            "multiplayer_globals_struct_definition"},

        {"CONTROL_CODE",
            "net_status_sessions",
            "net_force_host",
            "net_build_game_variant",
            "game_set_variant",
            "game_multiplayer"},

        {"CTF",
            "ctf top level options",
            "ctf primary options",
            "ctf carrier traits",
            "flag contested",
            "flag not home",
            "you have flag",
            "enemy has flag"},

        {"OTHER_MODES",
            "slayer top level options",
            "carrying oddball",
            "you control hill",
            "you are juggy",
            "you have bomb",
            "bomb contested"},

        {"ENGINE_RUNTIME",
            "game_engine_status_response_block",
            "game_engine_event_block",
            "game_engine_simulation_dependency_flags",
            "k_maximum_status_response_count",
            "game_engine_globals"},
    };

    /** Functions this big are almost certainly real logic rather than a thunk. */
    private static final long SUBSTANTIAL_BODY_BYTES = 256;

    @Override
    protected void run() throws Exception {
        String[] arguments = getScriptArgs();
        Path outputDirectory = arguments.length > 0
            ? Paths.get(arguments[0])
            : Paths.get(System.getProperty("user.dir"));
        Files.createDirectories(outputDirectory);

        Listing listing = currentProgram.getListing();
        FunctionManager functionManager = currentProgram.getFunctionManager();

        StringBuilder output = new StringBuilder();
        appendLines(output,
            "=== MJOLNIR Game-Engine Code Probe ===",
            "Program: " + currentProgram.getName(),
            "Executable path: " + currentProgram.getExecutablePath(),
            "Executable SHA-256 is verified out of band; MD5 here for cross-check: "
                + currentProgram.getExecutableMD5(),
            "Image base: " + currentProgram.getImageBase(),
            "");

        Map<String, Function> codeFunctions = new LinkedHashMap<>();
        List<String> summary = new ArrayList<>();

        for (String[] group : GROUPS) {
            String groupName = group[0];
            int found = 0;
            int codeRefs = 0;
            int dataRefs = 0;
            int noRefs = 0;
            Set<String> groupFunctions = new LinkedHashSet<>();

            appendLines(output, "=== Group " + groupName + " ===");

            for (int i = 1; i < group.length; i++) {
                String probe = group[i];
                List<Address> hits = findAll(probe.getBytes(StandardCharsets.US_ASCII));
                if (hits.isEmpty()) {
                    appendLines(output, "  " + probe + " | NOT FOUND");
                    continue;
                }
                found++;

                for (Address hit : hits) {
                    int probeCode = 0;
                    int probeData = 0;
                    List<String> detail = new ArrayList<>();

                    ReferenceIterator references =
                        currentProgram.getReferenceManager().getReferencesTo(hit);
                    while (references.hasNext()) {
                        Reference reference = references.next();
                        Address from = reference.getFromAddress();
                        boolean isCode = listing.getInstructionAt(from) != null;
                        Function owner = functionManager.getFunctionContaining(from);

                        if (isCode) {
                            probeCode++;
                            if (owner != null) {
                                codeFunctions.put(owner.getEntryPoint().toString(), owner);
                                groupFunctions.add(owner.getName() + " @ " + owner.getEntryPoint());
                            }
                        } else {
                            probeData++;
                        }

                        detail.add("      " + from
                            + " | " + (isCode ? "CODE" : "DATA")
                            + " | " + reference.getReferenceType()
                            + " | " + (owner == null
                                ? "no containing function"
                                : owner.getName() + " @ " + owner.getEntryPoint()
                                    + " (" + owner.getBody().getNumAddresses() + " bytes)"));
                    }

                    codeRefs += probeCode;
                    dataRefs += probeData;
                    if (probeCode == 0 && probeData == 0) {
                        noRefs++;
                    }

                    appendLines(output, "  " + probe + " @ " + hit
                        + " | code=" + probeCode + " data=" + probeData);
                    for (String line : detail) {
                        appendLines(output, line);
                    }
                }
            }

            appendLines(output, "",
                "  " + groupName + " totals: probes found=" + found
                    + " codeRefs=" + codeRefs
                    + " dataRefs=" + dataRefs
                    + " unreferenced=" + noRefs,
                "");
            summary.add(String.format(
                "%-18s found=%-3d codeRefs=%-5d dataRefs=%-5d unreferenced=%-3d functions=%d",
                groupName, found, codeRefs, dataRefs, noRefs, groupFunctions.size()));
            for (String function : groupFunctions) {
                appendLines(output, "  owning function: " + function);
            }
            appendLines(output, "");
        }

        appendLines(output, "=== Summary ===");
        for (String line : summary) {
            appendLines(output, line);
        }
        appendLines(output, "",
            "Read this against the two controls. If a mode group's codeRefs are ~0 while",
            "CONTROL_CODE's are not, the mode survives as definitions only. If a mode group",
            "shows code references into substantial functions, live game-engine code remains.",
            "");

        List<Function> substantial = new ArrayList<>();
        for (Function function : codeFunctions.values()) {
            if (function.getBody().getNumAddresses() >= SUBSTANTIAL_BODY_BYTES) {
                substantial.add(function);
            }
        }
        substantial.sort(Comparator.comparingLong(
            (Function f) -> f.getBody().getNumAddresses()).reversed());

        appendLines(output, "=== Substantial Code-Referencing Functions ("
            + substantial.size() + " of " + codeFunctions.size() + ") ===");

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        int decompiled = 0;
        for (Function function : substantial) {
            appendLines(output, "",
                "=== " + function.getName() + " @ " + function.getEntryPoint()
                    + " (" + function.getBody().getNumAddresses() + " bytes, "
                    + function.getCalledFunctions(monitor).size() + " callees) ===");
            if (decompiled < 25) {
                appendLines(output, decompile(decompiler, function));
                decompiled++;
            } else {
                appendLines(output, "[decompilation capped at 25 functions]");
            }
        }
        decompiler.dispose();

        Path outputPath = outputDirectory.resolve("HaloSimulation_GameEngineCode.txt");
        Files.write(outputPath, output.toString().getBytes(StandardCharsets.UTF_8));
        println("[MJOLNIR Ghidra] Wrote " + outputPath);
        for (String line : summary) {
            println("[MJOLNIR Ghidra] " + line);
        }
    }

    private List<Address> findAll(byte[] pattern) throws Exception {
        List<Address> hits = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        Address cursor = memory.getMinAddress();
        while (cursor != null && hits.size() < 64) {
            Address match = memory.findBytes(cursor, pattern, null, true, monitor);
            if (match == null) {
                break;
            }
            hits.add(match);
            cursor = match.next();
        }
        return hits;
    }

    private String decompile(DecompInterface decompiler, Function function) {
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
