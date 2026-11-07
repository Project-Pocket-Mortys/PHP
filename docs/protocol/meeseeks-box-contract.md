# Mr. Meeseeks Box in wild battles

Android 2.41.0 multiplayer metadata identifies `ItemMrMeeseek` as a battle-only,
non-self `DamageHP` item. Its shipped English description is "Instantly defeats
another Morty." This establishes an instant-defeat effect without selecting a
damage formula. The native request and animation paths below support a narrow
PvWM implementation. They do not recover original-server consumption,
initiative, rewards, cooldowns or error statuses.

## Evidence and reproduction

```powershell
wsl -- bash tools/research/ghidra-meeseeks-box.sh
```

The wrapper requires pinned REA 6.8.0 in default WSL, records a fresh root
inspection, then uses the hash-guarded Ghidra 12.1.4 wrapper with `-noanalysis`
for nine selected methods. Independent Capstone disassembly reads those
functions from the actual ELF using PT_LOAD translation and dumper method
boundaries. It also joins the actual MP ItemInfo record to EN by exact item ID.
Outputs remain ignored under `.research/`.

The ARM64 library SHA-256 is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.
REA inspection evidence is
`ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`,
with inventory evidence
`ev_be493fd671f9be32659c50fd1fb5d90ed4cdecff7d1a18c82a70e508eed9bfc5`.
Those receipts establish root identity, not method semantics.

The reproduced output hashes are:

| Ignored artifact | SHA-256 |
| --- | --- |
| `ghidra-meeseeks-box.json` | `295b97797cf8c9e78b64343f8f4bceddf71485504d9153663b2ae4dd21173581` |
| `meeseeks-box-arm64.txt` | `c9e3422e766a98a728e2041aa675dfa35d777245119c106d75695a77d6c7d237` |
| `meeseeks-box-metadata.json` | `490ec9c646fc9bb13ba4942b61ce91bfedf1382c49f1075178c02049e763c86f` |

Current MP bundle and ItemInfo hashes are respectively
`f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413` and
`ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39`.
EN TextAsset hash is
`841eed65c78a058635eef4993f07b0a5592e8906f77c95027604cc3c57d4e1c4`.
The complete MP record sets `use_battle=true`, `use_world=false`,
`use_self=false`, `use_account=false`, `effect_type=DamageHP`,
`attacker_animation=MrMeeseek`, and no defender animation or numeric effect.
The exact ID also matches `MPItemDefs.kMrMeeseekID` in the managed dump.

## Native availability and actor identity

`MPBagUI.ScrollMenuCellSelectedHandler` (`0x1571ce8`) first checks the MP battle
use flag. For `DamageHP` and `FDAItem`, it disables use when
`(enemy.type | 2) == 7`, showing `RAID_BOSS_ITEM_NOT_ALLOWED_INFO`. The dumped
`eMPOpponentType` values make this a check for `RAID_BOSS=5` and
`MOVING_MORTY=7`; `WILD_MORTY=1` passes. Capture's separate wild-only and
owned-Morty-limit branch does not apply to this item. This establishes native
wild availability; it is not authorization to implement trainer, raid, moving
Morty or private-player battles.
Capstone independently confirms `ldr w8,[x8,#0x20]` at `0x15720b4`,
`orr w8,w8,#2` at `0x15720b8`, `cmp w8,#7` at `0x15720bc`, and the normal-use
branch at `0x15720c0` when that comparison differs.

`MPBagState.UIUseHandler` (`0x1570ff0`) follows the non-self, non-account,
BATTLE-origin branch directly to `SelectMove(ITEM=2, player.currentMorty.netId,
bag.selectedItemID)`. There is no party target-selection screen for this item.
The owned ID identifies the player's active actor, not the enemy Morty and not
an arbitrary owned bench member.

`NetworkBattleAPI.SelectMove` (`0x17882bc`) constructs:

```json
{"session_id":"SESSION","battle_id":"BATTLE","type":"ITEM","owned_morty_id":"PLAYER_ACTIVE_OWNED_ID","move_id":"ItemMrMeeseek"}
```

Its five fields contain no nonce, turn number or idempotency key. See the
[shared battle transport contract](battle-completion-contract.md).

## Action snapshots and completion

`MPBattleActItemData.SetFromDict` (`0x1584ff8`) parses `item_id`,
`owned_morty_id`, `success` and integer `effect_value`, after the base action
parser. `MPBattleUI.<StartTurnAct>d__87.MoveNext` (`0x15969a8`) resolves actor
and defender by player ID and merges both Morty snapshot arrays before item
animation. A compatible PvWM action is:

```json
{"type":"ITEM","attacker_player_id":"PLAYER","defender_player_id":"WILD_OPPONENT","item_id":"ItemMrMeeseek","owned_morty_id":"PLAYER_ACTIVE_OWNED_ID","success":true,"effect_value":23,"attacker_morty_datas":[],"defender_morty_datas":[{"owned_morty_id":"SPAWN_ID","hp":0}]}
```

Here 23 illustrates the enemy's prior HP. Reporting that HP as the actual
damage is an explicit replacement convention; no original numeric result is
recovered. The authoritative effect is the defender snapshot's zero HP.
The attacker array can be empty because this item changes no owned HP, AP,
ailment, stat or active identity.

`MPBattleUI.<TurnActItem>d__95.MoveNext` (`0x159986c`) resolves
`owned_morty_id` against the attacker. With its current active ID, the normal
active branch plays the item animation. The exact `ItemMrMeeseek` branch waits
two seconds and displays `ITEM_APPLY_MR_MEESEEK` ("I'm Mr. Meeseeks, look at
me!"). The `DamageHP` branch reads **defender.currentMorty.hp** and tweens the
defender HP bar to that value. It does not derive damage from `effect_value`.
Coroutine field offsets are attacker `+0x20`, action `+0x28`, defender `+0x38`;
the opponent's current Morty is `+0x48` and Morty HP is `+0x30`.

`MPItemDefs.GetItemUsedResultText` (`0x176a6ec`) has no `DamageHP` result branch
and returns null for this effect. The item coroutine returns when that result
is null, after the animation/status updates. The localized general damage
message existing in EN therefore does not establish a Meeseeks numeric result
contract. No extra capture result or captured-Morty dictionary is required.

Use the established `WIN` completion envelope after the item action.
`MPBattleState.UITurnFinishedHandler` (`0x1576f1c`) dispatches normal terminal
outcomes to `FinishBattle`; it contains no Meeseeks-specific completion path.
Preserve the existing empty `xp_datas`, `rewards` and `attacks_to_learn`
conventions. Do not generate rewards, XP or a captured owned Morty.

Inventory is an absolute update in
`player_datas.player.owned_items`, including
`{"item_id":"ItemMrMeeseek","quantity":0}` for depletion.
`MPOpponentData.SetItemsFromDicts` (`0x158c958`) removes quantities below one;
omitting the item would retain stale client stock.

## Replacement transaction and focused validation

A successful use should lock the same user, active battle, original party,
claimed wild spawn and single inventory row as existing item uses; require the
request actor to equal the living active owned Morty; consume one box; set
battle enemy HP to zero; complete with the player as winner; remove/release the
wild encounter using existing WIN behavior; and publish one private terminal
turn in the same transaction. With a defeated defender, skip counterattack.
Consumption, no retaliation and HTTP choices are explicit replacement policy,
not recovered original-service parity.

Terminal battle state rejects a late duplicate without a second consumption.
Concurrent requests serialize on the user/battle locks and only one can win.
This property follows terminal-state validation, not request-body deduplication.
Missing/invalid/duplicate stock, a foreign or bench actor, invalid/cache-mismatched
HP, pending forced replacement, a due timeout, ambiguous party identity and
already terminal battles must preserve existing validation and rollback.

Focused tests should cover native actor-shaped success with arbitrary positive
enemy HP (including 1 and odd HP), unchanged owned HP/AP/flags/party identity,
zero inventory projection, one defender HP-zero action with no AI action,
durable terminal/wild cleanup, retry/concurrent last-stock behavior and a late
event-insert failure rolling back stock, battle, wild and user state. Keep other
unsupported item families rejected and keep world use unsupported. A separate
native Android UI use was subsequently verified by the
[guarded acceptance follow-up](android-meeseeks-box.md); that capture remains
separate from the static evidence above.
