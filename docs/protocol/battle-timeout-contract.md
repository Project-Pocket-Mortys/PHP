# Battle timeout and cancellation contract (Android 2.41.0 ARM64)

The native client has a move countdown and a separate session watchdog. Expiring the move countdown does not end the battle or submit a fallback move. A replacement server can end an abandoned PvWM battle using the existing terminal result contract. The original server's expiration interval, grace period, penalty and scheduling policy were not recovered.

## Evidence and reproduction

Inspected 2026-11-05 with default WSL, REA 6.8.0 and bounded Ghidra 12.1.4 native decompilation. Run `wsl bash tools/research/ghidra-battle-timeouts.sh`. The script inventories the actual library with REA, then uses the existing hash-checking `-noanalysis` driver for two disposable imports (22 and 13 functions). The REA artifact evidence is `ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`, linked inventory `ev_be493fd671f9be32659c50fd1fb5d90ed4cdecff7d1a18c82a70e508eed9bfc5`; this identifies root bytes, not function semantics. The explicit Ghidra doctor report is `.research/rea-battle-timeouts-6.8.0-doctor.json`; it reports `healthy:true` for that scope and `environment_healthy:false` for unrelated missing engines/skill identity.

| Artifact | SHA-256 |
| --- | --- |
| ARM64 `libil2cpp.so` | `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326` |
| `.research/dumper/dump.cs` | `8b659049aada5d5037f0c4d108d81e8ab9ff5e8127a11dd78f0a3954aeced27e` |
| `.research/dumper/script.json` | `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb` |
| `.research/ghidra-battle-timeouts.json` | `704f1ca6fadf456869c5fb275334ab05409b9faefb81c299244bbfe9fdc2bf2e` |
| `.research/ghidra-battle-timeouts-ui.json` | `b683819fcc7a1291c7b94a9b93e8cecdc691a25d4e23e9e41f4679713573904c` |
| `.research/battle-timeouts-arm64.txt` | `a00e4b34bfef0d0f6208ddfeb7c33e8a628a31324eec748ba3057dda16e3b496` |

RVAs exclude Ghidra's `0x100000` image base. Managed signatures and fields are cross-checked against the dump; managed dummy assemblies are not executable evidence. A separate Capstone 5.0.7 pass disassembled each output's exact `native_rva`/`body_bytes` range from the actual ELF, translating PT_LOAD virtual addresses to file offsets. It used the explicit interpreter `C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe -X utf8` with `.research/python` on the module path; no Windows Python alias was invoked. As in the [completion contract](battle-completion-contract.md), exception tails that flow into neighboring methods do not establish additional normal behavior.

## Two distinct timers

`BattleMoveTimeResponse` (`dump.cs:27068`) carries `timeout:int`. `NetworkBattleAPI.BattleMoveTimeHandler` (`0x1788d00`) deserializes it, converts it to float, constructs `MPBattleTimerData`, stores it in `timerData` (`+0x70`) and invokes `MoveTimerStartedEvent`. Its constructor (`0x1586360`) writes the supplied value to both `time` (`+0x10`) and `timeTotal` (`+0x14`). There is no recovered absolute server timestamp in this message.

`MPBattleTimerData.ManualUpdate` (`0x1586388`) decrements a positive time by Unity `deltaTime`, clamps it to zero, and returns false on the positive-to-zero transition. If initialized at zero or negative, it returns true without decrementing; sending zero is not an established immediate-expiration mechanism. Capstone confirms the `fsub` at `0x15863a8`, clamp at `0x15863b0`, and transition branch at `0x15863bc`.

`NetworkBattleAPI.UpdateBattleTurnTimer` (`0x17872a0`) and the inlined counterpart in `Update` (`0x17871d0`) clear `timerData` and set `isTimerExpired` (`+0x80`) when the timer returns false. Capstone confirms the stores at `0x17872c0` and `0x17872c4`. They do not call `SelectMove`, `EndBattle`, a turn-result event, or a world transition. `MPBattleTimer.Update` (`0x1578f0c`) stops its visual update when expired/skipped; otherwise it updates the fill, rotates the hand and vibrates in the last third.

`NetworkBattleAPI.SelectMove` (`0x17882bc`) refuses the normal PvWM request after `isTimerExpired` or `isTimerSkipped` is set. Its separate special PvA branch must not be generalized to wild battles. A successful selection clears the timer and sets `isTimerSkipped` (`+0x81`); this flag means selection already occurred, not that the server ran a skip turn. Thus a server that only expires an idle battle when the next move arrives can strand this client.

The separate `timeOutCount` (`+0xa8`) is a watchdog. `StartTimeOut` (`0x1788660`) stores float `180.0` (`0x43340000`); `StopTimeOut` (`0x178866c`) stores zero. `UpdateTimeOut` (`0x1787204`) decrements a positive value, then calls `NetworkSessionAPI.Disconnect` with reason `11`, the dump's `eNetSessionDisconnectType.BATTLE_TIMED_OUT`. Capstone confirms `mov w1,#0xb` at `0x178728c` and the tail call to `0x17b37ac` at `0x1787298`. `Disconnected` (`0x1786f34`) calls `Leave` (`0x1786fbc`), which unregisters battle events and clears local identity/timer fields. This is a session disconnect fallback, not evidence for an ordinary battle-only cancellation deadline. The string `out_of_time` in `EndBattle` belongs to moving-Morty analytics; it does not establish a wire outcome named `out_of_time`.

## Supported terminal outcomes

`BattleTurnResultHandler` (`0x1788dc4`) parses the ordinary `battle:turn-result` payload, clears both timer flags and watchdog, builds the action list and both player data objects, then calls `EndBattle` for outcomes `2..6` or `9`. It also maps WIN with `battle_abandoned:true` to ABANDONED. Capstone verifies the terminal comparison at `0x17893c4`/`0x17893c8`, call at `0x17893d4` and the separate outcome-9 branch. `EndBattle` (`0x1787b5c`) clears the battle ID/type and unregisters in-battle handlers.

| Outcome | Native behavior relevant to cancellation |
| --- | --- |
| DRAW (4) | Clears network battle; wild finish shows draw dialogue. World result flag treats 3/4 as loss-like, so it is not a neutral cancellation choice. |
| RUN (6) | Clears network battle; wild finish shows run dialogue; does not set that loss-like flag. |
| ABANDONED (9) | Clears network battle; also invokes `AbandonedEvent` after `TurnResultEvent`. Wild finish takes the immediate default branch, without win/lose/run dialogue. |
| FORCE_END (10) | Exists in the enum and UI handles it, but this network handler does not call `EndBattle` for 10. It is not established as a self-contained wire cancellation. |

Other terminal outcomes WIN/LOSE/CAUGHT have their existing gameplay meanings. There is no dedicated TIMEOUT or CANCEL member in `eMPBattleTurnResult` (`dump.cs:62272`). Do not invent one.

`MPBattleState.NetBattleTurnResultHandler` (`0x1578c1c`) plays results immediately when active and idle; otherwise it sets `_waitingToPlayTurnActDatas`. The extra abandonment event is significant when an idle user is in a side menu: `MPPartyState.NetBattleComeBackHandler` (`0x15c9a80`) returns the active party state to battle; `MPBagState` (`0x1570564`) returns from the bag; stats (`0x15bebf0`) and Mortydex entry (`0x15b95f4`) remove backstack entries then return. These handlers are guarded by `IsActiveAndNotTransitioning`. This is stronger evidence for ABANDONED than silently using RUN when cancellation must recover from a party/bag selection screen. A transition already in progress still requires runtime validation.

## Finishing without HP, AP or rewards changes

`MPBattleUI.<StartTurn>d__86.MoveNext` (`0x159673c`) accepts an empty action list: it skips action iteration, applies the supplied owned-item state, runs the optional XP coroutines and requests turn completion. With no actions, it never enters `StartTurnAct`, where the authoritative Morty dictionaries normally update HP/AP/status. Preserve the current item/cooldown state; an empty action list is not permission to erase inventory.

`MPBattleState.UITurnFinishedHandler` (`0x1576f1c`) routes CONTINUE/FORCE_SWITCH/ASK_SWITCH separately and routes other results to `FinishBattle`. `MPBattleUI.<FinishBattle>d__80.MoveNext` (`0x1594760`) runs the opponent-type finish coroutine and then invokes `BattleFinishedEvent`. The wild finish (`0x15953e0`) returns immediately for ABANDONED. `UIBattleFinishedHandler` (`0x15772d0`) sets its world loss-like flag only for outcomes 3/4, and, when attacks-to-learn, rewards, player-level and incentive screens are unnecessary, clears battle info and performs the ordinary state transition. Empty XP/rewards behavior is independently established in the [completion contract](battle-completion-contract.md).

The required `player_datas.player` and `.opponent` objects can each be `{}`. `MPBattleTurnOpponentData`'s dictionary constructor (`0x15856ec`) first creates default `MoveCooldowns`; `SetFromDict` (`0x1585818`, reproduced in the completion pass) enumerates optional dictionary keys. Omitting `move_log` avoids fabricating a RUN count or cooldown. Omitting `owned_items` leaves its array null; `MPOpponentData.SetItemsFromDicts` (`0x158c958`), called with `clear=false`, returns without modifying items for a null or empty array. Capstone confirms the clear guard at `0x158c9e4` and null-array return branch at `0x158ca00`. Omitted XP, rewards, attacks-to-learn and incentive fields leave the corresponding optional screens unnecessary. Explicit empty XP/reward arrays are also supported.

A minimal compatible terminal cancellation is:

```json
{"outcome":9,"battle_abandoned":false,"turn_datas":[],"player_datas":{"player":{},"opponent":{}}}
```

The implementation preserves the existing outcome-name wire convention and
sends `"outcome":"ABANDONED"` (enum value 9). The Android acceptance separately
verifies this spelling through the native SSE parser and ordinary world return.

`battle_abandoned` only remaps outcome 2 to 9; with explicit outcome 9 either boolean value is accepted by this handler. False avoids implying a remapped WIN. This is a client compatibility conclusion. It does not prove which result the original server chose when a timer expired, and it does not justify changing authoritative HP, attack AP, statuses, party order, items, XP, currency, capture ownership or rewards.

## Replacement-server policy boundary

The replacement server must choose and document its own deadline, durable marker, dispatch mechanism and cleanup schedule. The 180-second client watchdog is not proof of the original server's move expiration policy. Persist a battle-only terminal cancellation once, retain already committed gameplay state, and publish its compatible result independently of another move request. Late moves and repeated sweeps must not mutate the completed battle or emit a second terminal result. Scope that transition to the battle's session so ordinary world/SSE presence can continue. None of those transaction, race, replay or scheduling requirements are claims about the original server implementation.

For a safety cancellation, ABANDONED (9) has the strongest recovered path: it clears network battle identity, avoids the draw/lose world flag, carries no fabricated action/reward, and returns active party/bag screens toward the pending battle result. Android runtime validation should still exercise both the battle screen and a side menu. This static research does not establish post-timeout reconnect replay, original penalties, or missing combat formulas.
