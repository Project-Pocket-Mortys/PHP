# Shared initial RUN terminal boundary

This bounded Android 2.41.0 ARM64 review extends the
[first-selection contract](paired-selection-contract.md) and
[shared startup contract](shared-battle-startup-contract.md). It establishes a
native voluntary RUN request, terminal presentation and a restricted duplicate
delivery boundary. It does not recover the original server's surrender rules,
combat formulas, disconnect adjudication, rewards or later-turn identity.

## Native request and presentation

`MPBattleUI.MainMenuBtnPressedHandler` (`0x157bb6c`, 640 bounded bytes) checks
the selected move button's cooldown lock first. For Run (menu index 3), opponent
types RAID_BOSS=5, FYRE_SALE_SUMMER=6 and CUSTOM_BATTLE=8 display a refusal.
USER=2, the human PvF opponent type, reaches the trainer Run confirmation.
`RefreshMainMenu` (`0x157abf0`) derives that lock from `move_log.cooldown.RUN`.
The initial research snapshots use zero cooldowns; the review does not establish
later server cooldown policy.

`MPBattleState.UIRunBtnHandler` (`0x15781d4`) opens the existing confirmation.
`GenericPopupRunConfirmationHandlerBody` (`0x15787e0`, 336 bytes), on the
confirm branch, calls `NetworkBattleAPI.SelectMove` with move type RUN=4, the
player's current active Morty's owned net ID, and a null move ID. The existing
five-field request constructor therefore sends:

```json
{"session_id":"current-session","battle_id":"shared-battle","type":"RUN","owned_morty_id":"active-owned-morty","move_id":null}
```

The confirmation does not submit a turn number, nonce or phase ID. Its normal
request acknowledgement follows the same HTTP-error parser as ATTACK. A success
body cannot communicate the terminal result; use the asynchronous
`battle:turn-result` consumer contract.

`eMPBattleTurnResult` (`dump.cs:62272`) includes WIN=2, LOSE=3, DRAW=4,
RUN=6 and ABANDONED=9. There is no OPPONENT_RUN member.
`BattleTurnResultHandler` (`0x1788dc4`, 1824 bytes) maps WIN with
`battle_abandoned:true` to ABANDONED. For outcomes 2 through 6 or 9 it calls
`EndBattle` before rewards and the UI result event.

`FinishBattleTrainer.MoveNext` (`0x1595044`, 808 bytes) presents RUN using
`BATTLE_RUN_FROM_TRAINER`. Ordinary WIN uses
`MP_BATTLE_FINISHED_TRAINER_WON`. ABANDONED removes enemy presentation and uses
`MP_BATTLE_FINISHED_TRAINER_ABANDONED` with four seconds of dialogue.
ABANDONED additionally invokes the API's separate `AbandonedEvent`, when it has
a subscriber, after the normal UI result event. Original-server routing of
voluntary surrender to these alternatives is not recovered.

`StartTurn.MoveNext` (`0x159673c`, 504 bytes) accepts an empty action list,
passes the player's optional item data to `SetItemsFromDicts` with `clear=false`,
processes the two optional XP arrays, then signals turn finished. An initial RUN
needs no fabricated RUN act, damage, faint, XP or reward.

## Minimal terminal payload and omitted fields

The supported minimal runner payload is:

```json
{"outcome":6,"battle_abandoned":false,"turn_datas":[],"player_datas":{"player":{},"opponent":{}}}
```

The peer payload has the same shape with outcome 2 and `battle_abandoned:true`.
The `player` and `opponent` entries must be JSON objects, including when empty;
they are not JSON arrays. Keep `turn_datas` an explicit empty array. These
objects produce real `MPBattleTurnOpponentData` instances and allow the normal
terminal consumer path.

Omitting the optional arrays is safe and differs from inventing empty values
for every possible field:

- The dictionary constructor (`0x15856ec`) creates `MoveCooldowns` then calls
  `SetFromDict` (`0x1585818`). `SetFromDict` iterates only keys actually present.
  With `{}`, its items, XP, rewards, attacks-to-learn, player-level and incentive
  fields retain their null defaults.
- `MPOpponentData.SetItemsFromDicts` (`0x158c958`) clears inventory only if its
  `clear` argument is true. With false and a null dictionary array it skips the
  update loop and returns, preserving the existing client items. Supplying a
  fabricated snapshot or even explicit item arrays is unnecessary here.
- `AwardXPDatas.MoveNext` (`0x15943dc`) explicitly returns without XP processing
  for a null XP array. Empty XP arrays are also accepted, as previously reviewed.
- `IsAttacksToLearnStateRequired` (`0x15861b4`),
  `IsPlayerLevelStateRequired` (`0x1586214`), `IsRewardStateRequired`
  (`0x1586248`) and `IsVideoRewardStateRequired` (`0x15862d4`) return false for
  the corresponding null fields. The UI therefore takes its ordinary finish
  transition without optional reward screens.

Do not add `player_xp_datas:[]`: that field expects a dictionary, not an array.
Do not add an empty incentive or attacks-to-learn container merely to fill
optional fields. No `move_log` values, item quantities, XP, score or rank need
to be supplied for this minimal terminal. This establishes the bounded native
consumer contract; paired Android acceptance remains separate.

## Duplicate delivery on one original stream

The result handler itself has **no battle-ID or active-battle guard** before
deserialization and player-data writes. Clearing its current ID does not make a
direct second invocation harmless. The native protection is removal of its
event subscription, with these observed steps:

1. `EndBattle` (`0x1787b5c`) clears timer flags and the API's ID/type fields,
   then calls `SetActiveInBattleHandlers(false)` before the result handler
   applies rewards or emits `TurnResultEvent`.
2. `SetActiveInBattleHandlers` (`0x17878e8`) unregisters the API delegate from
   `battle:turn-result` through `NetworkSessionAPI.Off` (`0x17b6998`),
   `NetworkEventSource.Off` (`0x17b5628`) and
   `RemoveInternalHandler` (`0x17b9618`). The latter removes the matching
   delegate and deletes the event-name key when its list becomes empty.
3. `NetworkEventSource.OnMessageHandler` (`0x17b9e1c`) calls
   `CallHandlers` (`0x17b9c44`) for each message. `CallHandlers` looks up the
   current event dictionary first and returns if the key is absent. It snapshots
   the handler list only for the current message, then invokes synchronously.
4. Best.ServerSentEvents `OnDownloadStarted` (`0x1a489fc`) starts its
   `DataProcessor` as a Unity coroutine. Its `MoveNext` (`0x1a49bb4`) feeds data
   and calls `HandleEvents` (`0x1a499dc`) synchronously. `HandleEvents` dequeues
   and synchronously invokes `OnMessageReceived` (`0x1a494ec`) for each message
   before dequeuing the next. That method invokes the message callback directly.

Thus a later identical terminal on that same established stream cannot reach
the removed battle delegate after the first terminal has completed its handler,
including while its UI animation finishes or after world return. Multiple
messages in one data batch still pass through the per-message lookup.

This is **not a general replay protocol**. A future battle can register the same
delegate again; an old result would then have no native ID fence. The chosen
replacement transport therefore never replays terminal events, including on the
original stream. Its existing one-shared-startup-per-stream restriction remains;
this review does not require forbidding later legacy wild battles on that stream.
Do not infer a native terminal acknowledgement from handler removal or the HTTP
move acknowledgement.

## Bounded replacement policy

A research-only first RUN uses separately documented replacement policy:
require both initial ready signals, READY state, both original start delivery
attempts, exact live stream bindings and the live fixed startup lease.
Authenticate the actor, validate both frozen parties and exact claims, and
require the runner to have made no previous own selection. A peer's zero or one
already-stored initial ATTACK remains inert history and spends no PP. Atomically
store one immutable terminal decision and two recipient-specific payloads,
return both users to WORLD, release only the original claims, and retire
startup/selection records without changing saves. Races with another RUN,
ATTACK, expiry or cancellation must serialize.

The chosen recipient policy is runner RUN=6 with `battle_abandoned:false`,
and peer WIN=2 with `battle_abandoned:true`, producing native ABANDONED
presentation. This adjudication/presentation choice is replacement policy,
not recovered original-server behavior. It establishes no rewards, ranking or
statistics.

Persist both terminal intents before publication. On each original bound stream,
commit a recipient-specific attempt marker before writing its terminal SSE
event. Subsequent polls emit no terminal and refresh only that stream's own
heartbeat. Keep the stream alive without immediate `session:end` so disconnect
does not interrupt finish presentation. This is at-most-once publication
attempt semantics, matching the startup transport; it is not exactly-once
delivery. A crash after the marker commits but before the SSE write can lose
the presentation. The broken socket then uses existing native disconnect and
fresh-login recovery into persisted WORLD state. No terminal is replayed onto
the old stream or a replacement stream, and no battle resume is claimed.
Publication is neither delivery proof nor a native acknowledgement. Paired
Android acceptance remains required for both presentations and recovery.

Public invitation acceptance remains disabled. No new selection phase, later
ready interpretation, move nonce, combat action or administrative-disconnect
outcome follows from this narrow voluntary RUN boundary.

## Reproduction

Run `wsl bash tools/research/ghidra-shared-run.sh` from the repository. It uses
default WSL REA 6.8.0 artifact inspection, targeted Ghidra 12.1.4 without whole
program analysis, and the explicit Windows Python executable
`C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe` for bounded
ARM64 exports. REA establishes artifact identity only. No database, device,
account or runtime gameplay operation is performed.

The pinned ELF SHA-256 is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`;
metadata version is 31, metadata SHA-256 is
`b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`,
and script mapping SHA-256 is
`a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`.

Ignored outputs are `.research/rea-shared-run-6.8.0-artifact.json`,
`.research/ghidra-shared-run-contract.json`,
`.research/shared-run-contract-methods.json` and
`.research/shared-run-contract-arm64.txt`. The method manifest records each
signature, next method/address boundary, byte length and body hash. Ghidra may
follow exception fallthrough beyond those bounds; conclusions use the bounded
ARM64 normal paths. Existing completion and paired-selection receipts remain
separate evidence and do not constitute a new paired RUN acceptance run.

The wrapper reproduced 33 bounded methods, including the omitted-field checks.
The complete run's SHA-256 values were
`de467dca6955e62bbeab3d9c2d30021c2a08ced5fa79dd143783e4b359684360`
for Ghidra JSON, `7cdff19ed2da7cc48435a205a49da1c6b6f5d991ab0bed90f2c6cce1809648bc`
for the manifest, and
`5ded061b6c51789b4608a1024c9f0045558c3aecd3dee9db94dc0d60bee93469`
for ARM64 text. Ghidra presentation hashes may vary on reproduction. Bash syntax
and whitespace checks passed. This research pass changed only this contract and
its reproduction wrapper; backend implementation and device acceptance remain
separate work.
