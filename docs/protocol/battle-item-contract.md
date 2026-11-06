# Multiplayer battle healing and cure items (Android 2.41.0 ARM64)

The native client supports items on the active Morty and on a selected bench Morty. For ITEM, request `owned_morty_id` identifies the **item target**, unlike SWITCH, where it identifies the outgoing active Morty. Native client evidence establishes selection, response consumption and eligibility; it does not recover original-server turn cost, retaliation, damage, inventory transaction policy or HTTP statuses.

## Evidence and reproduction

Run `wsl bash tools/research/ghidra-battle-items.sh`. This uses default WSL, pinned REA 6.8.0 through `rea.sh`, and the hash-checking targeted Ghidra driver. Ghidra 12.1.4 imports a disposable project with `-noanalysis` and decompiles 18 selected functions. It does not run automatic whole-library analysis. REA artifact evidence is `ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`, linked inventory `ev_be493fd671f9be32659c50fd1fb5d90ed4cdecff7d1a18c82a70e508eed9bfc5`; that inventory identifies root bytes, not function behavior.

| Artifact | SHA-256 |
| --- | --- |
| Actual ARM64 `libil2cpp.so` | `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326` |
| `.research/dumper/dump.cs` | `8b659049aada5d5037f0c4d108d81e8ab9ff5e8127a11dd78f0a3954aeced27e` |
| `.research/dumper/script.json` | `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb` |
| `.research/ghidra-battle-items.json` | `fd6c97f15b24da03bd6399c1a43d1e97826ce2bf4fffcda2fc7ca8d97d90b0a4` |
| `.research/battle-items-arm64.txt` | `d412aa39b20fc0b0795c32576547bcc7a3c19df834d7d0b794de209e30c73a83` |
| `.research/battle-item-metadata.json` | `1257e66fc0da4913b328ceef90a986cdd830c265e8ada1a761b19a469efe2ebe` |

The independent Capstone 5.0.7 check reads each selected function's exact `native_rva`/`body_bytes` range, translating ELF PT_LOAD addresses to file offsets. It disassembles the actual library, not dummy managed DLLs. It used the explicit Windows interpreter `C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe` with `.research/python` on the module path. RVAs here exclude Ghidra's `0x100000` image base. Managed signatures and field offsets are cross-checked against the dumper; exception tails that flow into neighboring functions do not establish extra gameplay behavior.

## Request selection and target identity

```json
{"session_id":"SESSION","battle_id":"BATTLE","type":"ITEM","owned_morty_id":"TARGET_OWNED_ID","move_id":"ItemSerum"}
```

`NetworkBattleAPI.SelectMove` (`0x17882bc`) constructs the five fields above, as established in the [completion contract](battle-completion-contract.md). The item ID occupies `move_id`; it is not an attack ID or a separate `item_id` request field.

The exact target chain is:

1. `MPPartyUI.MortyCellSelectedHandler` (`0x15ccb40`) stores the selected cell at UI `+0xa0` and emits `MortySelectedEvent` with its data (`cell+0xf8`). It does not replace the current battle cell (`+0x98`).
2. `MPPartyState.UIMortySelectedHandler` (`0x15cb0ec`) stores that selected data in `MPPartyInfo.selectedMortyData` (`+0x20`).
3. `MainMenuItemBtnPressedHandler` (`0x15cd244`, index 0) calls `RequestUseItem` (`0x15cd0b8`), which dispatches `UseItemEvent`.
4. `MPPartyState.UIItemHandler` (`0x15cb498`), with an item selected and origin BATTLE (2), calls `SelectMove(ITEM=2, selectedMortyData.netId, selectedItemID)`, then returns to battle. The owned ID comes from selected data `+0x18`; the item comes from party info `+0x28`.

When no item has been selected, this party handler opens the bag with the selected Morty carried in `MPBagInfo`. Conversely, `MPBagState.UIUseHandler` (`0x1570ff0`) routes battle `use_self` items to party selection, carrying the battle Morty and selected item into `MPPartyInfo`; non-self battle items can submit ITEM directly using the current battle Morty. The latter path is not the healing-item target convention: all twelve supported healing/cure items below are `use_self:true`.

## Result snapshots and animation

An ITEM action parses these fields in `MPBattleActItemData.SetFromDict` (`0x1584ff8`), after its base parser:

```json
{"type":"ITEM","attacker_player_id":"PLAYER","defender_player_id":"OPPONENT","item_id":"ItemSerum","owned_morty_id":"TARGET_OWNED_ID","success":true,"effect_value":20,"attacker_morty_datas":[],"defender_morty_datas":[]}
```

Arrays here illustrate placement only: send the authoritative dictionaries for the action's state. The item parser stores item ID at `+0x38`, target owned ID at `+0x40`, bool `success` at `+0x48`, integer `effect_value` at `+0x4c`. It uses `success`, not the world endpoint's `is_success` key.

`MPBattleUI.<StartTurnAct>d__87.MoveNext` (`0x15969a8`) resolves attacker/defender by their player IDs and merges both Morty arrays using `SetMortiesFromDicts(...,false,false)` **before** dispatching `TurnActItem`. Thus each action must describe that action's post-effect state. A subsequent AI action carries its later state; publishing final damaged HP in the item action would animate the wrong healing amount/state.

`MPBattleUI.<TurnActItem>d__95.MoveNext` (`0x159986c`) looks up the action's target through `attacker.GetMortyData(owned_morty_id)`. If lookup fails it falls back to the current Morty; the server should always supply a valid party-owned target instead of relying on this fallback. It explicitly branches when target and current Morty differ. The bench path plays item SFX and target-specific dialogue, and refreshes party status for revive. It does not switch the active Morty. The active path animates item effects; HP/revive/cure HP tweens read the already-updated current model's `hp`, not `effect_value`. AP and status mutations also come from dictionaries.

Both branches use `MPItemDefs.GetItemUsedResultText` (`0x176a6ec`) with the same `effect_value`; the battle consumer does not reinterpret it as a different amount. Capstone confirms the direct `ldr w2,[action,#0x4c]` at `0x15999a0` and call to `0x176a6ec` at `0x15999bc`. HP messages use actual restored HP, AP/revive messages use percentages, and targeted cure messages ignore the number. Compatible replacement conventions are actual HP delta for healing, 100 for full revive/full AP, and 0 for targeted cures. The original service's chosen cure number is unknown.

Return absolute remaining inventory in `player_datas.player.owned_items`, using `{"item_id":"ItemSerum","quantity":0}` when the last unit is consumed. `MPOpponentData.SetItemsFromDicts` (`0x158c958`) merges records and removes quantities below one; omission retains the previous quantity. The player-data application chain is covered by the [completion contract](battle-completion-contract.md), and zero-removal semantics by the [use-item contract](use-item-contract.md).

## Item metadata and eligibility

Fresh `export_item_effects.py` output verifies all twelve items have `use_battle:true` and `use_self:true` in MP `ItemInfo`. Current MP bundle SHA-256 is `f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`; ItemInfo TextAsset hash is `ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39`, path ID `8663868515058661470`. Amounts are from shipped descriptions and existing world helper scope, not an original multiplayer server formula.

| Item IDs | Effect | Supported replacement value |
| --- | --- | --- |
| ItemSerum / ItemGreatSerum / ItemSensationalSerum | RestoreHP | 20 / 50 / 200 HP, capped by missing HP |
| ItemPureSerum | RestoreHP | Full missing HP |
| ItemEasterEgg / ItemPumpkin | RestoreHP | 30 HP, capped by missing HP |
| ItemSpicyBBQPizza / ItemBreakfastMedley | RestoreHP | 200 HP, capped by missing HP |
| ItemPureHalzinger | Revive | Full HP; result percentage 100 |
| ItemPurePlutonicRock | RestorePP | All attack AP to catalog maxima; result percentage 100 |
| ItemPoisonCure / ItemParalysisCure | Cure/Poison or Cure/Paralysis | Clear matching status only; result value 0 |

`MPItemDefs.CanItemBeApplyedToMorty` (`0x176a44c`) requires a living target with missing HP for RestoreHP, a living target with remaining total PP below total maximum PP for RestorePP, a fainted target for Revive, and a living target with the matching ailment for targeted Cure. Cure does not require missing HP. Party selection invokes this helper for the selected item and selected Morty; it does not restrict a self-use item to the active member. Thus a fainted bench target is valid for full revive while the current active member remains alive. A living bench target can receive healing, AP restore or a matching cure.

The pending forced-switch menu handler (`0x15cd2e4`) exposes switch and stats; no item choice is offered. Rejecting ITEM with HTTP 409 while replacement is pending is compatible replacement policy, including attempts to revive a bench member while the current active member is fainted. It is not recovered original-server HTTP/error parity.

## Implementation boundary

Apply only the twelve existing world effect plans to an owned member of the initial battle party, while requiring a living current active member and coherent inventory/owned/battle snapshots. The target may differ from active identity. Persist the consumed quantity and selected HP/PP/status changes atomically with the ordered action snapshots and battle result. For bench use, retain the current active identity and its HP except for any later counterattack.

Consuming a voluntary item turn and then retaining the existing random AI 1..3 counterattack against the active member is an explicit replacement policy. Native evidence does not establish that original server turn ordering or damage. After that existing AI action, choose CONTINUE when the active member lives, FORCE_SWITCH when it faints and another party member lives, and LOSE when the party is exhausted, consistent with the [switch contract](battle-switch-contract.md). The server must consider a bench revive in the resulting living-party calculation.

Keep `ItemMortyChip` capture and other unsupported item families at the existing HTTP 501 ITEM_UNUSABLE failure, with no inventory/state/event mutation. Do not infer percentage-item rounding, Cure/All, stat increases, original retaliation or balance formulas from these twelve supported plans. This work is static native/data recovery; Android end-to-end acceptance remains separate.
