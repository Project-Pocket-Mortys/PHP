// Targeted IL2CPP protocol decompilation. Run with -noanalysis on a disposable import.
// @category PocketMortys
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FlowOverride;
import ghidra.program.model.symbol.SourceType;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class PocketProtocols extends GhidraScript {
    private Address nativeAddress(long offset) { return currentProgram.getImageBase().add(offset); }
    public void run() throws Exception {
        String[] args = getScriptArgs();
        JsonObject mapping = JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonObject();
        JsonArray methods = mapping.getAsJsonArray("ScriptMethod");
        List<JsonObject> selected = new ArrayList<>();
        TreeSet<Long> boundaries = new TreeSet<>();
        for (JsonElement a : mapping.getAsJsonArray("Addresses")) boundaries.add(a.getAsLong());
        for (JsonElement m : methods) boundaries.add(m.getAsJsonObject().get("Address").getAsLong());
        String filter = args.length > 2 ? args[2] : "NetworkBattleAPI\\$\\$(SelectingMove|SelectMove|BattleStartHandler|BattleMoveTimeHandler|BattleTurnResultHandler)|NetworkHTTP\\$\\$Request|NetworkHTTPRequest\\$\\$(GetPostDataJson|\\.ctor)|UdpNodeSender\\$\\$SendPosition";
        Set<Long> labeled = new HashSet<>();
        for (JsonElement element : methods) {
            JsonObject m = element.getAsJsonObject();
            String name = m.get("Name").getAsString();
            long offset = m.get("Address").getAsLong();
            if (offset == 0 || !labeled.add(offset)) continue;
            Address address = nativeAddress(offset);
            if (!currentProgram.getMemory().contains(address)) continue;
            createLabel(address, name.replaceAll("[^A-Za-z0-9_$]", "_"), true);
            // Function entries prevent the decompiler from treating calls as PIC branches.
            if (getFunctionAt(address) == null && getFunctionContaining(address) == null)
                currentProgram.getFunctionManager().createFunction(null, address, new AddressSet(address), SourceType.USER_DEFINED);
            if (name.matches(filter)) selected.add(m);
        }
        for (JsonElement element : mapping.getAsJsonArray("ScriptString")) {
            JsonObject s = element.getAsJsonObject();
            Address address = nativeAddress(s.get("Address").getAsLong());
            if (currentProgram.getMemory().contains(address)) {
                String value = s.get("Value").getAsString();
                String label = "literal_" + value.replaceAll("[^A-Za-z0-9_]", "_");
                if (label.length() > 100) label = label.substring(0,100);
                createLabel(address, label + "_" + address, false);
                setEOLComment(address, value);
            }
        }
        // This build's null-reference throw thunk is two ARM64 instructions with no
        // return epilogue; its callers terminate at BL and the next method follows.
        // Without the non-return annotation Ghidra flows into adjacent methods.
        Address throwThunk = nativeAddress(0x1354d7cL);
        Function throwFunction = getFunctionAt(throwThunk);
        if (throwFunction == null) throwFunction = currentProgram.getFunctionManager().createFunction(
            "il2cpp_null_throw_candidate", throwThunk, new AddressSet(throwThunk, throwThunk.add(7)), SourceType.USER_DEFINED);
        throwFunction.setNoReturn(true);
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        JsonArray results = new JsonArray();
        for (JsonObject m : selected) {
            monitor.checkCancelled();
            String name = m.get("Name").getAsString();
            // Exclude delegates/accessors; retain constructors, requests, callbacks and handlers.
            if (name.contains("Delegate$$") || name.matches(".*\\$\\$(get_|set_|add_|remove_).*")) continue;
            Address address = nativeAddress(m.get("Address").getAsLong());
            Long next = boundaries.higher(m.get("Address").getAsLong());
            if (next == null) continue;
            AddressSet body = new AddressSet(address, nativeAddress(next - 1));
            new DisassembleCommand(address, body, true).applyTo(currentProgram, monitor);
            Function f = getFunctionAt(address);
            if (f == null) f = currentProgram.getFunctionManager().createFunction(null, address, body, SourceType.USER_DEFINED);
            else f.setBody(body);
            var instructions = currentProgram.getListing().getInstructions(body, true);
            while (instructions.hasNext()) {
                var instruction = instructions.next();
                if (instruction.getMnemonicString().equalsIgnoreCase("b")) {
                    for (Address destination : instruction.getFlows()) {
                        if (!body.contains(destination) && getFunctionAt(destination) != null)
                            instruction.setFlowOverride(FlowOverride.CALL_RETURN);
                    }
                }
                if (!instruction.getFlowType().isCall()) continue;
                for (Address destination : instruction.getFlows()) {
                    if (currentProgram.getMemory().contains(destination) && getFunctionContaining(destination) == null)
                        currentProgram.getFunctionManager().createFunction(null, destination, new AddressSet(destination), SourceType.USER_DEFINED);
                }
            }
            decompiler.flushCache();
            JsonObject out = new JsonObject();
            out.addProperty("method", name);
            out.addProperty("address", address.toString());
            out.addProperty("image_base", currentProgram.getImageBase().toString());
            out.addProperty("native_rva", "0x" + Long.toHexString(m.get("Address").getAsLong()));
            out.addProperty("body_bytes", next - m.get("Address").getAsLong());
            out.addProperty("analysis_note", "Build-specific non-return annotation at RVA 0x1354d7c; external B to known method entry marked tail call. Validate against ARM64 disassembly. Managed parameter types not imported.");
            if (f == null) {
                out.addProperty("error", "Function creation failed");
            } else {
                DecompileResults result = decompiler.decompileFunction(f, 20, monitor);
                if (result.decompileCompleted()) out.addProperty("pseudocode", result.getDecompiledFunction().getC());
                else out.addProperty("error", result.getErrorMessage());
            }
            results.add(out);
            Files.writeString(Path.of(args[1]), new GsonBuilder().setPrettyPrinting().create().toJson(results), StandardCharsets.UTF_8);
            println("Decompiled " + name);
        }
        decompiler.dispose();
        Files.writeString(Path.of(args[1]), new GsonBuilder().setPrettyPrinting().create().toJson(results), StandardCharsets.UTF_8);
        println("Pocket Mortys targeted functions: " + results.size());
    }
}
