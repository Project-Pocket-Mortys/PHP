# Multiplayer poison/paralysis cure contract

Android 2.41.0 multiplayer native code supports targeted poison and paralysis cures for a living Morty with the corresponding ailment, including at full HP. A cure clears the matching status; it does not need a numeric healing effect. The client does not establish whether the original server returned `effect_value:0` or `1` for a cure: its Cure dialogue ignores this integer. Returning zero is compatible, not a recovered original-server convention.

## Evidence

Run `wsl bash tools/research/ghidra-capture-rules.sh`. Its second bounded native pass selects six multiplayer functions and writes `.research/ghidra-status-cure.json`, SHA-256 `f3c6cdab9cbd2ab41cc45afa7435ec26b5a6c96cc850a545d9295392f70bf9cd`. The ELF, dumper hashes, REA provenance and Ghidra limitations are recorded in [capture rules research](capture-rules-research.md). Binary SHA-256 is `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.

A separate Capstone 5.0.7 bounded disassembly of those six actual ARM64 bodies is `.research/status-cure-arm64.txt`, SHA-256 `57f35a66f4cccd30a6db0a7455c2ae7bef26884058be52a8b6d43ed442cf6016`. This is native evidence, not decompilation of dummy DLLs. All RVAs below exclude Ghidra's `0x100000` image base.

The preserved multiplayer ItemInfo catalog has TextAsset SHA-256 `c7ddb7536ad2a4fa1f48bf3e109e520a706b9056e5d9c484b808ba222f3e5fcc`; the current on-disk TextAsset is `ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39`. The price-only differences and current bundle provenance are documented in [the data audit](capture-data-audit.md). Both versions give `ItemPoisonCure` and `ItemParalysisCure` `effect_type:"Cure"`, `use_world:true`, `use_battle:true`, `use_self:true`, `use_account:false`. Their `effect_stat` is respectively `Poison` and `Paralysis`. Item metadata does not carry a numeric cure amount.

## Eligibility

`MPItemDefs.CanItemBeApplyedToMorty` (`0x176a44c`) follows this Cure path:

1. Require an existing Morty and reject `isFainted`, using `ITEM_APPLY_CURE_FAILED_FAINTED`.
2. For Poison, reject when `isPoisoned` is false, using `ITEM_APPLY_CURE_FAILED_POISON`.
3. For Paralysis, reject when `isParalysed` is false, using `ITEM_APPLY_CURE_FAILED_PARALYSIS`.
4. Otherwise permit the item. The full-HP check applies to Cure/All; it does not reject Poison or Paralysis cures on an afflicted living Morty at full HP.

ARM64 `0x176a53c` calls the model's `get_isFainted`; the living branch reaches `0x176a5e4`. That branch selects the effect-stat checks and reads the ailment bytes at model offsets `0x50`/`0x51`. These fields belong to `MPOpponentMortyData`; no singleplayer cure routine is needed to establish the eligibility rule.

This is client eligibility evidence, not a copy of original-server validation. A compatible server must enforce ownership, inventory availability, current route eligibility and living/afflicted target conditions itself. Rejecting a no-op cure without consuming inventory is an implementation requirement to avoid charging for an effect that the client disallows, not evidence of the original database transaction code.

For a successful poison cure, clear only poison; retain paralysis, HP, XP, stats and attacks. For a successful paralysis cure, clear only paralysis and retain the other state. This targeted behavior follows the item metadata and status-specific client messages; it requires no guessed probability or amount. `ItemFullRecover` is Cure/All and is outside this targeted-cure contract.

## Result and UI

The response remains the unwrapped `PlayerUseItemResponse` documented in [use-item contract](use-item-contract.md): `owned_morty_id`, `item_id`, `is_success`, integer `effect_value`, `owned_morties`, `owned_items`, and optional `attacks_to_learn`. For a successful targeted cure, use `is_success:true`, `effect_value:0`, and return the selected Morty's actual updated status snapshot plus the actual remaining owned-item quantity. Zero is a compatible server convention because the cure consumer does not use a magnitude; it is not an assertion about the original service's chosen value.

`NetworkPlayerAPI.<UseItem>b__52_0` (`0x17a6a20`) invokes `ParseHTTPResponse` for the typed response, stores error/response, dispatches `UseItemEvent`, then invokes the change event on error NONE (2) with a nonnull response.

`MPPartyState.NetUserUseItemsHandler` (`0x15c9aa0`) merges `owned_morties` and `owned_items` before branching on the error enum. On NONE it finds the selected Morty, passes `is_success` and `effect_value` to `MPPartyUI.UseItemCo`, and starts that coroutine. Therefore an error response must not contain success-shaped changed arrays that would accidentally mutate client state.

`MPPartyUI.<UseItemCo>d__54.MoveNext` (`0x15cd970`) only takes the HP tween branch for RestoreHP or Revive. A targeted Cure refreshes the Morty cell using the updated model and invokes `GetItemUsedResultText`.

`MPItemDefs.GetItemUsedResultText` (`0x176a6ec`) selects fixed Cure text from the item's effect stat: `ITEM_APPLY_POISONED`, `ITEM_APPLY_PARALYSED`, or `ITEM_APPLY_CURE_FULL`. It formats the player pronoun and Morty name and returns. Its Cure branch never reads the incoming numeric `itemEffectValue` and does not use `isSuccess` to decide whether to show the cure dialogue. Consequently neither a numeric `1` nor a positive HP delta is required for cure success, and a no-op should use the route's failure path rather than an apparently successful cure response.

## Explicit false status updates

`MPOpponentMortyData.SetFromDict` (`0x158cb1c`) recognizes `is_poisoned` and `is_paralysed`, calls `System.Convert.ToBoolean`, and writes the resulting boolean bytes at `0x50` and `0x51`. JSON `false` is applied; it is not ignored as an absent value. Omitted fields remain unchanged during partial updates.

Return both statuses explicitly when serializing an authoritative owned-Morty snapshot, for example `is_poisoned:false` and the unchanged `is_paralysed` value for a poison cure. The durable record and response must agree, and reloading the owned Morty must reproduce those status values. Persisting the item decrement and selected status change together is a server correctness requirement; the native client cannot prove original-server database ordering.
