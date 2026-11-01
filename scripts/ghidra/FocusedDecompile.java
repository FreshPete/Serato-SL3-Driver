// Focused fallback when whole-program REA analysis exceeds its startup budget.
// Imports the original without executing it. No whole-program analysis is run.
// Arguments: output JSON, then start:end preferred VAs from PE unwind ranges.
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.Function;
import com.google.gson.*;
import java.nio.file.*;

public class FocusedDecompile extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        JsonObject result = new JsonObject();
        result.addProperty("binary_sha256", currentProgram.getExecutableSHA256());
        result.addProperty("coverage", "Selected unwind ranges only; no whole-program auto-analysis. Types, callers and ABI may be incomplete.");
        JsonArray functions = new JsonArray();
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            for (int i=1; i<args.length; i++) {
                String[] range = args[i].split(":");
                Address start = toAddr(range[0]);
                Address end = toAddr(range[1]).subtract(1);
                new DisassembleCommand(start, new AddressSet(start,end), true).applyTo(currentProgram, monitor);
                Function function = getFunctionAt(start);
                if (function == null) function = createFunction(start, "focused_"+start);
                JsonObject row = new JsonObject();
                row.addProperty("start", start.toString());
                row.addProperty("end_exclusive", toAddr(range[1]).toString());
                if (function == null) {
                    row.addProperty("error", "Function creation failed");
                } else {
                    DecompileResults output = decompiler.decompileFunction(function, 90, monitor);
                    row.addProperty("complete", output.decompileCompleted());
                    row.addProperty("diagnostic", output.getErrorMessage());
                    if (output.getDecompiledFunction()!=null) row.addProperty("pseudocode",output.getDecompiledFunction().getC());
                }
                functions.add(row);
            }
        } finally { decompiler.dispose(); }
        result.add("functions", functions);
        Files.writeString(Path.of(args[0]), new GsonBuilder().setPrettyPrinting().create().toJson(result));
    }
}
