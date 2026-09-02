// Headless Ghidra probe: does the simulation DLL still hold executable game-engine
// code for the competitive modes, or only tag definition tables?
//
// The naive form of this question — "is the string referenced from an instruction?" —
// does not work on this binary. Blam is table-driven: a name string is referenced only
// by a pointer table entry, and the table base is what code touches. A first version of
// this script reported zero code references for every group INCLUDING its own control
// group of known console-command names, which is how we know the one-hop model was
// wrong rather than the modes being absent.
//
// So this walks up. From a string, follow data references to the table entry, find the
// table base (entries in the middle of a table are usually unreferenced, so scan
// backwards for the nearest referenced address), and repeat until the chain reaches an
// instruction. What comes out is the function that ultimately consumes the string, plus
// how many hops away it was.
//
// Two calibration groups anchor the reading: CONTROL_DEFINITION is known tag-definition
// field names, CONTROL_CODE is known console-command names. Mode groups are only
// meaningful when read against both.
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
import ghidra.program.model.symbol.ReferenceManager;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AnalyzeGameEngineCode extends GhidraScript {

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

    /** How many data-to-data hops to follow before giving up on reaching code. */
    private static final int MAX_HOPS = 8;
    /** How far back to scan for a table base, in bytes. */
    private static final int TABLE_SCAN_BYTES = 0x4000;
    /** Pointer stride to step by when scanning backwards for a table base. */
    private static final int POINTER_STRIDE = 8;
    /** Functions at least this large are logic rather than a thunk. */
    private static final long SUBSTANTIAL_BODY_BYTES = 256;

    private Listing listing;
    private FunctionManager functionManager;
    private ReferenceManager referenceManager;

    /** Where a walk ended up. */
    private static final class Landing {
        Function function;
        int hops;
        String trail;
        String outcome;
    }

    @Override
    protected void run() throws Exception {
        String[] arguments = getScriptArgs();
        Path outputDirectory = arguments.length > 0
            ? Paths.get(arguments[0])
            : Paths.get(System.getProperty("user.dir"));
        Files.createDirectories(outputDirectory);

        listing = currentProgram.getListing();
        functionManager = currentProgram.getFunctionManager();
        referenceManager = currentProgram.getReferenceManager();

        StringBuilder output = new StringBuilder();
        appendLines(output,
            "=== MJOLNIR Game-Engine Code Probe (multi-hop) ===",
            "Program: " + currentProgram.getName(),
            "Executable path: " + currentProgram.getExecutablePath(),
            "Executable MD5: " + currentProgram.getExecutableMD5(),
            "Image base: " + currentProgram.getImageBase(),
            "Max hops: " + MAX_HOPS + "   table scan window: 0x"
                + Integer.toHexString(TABLE_SCAN_BYTES) + " bytes",
            "");

        Map<String, Function> reached = new LinkedHashMap<>();
        List<String> summary = new ArrayList<>();

        for (String[] group : GROUPS) {
            String groupName = group[0];
            int probesFound = 0;
            int landedInCode = 0;
            int strandedInData = 0;
            int unreferenced = 0;
            Set<String> groupFunctions = new LinkedHashSet<>();
            long hopTotal = 0;

            appendLines(output, "=== Group " + groupName + " ===");

            for (int i = 1; i < group.length; i++) {
                String probe = group[i];
                List<Address> hits = findAll(probe.getBytes(StandardCharsets.US_ASCII));
                if (hits.isEmpty()) {
                    appendLines(output, "  " + probe + " | NOT FOUND");
                    continue;
                }
                probesFound++;

                // One representative hit per probe keeps the report readable; duplicate
                // string copies land in the same place.
                Address hit = hits.get(0);
                Landing landing = walkToCode(hit);

                if (landing.function != null) {
                    landedInCode++;
                    hopTotal += landing.hops;
                    reached.put(landing.function.getEntryPoint().toString(), landing.function);
                    groupFunctions.add(landing.function.getName()
                        + " @ " + landing.function.getEntryPoint()
                        + " (" + landing.function.getBody().getNumAddresses() + " bytes)");
                } else if ("unreferenced".equals(landing.outcome)) {
                    unreferenced++;
                } else {
                    strandedInData++;
                }

                appendLines(output,
                    "  " + probe + " @ " + hit
                        + " | " + landing.outcome
                        + (landing.function == null
                            ? ""
                            : " in " + landing.function.getName()
                                + " @ " + landing.function.getEntryPoint()
                                + " after " + landing.hops + " hop(s)"),
                    "      trail: " + landing.trail,
                    "  (" + hits.size() + " copies of this string)");
            }

            appendLines(output, "",
                "  " + groupName + " totals: found=" + probesFound
                    + " landedInCode=" + landedInCode
                    + " strandedInData=" + strandedInData
                    + " unreferenced=" + unreferenced,
                "");
            summary.add(String.format(
                "%-18s found=%-3d code=%-3d stranded=%-3d unref=%-3d fns=%-3d avgHops=%s",
                groupName, probesFound, landedInCode, strandedInData, unreferenced,
                groupFunctions.size(),
                landedInCode == 0 ? "-" : String.format("%.1f", (double) hopTotal / landedInCode)));
            for (String function : groupFunctions) {
                appendLines(output, "  reached: " + function);
            }
            appendLines(output, "");
        }

        appendLines(output, "=== Summary ===");
        for (String line : summary) {
            appendLines(output, line);
        }
        appendLines(output, "",
            "How to read it. CONTROL_DEFINITION is the shape of 'definitions only'.",
            "CONTROL_CODE is the shape of 'a real code table'. A mode group that matches",
            "CONTROL_CODE — landing in substantial functions at similar hop counts — means",
            "live game-engine code remains. A mode group that matches CONTROL_DEFINITION,",
            "or that strands in data where CONTROL_CODE reaches code, means the mode",
            "survives as tag definitions only.",
            "",
            "If CONTROL_CODE itself strands, the walk is still not modelling this binary",
            "and NO conclusion should be drawn about the mode groups.",
            "");

        List<Function> substantial = new ArrayList<>();
        for (Function function : reached.values()) {
            if (function.getBody().getNumAddresses() >= SUBSTANTIAL_BODY_BYTES) {
                substantial.add(function);
            }
        }
        substantial.sort(Comparator.comparingLong(
            (Function f) -> f.getBody().getNumAddresses()).reversed());

        appendLines(output, "=== Reached Functions, Substantial First ("
            + substantial.size() + " of " + reached.size() + ") ===");

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        int decompiled = 0;
        for (Function function : substantial) {
            appendLines(output, "",
                "=== " + function.getName() + " @ " + function.getEntryPoint()
                    + " (" + function.getBody().getNumAddresses() + " bytes, "
                    + function.getCalledFunctions(monitor).size() + " callees) ===");
            if (decompiled < 20) {
                appendLines(output, decompile(decompiler, function));
                decompiled++;
            } else {
                appendLines(output, "[decompilation capped at 20 functions]");
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

    /**
     * Follow references up from a string until the chain reaches an instruction.
     *
     * At each hop: if anything referencing the current address is code, we are done.
     * Otherwise step to a data referrer. When an address has no references at all it is
     * usually the interior of a table, so scan backwards for the nearest address that
     * does — that is the table base, and the base is what code holds.
     */
    private Landing walkToCode(Address start) throws Exception {
        Landing landing = new Landing();
        StringBuilder trail = new StringBuilder(start.toString());
        Set<Address> seen = new HashSet<>();

        Address current = start;
        boolean everReferenced = false;

        for (int hop = 1; hop <= MAX_HOPS; hop++) {
            if (!seen.add(current)) {
                landing.outcome = "cycle";
                landing.trail = trail.toString();
                return landing;
            }

            Address dataStep = null;
            boolean referenced = false;

            ReferenceIterator references = referenceManager.getReferencesTo(current);
            while (references.hasNext()) {
                Reference reference = references.next();
                Address from = reference.getFromAddress();
                referenced = true;
                everReferenced = true;

                if (listing.getInstructionAt(from) != null) {
                    Function owner = functionManager.getFunctionContaining(from);
                    trail.append(" -> CODE ").append(from);
                    landing.function = owner;
                    landing.hops = hop;
                    landing.trail = trail.toString();
                    landing.outcome = owner == null
                        ? "reached code outside any function"
                        : "reached code";
                    return landing;
                }
                if (dataStep == null) {
                    dataStep = from;
                }
            }

            if (dataStep == null) {
                // Nothing points here. Most likely a table interior; find the base.
                Address base = scanBackForReferencedAddress(current);
                if (base == null) {
                    landing.outcome = everReferenced || referenced
                        ? "stranded in data"
                        : "unreferenced";
                    landing.trail = trail.toString();
                    return landing;
                }
                trail.append(" ~> base ").append(base);
                current = base;
                continue;
            }

            trail.append(" -> data ").append(dataStep);
            current = dataStep;
        }

        landing.outcome = "stranded in data (hop limit)";
        landing.trail = trail.toString();
        return landing;
    }

    /**
     * Walk backwards in pointer-sized steps looking for an address something refers to.
     * Table entries in the middle of an array are unreferenced; the base is not.
     */
    private Address scanBackForReferencedAddress(Address from) {
        Memory memory = currentProgram.getMemory();
        for (int offset = POINTER_STRIDE; offset <= TABLE_SCAN_BYTES; offset += POINTER_STRIDE) {
            Address candidate;
            try {
                candidate = from.subtract(offset);
            } catch (Exception e) {
                return null;
            }
            if (!memory.contains(candidate)) {
                return null;
            }
            if (referenceManager.getReferenceCountTo(candidate) > 0) {
                return candidate;
            }
        }
        return null;
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
