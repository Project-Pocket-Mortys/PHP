# Android 2.41.0 multiplayer crafting

This contract is recovered from the ARM64 client, not a capture of the retired server. Method RVAs below refer to `libil2cpp.so` SHA-256 `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`. Ghidra's imported addresses add image base `0x100000`; use `native_rva` in the research output when comparing with the dumper.

## Request

`NetworkPlayerAPI.CraftRecipe` at RVA `0x17a4ccc` constructs a request for `/session/recipe/use`. The anonymous body is exactly:

```json
{"session_id":"<active session>","recipe_id":"RecipeSerum"}
```

The native constructor passes session data's session ID and its `recipeId` argument to anonymous type 43 (`<string,string>`). The method's `quickCraft` Boolean is unused in the recovered constructor and is not a body member. There is no requested quantity, ingredient array, result item, unlock flag, or account identifier in the body. Common HTTP encoding and session validation follow the existing transport contract.

## Success body and inventory semantics

`PlayerCraftRecipeResponse` has `owned_items: Dictionary<string,object>[]` at offset `0x10` and `result: Dictionary<string,object>` at `0x18`. Its native callback at RVA `0x17a985c` accepts success enum `NONE` (`5`), then:

1. Calls `MPOpponentData.SetItemsFromDicts(owned_items, false)`.
2. Constructs `MPRewardData(CRAFT, result)`, with reward source `CRAFT=6`.
3. Applies that reward through `MPPlayerData.ApplyRewardDatas`.
4. Calls the original callback with the reward and success enum.

`SetItemsFromDicts` at RVA `0x158c958` reads `item_id` as string and `quantity` as signed 16-bit integer. Quantities are absolute replacements, not deltas. A quantity less than one removes the local dictionary entry; omitted items remain unchanged because `clear=false`. Return every consumed ingredient, including an explicit zero when its last unit is consumed. A full snapshot that omits exhausted ingredients would leave stale entries.

`MPRewardData.Cast` at RVA `0x165e340` maps these result keys:

| Key | Meaning |
| --- | --- |
| `type` | Reward enum; `ITEM=3` selects item handling. |
| `item_id` | Crafted item ID, mapped to `RewardData.id`. |
| `quantity` | **Final total owned quantity**, mapped to `RewardData.newQuantity`. |
| `amount` | Quantity offered for the reward display. |
| `amount_received` | Quantity received for the reward display. |

`MPPlayerData.ApplyRewardData` at RVA `0x1592464`, item case `3`, performs `items[reward.id] = reward.newQuantity`. It does **not** add `amount_received` or `quantity`. Thus an output already owned twice becomes `quantity:3` after a one-item craft. Including the final output in `owned_items` as well is harmless: the reward writes the same absolute total. Omitting it from `owned_items` also works because `result` sets the final output count.

Example compatible response payload when Battery and Fleeb each fall to zero and Serum rises from two to three:

```json
{
  "owned_items": [
    {"item_id":"ItemBattery","quantity":0},
    {"item_id":"ItemFleeb","quantity":0},
    {"item_id":"ItemSerum","quantity":3}
  ],
  "result": {
    "type":3,
    "item_id":"ItemSerum",
    "quantity":3,
    "amount":1,
    "amount_received":1
  }
}
```

This illustrates the top-level response DTO payload; no extra success flag is required by the recovered consumer. The client body proves the meanings of these fields, not the historical server's exact choice of optional reward fields. The one-result recipe catalog, absence of a batch-count request, and one reward callback support reconstructing one output per accepted craft. The retired server's grant count is not independently observed.

## Recipes, limits, and UI state

`MPRecipeDefs.GetCombinationForRecipeID` at RVA `0x1770ce0` adds each nonempty Slot1, Slot2, and Slot3 to a list; it does not deduplicate. Treat repeated slots as repeated ingredient requirements. The data format contains item IDs per slot, without separate ingredient quantities. `GetCraftableQuantity` at `0x1770ed8` computes the minimum available count across occupied slots; its UI approximation does not aggregate duplicates, so server validation must count repeated ingredients itself.

`MPCraftRecipeUI.RecipeCellSelectedHandler` at `0x159eb08` gates the craft button on ingredient availability and the result item's count being less than **10**. Missing ingredients show `CRAFT_RECIPE_DIAL_MISSING_ITEMS`; output count at least ten shows `CRAFT_RECIPE_DIAL_NOT_ENOUGH_SPACE`. This craft UI uses literal ten rather than calling `GetBagLimit`.

`MPItemDefs.GetBagLimit` at `0x176a300` returns ten for normal items. It returns zero for `ItemCouponMP` and IDs returned by `MPAnimeFTUEDefs.GetAnimeFTUEItemIDs`. The zero's broader meaning should not be guessed from this function alone; it does not change the literal-ten crafting UI check. There is no `ItemInfo` per-row limit field involved in this recovered function.

The multiplayer recipe UI builds cells from `MPRecipeDefs.GetOrderedIds`; cells display result name, description, ingredient icons, and craftable quantity. The inspected multiplayer constructor, cells, request, response DTO, and callback do not read or write owned/known recipe collections or progression unlock fields. `MPCraftRecipeState` fields `_selectedRecipeID`, `_recipeCraftedInVisit`, and `_wentToRewardsScreen` are visit/UI navigation state, not server recipe ownership. Do not invent an unlock requirement from the campaign recipe UI's locked labels. Active/valid recipe membership should be checked against the multiplayer recipe catalog.

## Errors and atomic reconstruction

The managed `eCraftRecipeError` enum is:

| Value | Name |
| --- | --- |
| 0 | `UNKOWN` (client spelling) |
| 1 | `RECIPE_ID_INVALID` |
| 2 | `RECIPE_ITEM_NOT_OWNED` |
| 3 | `RECIPE_ITEM_RESULT_LIMIT` |
| 4 | `FAILED` |
| 5 | `NONE` |

The callback uses the existing `NetworkDefs.ParseHTTPResponse<eCraftRecipeError,PlayerCraftRecipeResponse>` helper. Only `NONE` with a non-null DTO enters inventory mutation. The multiplayer UI uses a generic `MP_CRAFT_ERROR` message on failure rather than differentiating these enum names. Native evidence establishes enum names and consumer behavior; it does not independently establish historical HTTP status codes or error envelope bytes.

Reconstructed server behavior should validate the session, active recipe, aggregate ingredient availability, and output limit before changing inventory. Consume ingredients and grant one output atomically, and return authoritative final counts. A failed validation must not consume ingredients. These transaction guarantees are implementation requirements inferred for coherent gameplay, not recovered server source.

## Reproduction and evidence

The initial pass used REA 6.4.0 through WSL. The default installation is now
[REA 6.8.0](rea-6.8-upgrade.md), verified with a fresh artifact inspection.
The commands and hashes below preserve the initial pass as historical evidence. These exact commands were executed on 2026-11-02 (logs are ignored local research artifacts):

```sh
wsl -- bash tools/research/rea.sh --help
wsl -- bash tools/research/rea.sh doctor --format json
wsl -- bash tools/research/rea.sh inspect-binary-layout .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json
wsl -- bash tools/research/rea.sh inspect-native-instruction .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so 0x17a4ccc --provider ghidra --format json
wsl -- bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json
wsl -- bash tools/research/ghidra-crafting.sh
```

Doctor reported the Ghidra installation/platform/architecture healthy; audit-wide health was false because unrelated optional providers were missing. `inspect-binary-layout` returned `provider_unavailable` for unconfigured `REA_PWNTOOLS_PYTHON`. The exact-address instruction request still started Ghidra import with default analysis; it was cancelled after about one minute when process inspection showed that behavior. Its retained result reports `code:cancelled`, `cleanup:complete`. No successful REA native instruction or function recovery is claimed.

REA `inspect-artifact` successfully authenticated the ELF through `rea-artifact-graph`, evidence ID `ev_f186d965d49e67d5aa3203afcd25b1775b0538889ab893bb183578739e0f9f32`. This supplies provenance, not method-body semantics. Method bodies come from the existing Ghidra `-noanalysis` targeted fallback, selected by `tools/research/ghidra-crafting.sh`: 28 functions recovered. Output includes a known decompiler limitation: exceptional paths sometimes flow into adjacent functions. Conclusions above use the normal paths, dumper field layouts, and exact method boundaries; trailing adjacent-method pseudocode is not treated as crafting logic.

| Local artifact | SHA-256 |
| --- | --- |
| `.research/rea-crafting-artifact.json` | `4ab024f008fdc9af296e97f474bd3e285412bf7686754eceebc6d7c7f2a9898c` |
| `.research/rea-crafting-doctor.json` | `54e1a35e77828f921dd94bb00e31ac237ab5ce03530c88d95a8d011ca322eb6b` |
| `.research/rea-crafting-layout.json` | `974c2b9ea1acb8ddaa6e31faa2b1bfb487de63bf1980f7b61febecd66ed72006` |
| `.research/rea-crafting-instruction.json` | `b55073a799c210a51a063c279dc7f80a623fce64250d8b51acd40966cccf38f0` |
| `.research/ghidra-crafting.json` | `2f89cada5c14f884e6a263a54e302ff49547614c3022fc3d0e8546d877ea3e74` |
| `.research/dumper/dump.cs` | `8b659049aada5d5037f0c4d108d81e8ab9ff5e8127a11dd78f0a3954aeced27e` |
| `.research/dumper/script.json` | `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb` |

The prior linear-reference anchors remain in `docs/protocol/native-transport.json` under `NetworkPlayerAPI$$CraftRecipe` and its display-class callback. Large binaries, dumps, and generated research outputs remain untracked.
