# Multiplayer battle switch contract (Android 2.41.0 ARM64)

This contract recovers the client wire format and state transitions for voluntary and forced switching. It does not recover the original server's turn ordering, AI policy, damage, or replacement turn cost. The distinction between request IDs and result IDs below is essential.

## Evidence and reproduction

Inspected 2026-11-04 using default WSL and pinned REA 6.8.0 via `tools/research/rea.sh inspect-artifact`. Artifact identity evidence is `ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`, linked inventory `ev_be493fd671f9be32659c50fd1fb5d90ed4cdecff7d1a18c82a70e508eed9bfc5`. Inventory establishes root bytes, not function semantics.

| Artifact | SHA-256 |
| --- | --- |
| `libil2cpp.so` | `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326` |
| `.research/dumper/dump.cs` | `8b659049aada5d5037f0c4d108d81e8ab9ff5e8127a11dd78f0a3954aeced27e` |
| `.research/dumper/script.json` | `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb` |
| `.research/ghidra-battle-switch.json` (28 functions) | `8930c6a61f701b1cf4ce605dca6c0b262c820ac6148f3bb18b000e720d1275e5` |
| `.research/ghidra-battle-switch-party.json` (9 functions) | `3728d845cda30c21260b04552bcf55ae534a2fa9b40d15d85ee3ace3fcc98e1d` |
| `.research/battle-switch-arm64.txt` | `ecf364c0b093f5ead22503d250296ba12e62ccc66e4c0023f8fdd192f192fa8a` |
| `.research/battle-switch-party-arm64.txt` | `54012c92eef57bc3c259c2a272508eb1718154a935ac5b985e8c8d5452529138` |

Reproduce the Ghidra passes with `wsl bash tools/research/ghidra-battle-switch.sh`. The wrapper hash-checks the actual library, imports disposable projects with `-noanalysis`, and restricts decompilation to named functions. RVAs exclude Ghidra's `0x100000` image base. Managed signatures/field offsets are from `dump.cs`, also represented by DiffableCs metadata. Exception tails can flow into neighboring methods; only normal paths establish behavior here.

A separate Capstone check disassembled each selected function's exact `native_rva`/`body_bytes` range after translating ELF PT_LOAD virtual addresses to file offsets. This independently verifies instruction arguments and stores described below; the ignored raw outputs are listed above. The Capstone library in `.research/python` is the Windows build, so that check used `py`, not WSL Python.

## SWITCH request: outgoing ID and incoming ID

The exact party-switch body sent to `/session/battle/move` is:

```json
{"session_id":"SESSION","battle_id":"BATTLE","type":"SWITCH","owned_morty_id":"OUTGOING_OWNED_ID","move_id":"INCOMING_OWNED_ID"}
```

`move_id` is the incoming owned Morty ID for this move type. It is not null. The result action uses a different convention: its `owned_morty_id` names the incoming Morty.

Evidence chain:

1. `MPPartyUI.MainMenuBattleSwitchBtnPressedHandler` (`0x15cd27c`, button index 0) and `MainMenuBattleForceSwitchBtnPressedHandler` (`0x15cd2e4`, index 0) call `RequestSwitchOrder(currentBattleCell.data, selectedCell.data)`. The cells are fields `+0x98` and `+0xa0`, and their Morty data is `+0xf8`.
2. `RequestSwitchOrder` (`0x15ccf34`) invokes the typed `SwitchEvent` with both objects in that order. `MPPartyState.UISwitchHandler` (`0x15cb144`), in state origin BATTLE (2), calls `NetworkBattleAPI.SelectMove(SWITCH=3, first.netId, second.netId)` and returns to battle. The WORLD branch instead edits deck order; a battle switch does not establish a persistent deck reorder.
3. Capstone confirms normal button loads at `0x15cd2a4`/`0x15cd2a8`, forced button loads at `0x15cd304`/`0x15cd308`, and `UISwitchHandler` at `0x15cb238`/`0x15cb23c` loads the two `netId` fields (`+0x18`) into x2/x3, sets w1 to 3 at `0x15cb240`, then calls `SelectMove` at `0x15cb248`.
4. `NetworkBattleAPI.SelectMove` (`0x17882bc`) builds the five-field request with enum `ToString()`. The anonymous constructor's field mapping is also recorded in `native-transport.json` and the [completion contract](battle-completion-contract.md).

The current battle active ID must match the outgoing ID. The incoming ID must identify a different, living, session-owned member of the battle party. Those server validations are compatibility/security requirements, not proof of original server error codes.

## SWITCH result and authoritative snapshots

A switch action has these parsed keys:

```json
{"type":"SWITCH","attacker_player_id":"SWITCHING_PLAYER","defender_player_id":"OTHER_PLAYER","owned_morty_id":"INCOMING_OWNED_ID","attacker_morty_datas":[],"defender_morty_datas":[]}
```

The arrays above illustrate field placement only. Supply authoritative Morty dictionaries, including the incoming member if the client does not already have its full data. Do not erase the party by replacing it with only the incoming member.

`MPBattleActSwitchData.SetFromDict` (`0x1585328`) calls base `MPBattleActData.SetFromDict` (`0x15840e8`) and parses `owned_morty_id` into `mortyNetId` (`+0x38`). The base reads `type`, both player IDs, and both Morty dictionary arrays. The attacker is the switching player, not necessarily the player who attacked previously.

`MPBattleUI.<StartTurnAct>d__87.MoveNext` (`0x15969a8`) resolves attacker/defender by their player IDs, applies both arrays using `MPOpponentData.SetMortiesFromDicts(..., clearMorties=false, clearAttacks=false)`, and then dispatches act type SWITCH (3). `SetMortiesFromDicts` (`0x158c668`) matches each dictionary by required `owned_morty_id` and updates the existing object in place; it creates a member when absent. Its exception tail contains adjacent item-parser code, which is not extra switch behavior.

`MPBattleUI.<TurnActSwitch>d__97.MoveNext` (`0x159a5d8`) runs `SwitchBringMortyIn` for the outgoing member, resolves the action's incoming `mortyNetId` through `MPBattleOpponent.GetMortyData` (`0x1574700`), then runs `SwitchSendMortyOut` with that object. The historical method names describe recall/send animations. `SwitchBringMortyIn` (`0x1596e30`) skips the recall tween for a fainted outgoing member. `SwitchSendMortyOut` (`0x1597104`) assigns `MPBattleOpponent.currentMortyData` (`+0x48`) to the incoming object before showing it; Capstone confirms the store at `0x1597978`. Thus current identity comes from the SWITCH act, while HP/PP/status come from the applied dictionaries.

No `player_datas.player` active-Morty field was established. Its parser handles cooldowns, items, XP, rewards and ranking data, as documented in the completion contract. Adding an arbitrary active ID there is not a substitute for the action.

## FORCE_SWITCH and ASK_SWITCH

`MPBattleState.UITurnFinishedHandler` (`0x1576f1c`) branches on the network outcome after all action animations:

| Outcome | Client behavior |
| --- | --- |
| CONTINUE (1) | Calls ordinary `SelectingMoveRequest` |
| FORCE_SWITCH (8) | Calls `NetworkBattleAPI.SelectingMove`, then opens party with origin BATTLE and `forceSwitch=true` |
| ASK_SWITCH (7) | Offers optional switch if the player has alternatives; otherwise submits NONE/current owned ID/null |
| Terminal outcomes | Starts finish-battle flow |

Ordinary `UISwitchBtnHandler` (`0x1578088`) opens the same party with `forceSwitch=false`. `MPPartyInfo` has explicit `battleOutMortyData` and `forceSwitch` fields. Both normal and forced switch choices send the outgoing/incoming request shape above.

`NetworkBattleAPI.SelectingMove` (`0x1788078`) sends `/session/battle/ready` with session and battle IDs. Therefore a ready call can occur while replacement is pending, before SWITCH arrives; it must not clear the pending replacement or permit an attack from the fainted member. After a successful switch result with CONTINUE, the client returns to normal selection and sends its ordinary next-ready request.

The forced party menu's native handler exposes switch and stats; the normal party handler also has a Back event. No RUN choice is exposed in this forced flow. Whether the replacement server accepts a direct RUN while pending is an explicit server policy decision; these client methods do not prove the original server's validation.

`NetworkBattleAPI.Persist(MPBattleActSwitchData, previousTurnResult)` (`0x1789708`) updates analytics: it omits the player's switch counter when the previous result was FORCE_SWITCH (8), and omits the opponent's switch counter when previous result was ASK_SWITCH (7). This demonstrates that replacement is distinguished from voluntary switching. It does not calculate damage, execute AI moves, persist HP, or prove an original turn-cost formula.

## Implementation boundary

A compatible party-capable replacement can keep battle ownership/spawn claims active when the active member faints and another battle-party member lives, publish the fainted HP and FORCE_SWITCH, and persist a pending-replacement phase. Exhausting the living party produces LOSE. A pending replacement must survive `/battle/ready`, failed selections and transaction rollback. A valid SWITCH must atomically select the incoming owned ID and return the matching authoritative dictionaries. Rejecting a dead, foreign, out-of-party, current, or stale outgoing/target selection must not mutate battle HP, PP, active identity, or event queues.

The client proves FORCE_SWITCH is a continuing replacement flow, but does not itself choose the server outcome based on party HP. The rule above follows the meaning of the observed forced-party flow and is a replacement-server implementation requirement. A normal switch consuming the action with a subsequent AI attack, and a forced replacement receiving no additional AI attack, are reasonable explicit replacement policies; neither was recovered as original server behavior. Preserve and label the existing damage 20 / AI damage 1..3 placeholders. Do not claim original initiative, damage, or capture formulas.
