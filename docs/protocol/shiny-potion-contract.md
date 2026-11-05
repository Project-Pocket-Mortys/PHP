# Shiny Potion activation contract

Android 2.41.0 ships a distinct account consumable, `ItemShinyPotion`. Actual
MP `ItemInfo` says `effect_type=ShinyPotion`, `use_world=true`,
`use_account=true`, `use_self=false`, `use_battle=false`. Its English description
specifies a two-hour increase in Shiny encounters. The duration is independently
supported; no numeric encounter probability is supplied.

## Reproduction and evidence limits

Run `bash tools/research/ghidra-shiny-potion.sh` under WSL. It uses the pinned
REA 6.8.0 wrapper, verifies the Android ARM64 build via the Ghidra wrapper,
exports bounded decompilation and ARM64 disassembly, and reads the actual MP and
English bundles with UnityPy. Ignored outputs are
`.research/rea-shiny-potion-6.8.0-artifact.json`,
`.research/ghidra-shiny-potion.json`, `.research/shiny-potion-arm64.txt` and
`.research/shiny-potion-metadata.json`. The native hash is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.
Actual bundle hashes and their preserved-extraction differences are documented
in [use-item-data.md](use-item-data.md).

The callback decompilation includes a fall-through into the next method after
its genuine return because the dumper method bounds are loose. ARM64 confirms
the real callback returns at `0x17a94f0`; subsequent HealActiveMortyDeck code
does not belong to this contract. Startup array handling and the variant getter
were also checked directly in ARM64.

## Request and response

`NetworkPlayerAPI.UseShinyPotion` (`0x17a423c`) sends
`/session/use-shiny-potion` with the one-field body `{"session_id":"..."}`.
There is no caller-supplied item, target Morty, duration or quantity. It first
calls `DoesPlayerAlreadyHaveActiveShinyPotion` (`0x1771744`), which checks the
locally saved expiry against `UtcNow` and displays an already-active popup
instead of making another request when expiry is in the future.

The callback (`0x17a9240`) parses `PlayerUseShinyPotionResponse` through the
normal HTTP response parser, using `eUseShinyPotionError`. Its enum values are:

| Value | Meaning |
|---|---|
| 0 | UNKNOWN |
| 1 | NOT_ENOUGH_SHINY_POTIONS |
| 2 | ALREADY_ACTIVE_SHINY_POTION |
| 3 | SHINY_POTIONS_IN_MAINTENANCE_MODE |
| 4 | NONE / success |

On success, the typed response body contains:

```json
{
  "quantity": 0,
  "shiny_potion_active": true,
  "end_usage_time": "2026-11-05T17:00:00Z",
  "shiny_potion_item_id": "ItemShinyPotion"
}
```

The example timestamp is illustrative. `quantity` is the absolute remaining
inventory, including zero. The callback passes the bool/DateTime directly to
`MPShinyPotionData.SetShinyPotion` (`0x165f33c`), then constructs an
`item_id`/`quantity` dictionary and merges it through
`MPOpponentData.SetItemsFromDicts`. This is separate from world `UseItem` and
opaque `UseGeneralItem` responses.

## Startup, expiry and stacking

`MPPlayerData.SetFromDict` (`0x15901b4`) reads `play_shiny_potion`, converts it
to a dictionary array and calls `MPShinyPotionData.SetupFromDict`
(`0x165f148`). A null value clears the active flag and locally saved expiry.
A non-null array must have a first dictionary, containing an `end_usage_time`
string accepted by `DateTime.Parse`. Active status derives from
`UtcNow < end_usage_time`; the startup dictionary needs no bool or item ID.

```json
{"play_shiny_potion":[{"end_usage_time":"2026-11-05T17:00:00Z"}]}
```

Use null for inactive state. An empty array triggers the native index-out-of-
bounds path and must not be emitted. An ISO 8601 UTC string is a compatible
representation; the original server's exact timestamp spelling is unknown.

`CheckIfShinyPotionDone` (`0x165f0bc`) clears active status and invokes the
registered callback after expiry. `NetworkPlayerAPI.ShinyPotionExpired`
(`0x17a6774`) also calls `MPShinyPotionDefs.OnShinyPotionExpiry`
(`0x1772198`), clearing local active state. This supports both local clock and
server event expiry handling, without requiring a new transport timer.

Client-side active-use denial and error enum 2 support rejecting another use
while an unexpired activation exists. An implementation can consume exactly
one potion and persist `now + 7200 seconds` atomically, returning actual
remaining stock. Server concurrency guards and HTTP rejection wording/status
are implementation policy; the original service's transaction behavior and
error envelope have not been captured. No endpoint-level battle-state check
appears in the native request constructor. The catalog's `use_battle=false`
describes item availability; it alone does not prove an original HTTP rule
about concurrent battles.

## Conditional wild variants

`MPOpponentMortyData.variant` getter (`0x158e478`) implements this exact order:

1. If the local player's Shiny Potion is inactive, return the stored variant.
2. If the selected Morty is not wild, return its stored variant.
3. If its stored variant is Shiny or Pulsing, return that variant.
4. Otherwise return `isShinyIfShinyPotionActive` as Normal (false) or Shiny (true).

The getter reads the existing eligibility flag; it rolls no probability.
`MPOpponentData.GetMortyData(MPOpponentData)` (`0x158daec`) finds the matching
existing Morty and copies top-level `shiny_if_potion` into that Morty's flag.
It does not construct a Morty, change its ID, or set its wild marker.
`MPOpponentMortyNode.EnableAnimations` (`0x161e174`) calls the conditional
getter both for the Shiny game-object toggle and for material variant selection.
This establishes an actual rendering consumer of the account activation.

The server currently has a pre-existing `shiny_if_potion` generator. Its
placeholder probability is not recovered original-game behavior and must not
be presented as such. Activation can preserve those existing flags/probabilities.
For a newly created wild battle, selecting Shiny when activation is unexpired,
the existing flag is true and the base variant is Normal follows the native
conditional rule. Applying that selection to the battle snapshot is a server
compatibility decision, not proof of the original service's precise wire
representation. Existing battle IDs, replay behavior and already-selected
variants must remain stable; no captured-ownership rule follows from this work.

Capture remains a separate unresolved contract. No probability, spawn generation,
capture formula, seed amount or XP growth rule is established by this audit.
