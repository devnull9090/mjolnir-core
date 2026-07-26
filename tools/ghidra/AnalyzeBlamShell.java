// Headless Ghidra probe for HaloSimulation_tag_release.dll.
// @category MJOLNIR

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.program.model.symbol.SymbolTable;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class AnalyzeBlamShell extends GhidraScript {
    private static final String TARGET_NAME = "CreateBlamEngineShell";
    private static final int MAX_CALLEES = 16;
    private static final int MAX_TABLE_ENTRIES = 96;
    private static final int MAX_DECOMPILED_METHODS = 12;

    @Override
    protected void run() throws Exception {
        String[] arguments = getScriptArgs();
        Path outputDirectory = arguments.length > 0
            ? Paths.get(arguments[0])
            : Paths.get(System.getProperty("user.dir"));
        Files.createDirectories(outputDirectory);

        Function target = findTargetFunction();
        if (target == null) {
            throw new IllegalStateException("Could not find exported function " + TARGET_NAME);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        StringBuilder output = new StringBuilder();
        appendLines(output,
            "=== MJOLNIR HaloSimulation Shell Analysis ===",
            "Program: " + currentProgram.getName(),
            "Executable path: " + currentProgram.getExecutablePath(),
            "Image base: " + currentProgram.getImageBase(),
            "Language: " + currentProgram.getLanguageID(),
            "Compiler: " + currentProgram.getCompilerSpec().getCompilerSpecID(),
            "",
            "=== Export ===",
            describeFunction(target),
            "",
            "=== Export Decompilation ===",
            decompileFunction(decompiler, target));

        List<Reference> references = new ArrayList<>();
        ReferenceIterator referenceIterator = currentProgram.getReferenceManager()
            .getReferencesTo(target.getEntryPoint());
        while (referenceIterator.hasNext()) {
            references.add(referenceIterator.next());
        }

        appendLines(output, "", "=== References To Export (" + references.size() + ") ===");
        for (Reference reference : references.subList(0, Math.min(references.size(), 64))) {
            appendLines(output, reference.getFromAddress() + " -> " + reference.getToAddress()
                + " (" + reference.getReferenceType() + ")");
        }

        List<Function> callees = new ArrayList<>(target.getCalledFunctions(monitor));
        callees.sort(Comparator.comparing(Function::getEntryPoint));
        appendLines(output, "", "=== Direct Internal Callees (" + callees.size() + ") ===");
        for (Function function : callees) {
            appendLines(output, function.getName() + " @ " + function.getEntryPoint()
                + " | " + function.getSignature());
        }

        for (int index = 0; index < Math.min(callees.size(), MAX_CALLEES); index++) {
            Function function = callees.get(index);
            appendLines(output,
                "",
                "=== Callee " + (index + 1) + " ===",
                describeFunction(function),
                "",
                decompileFunction(decompiler, function));
        }

            appendFunctionPointerTables(output, decompiler, target);

        decompiler.dispose();
        Path outputPath = outputDirectory.resolve("HaloSimulation_CreateBlamEngineShell.txt");
        Files.write(outputPath, output.toString().getBytes(StandardCharsets.UTF_8));
        println("[MJOLNIR Ghidra] Wrote " + outputPath);
    }

    private Function findTargetFunction() {
        SymbolTable symbolTable = currentProgram.getSymbolTable();
        FunctionManager functionManager = currentProgram.getFunctionManager();

        for (Symbol symbol : symbolTable.getGlobalSymbols(TARGET_NAME)) {
            Function function = functionManager.getFunctionAt(symbol.getAddress());
            if (function != null) {
                return function;
            }
        }

        SymbolIterator symbols = symbolTable.getAllSymbols(true);
        while (symbols.hasNext()) {
            Symbol symbol = symbols.next();
            if (symbol.getName().toLowerCase().contains(TARGET_NAME.toLowerCase())) {
                Function function = functionManager.getFunctionContaining(symbol.getAddress());
                if (function != null) {
                    return function;
                }
            }
        }

        return null;
    }

    private void appendFunctionPointerTables(
            StringBuilder output,
            DecompInterface decompiler,
            Function target) throws Exception {
        Set<Address> referencedAddresses = new LinkedHashSet<>();
        InstructionIterator instructions = currentProgram.getListing()
            .getInstructions(target.getBody(), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            for (Reference reference : instruction.getReferencesFrom()) {
                Address address = reference.getToAddress();
                if (address.isMemoryAddress() && !target.getBody().contains(address)) {
                    referencedAddresses.add(address);
                }
            }
        }

        appendLines(output, "", "=== Referenced Function-Pointer Tables ===");
        int tableNumber = 0;
        for (Address address : referencedAddresses) {
            List<Function> methods = readFunctionPointerTable(address);
            if (methods.size() < 2) {
                continue;
            }

            tableNumber++;
            Symbol symbol = currentProgram.getSymbolTable().getPrimarySymbol(address);
            appendLines(output,
                "",
                "=== Interface Table " + tableNumber + " ===",
                "Address: " + address,
                "Symbol: " + (symbol == null ? "-" : symbol.getName()),
                "Entries: " + methods.size());

            for (int index = 0; index < methods.size(); index++) {
                Function method = methods.get(index);
                appendLines(output, String.format(
                    "[%02d] %s @ %s | %s",
                    index,
                    method.getName(),
                    method.getEntryPoint(),
                    method.getSignature()));
            }

            for (int index = 0; index < Math.min(methods.size(), MAX_DECOMPILED_METHODS); index++) {
                Function method = methods.get(index);
                appendLines(output,
                    "",
                    "--- Interface Table " + tableNumber + " Method " + index + " ---",
                    decompileFunction(decompiler, method));
            }
        }

        if (tableNumber == 0) {
            appendLines(output, "No contiguous function-pointer tables found.");
        }
    }

    private List<Function> readFunctionPointerTable(Address tableAddress) throws Exception {
        Memory memory = currentProgram.getMemory();
        FunctionManager functionManager = currentProgram.getFunctionManager();
        List<Function> functions = new ArrayList<>();

        for (int index = 0; index < MAX_TABLE_ENTRIES; index++) {
            Address entryAddress = tableAddress.add((long) index * Long.BYTES);
            long pointerValue = memory.getLong(entryAddress);
            Address pointerAddress = currentProgram.getAddressFactory()
                .getDefaultAddressSpace()
                .getAddress(pointerValue);
            MemoryBlock block = memory.getBlock(pointerAddress);
            if (block == null || !block.isExecute()) {
                break;
            }

            Function function = functionManager.getFunctionAt(pointerAddress);
            if (function == null) {
                function = functionManager.getFunctionContaining(pointerAddress);
            }
            if (function == null) {
                disassemble(pointerAddress);
                function = createFunction(pointerAddress, null);
            }
            if (function == null) {
                break;
            }
            functions.add(function);
        }

        return functions;
    }

    private String describeFunction(Function function) {
        return String.join("\n",
            "Name: " + function.getName(),
            "Entry: " + function.getEntryPoint(),
            "Signature: " + function.getSignature(),
            "Calling convention: " + function.getCallingConventionName(),
            "Body addresses: " + function.getBody().getNumAddresses(),
            "Thunk: " + function.isThunk());
    }

    private String decompileFunction(DecompInterface decompiler, Function function) {
        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
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