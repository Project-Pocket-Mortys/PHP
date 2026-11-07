# Use-item client contract

Static evidence from Android 2.41.0 ARM64, not an original-server capture or
Android UI validation. Request/response parsing is recovered; original-server
validation, HTTP statuses, inventory consumption decisions, and multiplayer
calculation formulas are not recovered.

## Reproduce

```powershell
wsl -- bash tools/research/ghidra-use-item.sh
```

The wrapper calls the existing targeted Ghidra driver in default WSL, verifies
`libil2cpp.so` SHA-256
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`,
and exports `.research/ghidra-use-item.json` (ignored). The final pass exported
20 entries without an `error` property. Addresses below are native RVAs;
Ghidra adds image base `0x100000`. Managed parameter types are not imported;
some exception paths extend into adjacent bodies. Conclusions use normal paths
cross-checked with managed signatures/field offsets, not those exception tails.

## Request

`NetworkPlayerAPI.UseItem(string mortyNetId, string itemId,
eAmplitudeUseItemSource source)`, RVA `0x17a46c8`, constructs a request for
`/session/use-item` (literal load at `0x17a47b8`). At `0x17a482c` it calls the
`AnonymousType41<string,string,string>` constructor, passing current session,
Morty ID, then item ID; the result is `NetworkHTTPRequest.postData` at offset
`0x20`. AnonymousType41 in `.research/dumper/dump.cs` names those fields:

```json
{"session_id":"<session>","owned_morty_id":"<owned Morty>","item_id":"ItemSerum"}
```

The source enum is not in this body. No attack position is requested. This is
separate from `UseGeneralItem` and account/shiny-item operations.

## Response

Callback `<UseItem>b__52_0`, RVA `0x17a6a20`, invokes shared
`ParseHTTPResponse<Int32Enum,object>` at `0x17a6ab0`; metadata at `0x17a6aa0`
identifies `<eUseItemError,PlayerUseItemResponse>`. JsonFx deserializes the JSON
body directly into the response type, without a `data` wrapper.
`PlayerUseItemResponse` (`dump.cs:31383`) has exactly:

| Field | Managed type | Offset |
|---|---|---|
| `owned_morty_id` | string | `0x10` |
| `item_id` | string | `0x18` |
| `is_success` | bool | `0x20` |
| `effect_value` | int | `0x24` |
| `owned_morties` | Dictionary<string,object>[] | `0x28` |
| `owned_items` | Dictionary<string,object>[] | `0x30` |
| `attacks_to_learn` | Dictionary<string,object>[] | `0x38` |

The callback stores response/error in `MPPartyInfo`, invokes `UseItemEvent`,
then invokes the API change event if error is `NONE` and response is nonnull.
It does not itself mutate local inventory or Morties.

`MPPartyState.NetUserUseItemsHandler` (`0x15c9aa0`) consumes the response while
active and not transitioning. For a nonnull response it merges both arrays
before checking the enum: `SetMortiesFromDicts(owned_morties,false,false)` and
`SetItemsFromDicts(owned_items,false)`. On enum `NONE` it optionally constructs
attacks-to-learn data, looks up the response Morty ID, and passes the response
item ID, success bool and effect integer to the item UI coroutine. Otherwise
it starts `UseItemFail`. A minimal healing success example is:

```json
{
  "owned_morty_id":"<owned Morty>",
  "item_id":"ItemSerum",
  "is_success":true,
  "effect_value":20,
  "owned_morties":[{"owned_morty_id":"<owned Morty>","hp":40}],
  "owned_items":[{"item_id":"ItemSerum","quantity":0}],
  "attacks_to_learn":[]
}
```

The values are illustrative. Return actual post-operation state. Full typed
Morty records including unchanged attacks are compatible; they are not required
by this consumer. `SetMortiesFromDicts` (`0x158c668`) finds by required
`owned_morty_id`, updating existing objects, or creates a new object.
`MPOpponentMortyData.SetFromDict` (`0x158cb1c`) enumerates present keys, retaining
absent fields. For an already known Morty, an ID plus changed `hp` integer is
sufficient for healing. Partial records are inappropriate for previously
unknown Morties, since missing fields then remain constructor defaults.

Attacks are merged too. `SetAttacksFromDicts` (`0x1581ddc`) matches an explicit
integer `position`, or falls back to existing `attack_id` when position is
absent. `MPAttackData.SetFromDict` (`0x1583dd4`) reads `attack_id` as string and
`pp` as integer. HP healing has no requirement to replace or change attacks;
future AP restoration must send updated PP records for affected attacks.

`SetItemsFromDicts` (`0x158c958`) requires `item_id` and `quantity` per record,
converts quantity to Int16, removes that item if quantity < 1, otherwise sets
its count. The response is a delta, not a clearing inventory snapshot. **Include
the consumed item with quantity zero when the last unit is used.** Omitting
it or sending an empty array retains its previous local count.

## Effects and failure display

`MPItemDefs.GetItemUsedResultText` (`0x176a6ec`) uses `effect_value` as restored
HP in the `RestoreHP` message; `RestorePP` formats it as a percentage and
`Revive` inserts it into the revive percentage message. It is not universally
an absolute amount. `MPPartyUI.<UseItemCo>d__54.MoveNext` (`0x15cd970`) animates
HP toward the updated Morty `hp`, not toward `effect_value`.

A transport success with `is_success:false` still enters the normal item
coroutine. For healing/revive/AP result text the bool is not consulted; it is
used for the level-increase maximum-level message. Therefore it should not be
assumed to provide a general failed-heal UI. A recognized HTTP error avoids
this path.

`MPItemDefs.CanItemBeApplyedToMorty` (`0x176a44c`) rejects HP healing for fainted
or full-HP Morties; AP restore for fainted or already full-AP Morties; revive
for living Morties. Those are client eligibility checks, not proof of the
original server's validation or failed-use consumption policy.

Single-player precedent, explicitly **not recovered multiplayer server code**:
`ItemDefs.ApplyRestoreHPItemToMorty` (`0x166a218`) caps restored HP by missing
HP and displays actual restored HP. `ApplyReviveItemToMorty` (`0x166a5b8`)
truncates the positive `maxHP * percentage / 100` result. `ApplyPPItemToMorty`
(`0x166a4dc`) passes `percentage/100` to `MortyData.RestoreAllPP` (`0x166aabc`),
which adds truncated `maxPP * fraction` to each attack and caps at maximum PP.
Using these formulas for multiplayer remains replacement-server policy until
original multiplayer server behavior is captured.

## Error contract and implementation policy

`eUseItemError` (`dump.cs:30213`) is `UNKOWN=0` (client spelling), `FAILED=1`,
`NONE=2`. Shared `ParseHTTPError<Int32Enum>` (`0x1b569d8`) recognizes enum names
from the non-success response's nested string `error.code`:

```json
{"error":{"code":"FAILED"}}
```

Unknown names fall back to zero on the normal error path. There are no specific
item-invalid, Morty-invalid, or insufficient-inventory enum literals here.
Exact original HTTP statuses and the distinction between invalid, unowned,
missing-inventory, unsupported, and inapplicable item requests remain unknown.
Authenticating the session, owner scoping, atomic inventory/state updates,
rejecting unsupported effects, and choosing appropriate non-success HTTP
statuses with `FAILED` are replacement-server decisions.

The current implementation milestone may support only ordinary out-of-battle
HP items. Blocking active battles, declining revive/AP/stat/account items,
not consuming failed uses, and using actual HP delta for `effect_value` must
be described as supported scope/policy rather than a reconstruction of every
original-server use-item behavior. This endpoint does not establish battle
state synchronization or a requirement for an SSE event.
