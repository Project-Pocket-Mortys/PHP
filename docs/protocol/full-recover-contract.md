# Multiplayer Pure Curum (`ItemFullRecover`) contract

Android 2.41.0 supports Pure Curum on a living Morty with missing HP, poison, or paralysis. It restores full HP and clears both ailments together. It leaves attack AP unchanged. This gives a fixed full-recovery contract without percentage arithmetic or single-player formulas.

## Sources and reproduction

Run `wsl bash tools/research/ghidra-full-recover.sh` from the repository root. It runs pinned REA 6.8.0 artifact inspection through default WSL, then the hash-checking Ghidra 12.1.4 targeted driver with `-noanalysis` in a disposable project. Nine selected real native functions are decompiled; no whole-library automatic analysis is used. It independently disassembles their exact ELF PT_LOAD/native-RVA/body-size ranges with Capstone 5.0.7, and reads MP metadata plus English localization with UnityPy 1.25.0 through the explicit Windows Python 3.14 executable. Preserved assets and runtime/account state are not changed.

| Artifact | SHA-256 |
| --- | --- |
| Actual ARM64 `libil2cpp.so` | `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326` |
| `.research/dumper/dump.cs` | `8b659049aada5d5037f0c4d108d81e8ab9ff5e8127a11dd78f0a3954aeced27e` |
| `.research/dumper/script.json` | `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb` |
| `.research/ghidra-full-recover.json` | `ff99f700e54eb78b7197e0b44c5633d717524c82816f60980660f37668060360` |
| `.research/full-recover-arm64.txt` | `333c1ca275ca475703263e91f23019ba290a4aa1817e2f93983cd7fbb951840c` |
| `.research/full-recover-metadata.json` | `a7d9af22dd5a1d9ab91263d68173f93c23aba98cc72e583b740d9ee14b273eba` |

REA root evidence is `ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`, linked inventory `ev_be493fd671f9be32659c50fd1fb5d90ed4cdecff7d1a18c82a70e508eed9bfc5`. Artifact inventory identifies bytes, not method semantics. Ghidra's annotation/tail-call limitations are those of [the targeted driver](../../tools/research/ghidra-targeted.sh); addresses below are native RVAs without its `0x100000` image base. Managed signatures and field offsets are checked against the dumper, and actual branches against Capstone.

## Exact item and localization

Fresh MP `ItemInfo` has `item_id:"ItemFullRecover"`, `effect_type:"Cure"`, `effect_stat:"All"`, `use_world:true`, `use_battle:true`, `use_self:true`, `use_account:false`. The English `Item.ItemFullRecover` name is **Pure Curum** and description is **Heals all HP and cures all ailments.** The internal asset ID `ItemFullRevive` and attacker animation `FullReviveGun` do not confer revival eligibility. There is no MP numeric effect amount.

The current MP bundle hashes to `f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`; its `ItemInfo` TextAsset hashes to `ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39` (path ID `8663868515058661470`). The English bundle hashes to `bbe4b3036a907354dd7cad8122c0f557491e3259b6f4f349eda27caa913bc7a8`; `EN` hashes to `841eed65c78a058635eef4993f07b0a5592e8906f77c95027604cc3c57d4e1c4` (path ID `2069814988615685635`). Both report Unity `2022.3.62f1`. Historical/current MP price differences are documented in [the data audit](capture-data-audit.md).

## Eligibility and combined effect

`MPItemDefs.CanItemBeApplyedToMorty` (`0x176a44c`) tests Cure, calls `MPOpponentMortyData.get_isFainted` at `0x176a53c`, and rejects a fainted target with `ITEM_APPLY_CURE_FAILED_FAINTED` ("Can't cure a Morty that is dazed."). For a living Cure/All target it checks HP/max HP at `0x176a604..0x176a610`, poison at `0x176a614..0x176a618`, and paralysis at `0x176a61c..0x176a620`. All healthy/full-HP checks failing reaches `ITEM_APPLY_CURE_FAILED_ALL` ("Can't cure a Morty with no problems."). AP is not inspected on this path.

| Target | Eligible |
| --- | --- |
| Living, missing HP, either/both/no ailments | Yes |
| Living, full HP, poison and/or paralysis | Yes |
| Living, full HP, neither ailment, missing AP | No |
| Fainted, with or without ailments | No |

On success set HP to the authoritative maximum and both `is_poisoned` and `is_paralysed` to false in the same effect plan. Preserve AP, attacks, stats, XP, level and identity. The full-HP effect and combined cure follow the shipped description joined to MP Cure/All and its native eligibility. These are not recovered original-server mutation instructions. The two client ailment fields are the established scope; do not invent additional persistent ailments or effects from the word "all".

## World response and effect value

Use the existing [world response contract](use-item-contract.md): unwrapped `owned_morty_id`, `item_id`, `is_success:true`, integer `effect_value`, actual updated `owned_morties` and absolute remaining `owned_items`. A compatible convention is `effect_value:0`. The original service's number is unknown.

`MPItemDefs.GetItemUsedResultText` (`0x176a6ec`) selects `ITEM_APPLY_CURE_FULL` ("{0} {1} is fully restored.") for Cure/All and formats pronoun/name. This branch ignores `itemEffectValue` and `isSuccess`; it does not require the restored HP delta. A no-op must therefore use a failure path without consuming inventory, rather than a success-shaped cure response. `MPPartyState.NetUserUseItemsHandler` (`0x15c9aa0`) merges returned Morty/item records before UI handling. `MPPartyUI.<UseItemCo>d__54.MoveNext` (`0x15cd970`) refreshes the updated cell; its explicit HP tween branch selects RestoreHP/Revive, not Cure. `MPOpponentMortyData.SetFromDict` (`0x158cb1c`) applies explicit false status values. Return both cleared statuses with the healed HP snapshot.

## Battle snapshots

Use the established [battle ITEM contract](battle-item-contract.md). Request `move_id:"ItemFullRecover"` and `owned_morty_id` identify the selected owned target, including an eligible bench member. Keep the active identity when targeting the bench. The action uses `item_id`, `owned_morty_id`, `success:true`, `effect_value:0`, and authoritative `attacker_morty_datas`/`defender_morty_datas`; battle uses `success`, while world uses `is_success`.

`MPBattleActItemData.SetFromDict` (`0x1584ff8`) reads the integer value. `MPBattleUI.<StartTurnAct>d__87.MoveNext` (`0x15969a8`) merges action Morty dictionaries before animation. `MPBattleUI.<TurnActItem>d__95.MoveNext` (`0x159986c`) resolves the explicit target and passes the value unchanged to the same result-text helper. Its active Cure path tweens HP from the already-updated model, not `effect_value`; status also comes from the snapshot. Its bench path uses target-specific dialogue without switching active Morty.

The ITEM snapshot must show full HP and both cleared statuses immediately after the item, before any later AI action. A later action carries its later HP/status state. Remaining inventory belongs in `player_datas.player.owned_items`, with explicit quantity zero for the last consumed unit. Apply durable state, inventory and ordered snapshots atomically. Existing turn cost, retaliation and forced-switch policy remain replacement-server choices documented in the battle contract; this research does not recover original-server ordering, damage, HTTP errors or transactions. No percentage formula, SP arithmetic or Android end-to-end acceptance is claimed.
