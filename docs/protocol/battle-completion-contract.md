# Battle completion contract (Android 2.41.0 ARM64)

This contract records the client requirements for completing existing multiplayer wild battles. It does not recover damage, growth, XP, capture chance, or reward formulas. Durable server transactions below are implementation requirements inferred from the client consuming authoritative state, not evidence of the original server implementation.

## Evidence and reproduction

Inspected on 2026-11-04 using default WSL and `tools/research/rea.sh` (REA 6.8.0). Fresh `.research/rea-battle-completion-6.8.0-artifact.json` reports evidence `ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`, linked root inventory `ev_be493fd671f9be32659c50fd1fb5d90ed4cdecff7d1a18c82a70e508eed9bfc5`. This is artifact identity evidence, not function semantics. The graph inventory covers root bytes only.

`rea doctor --provider ghidra --format json` reports `healthy:true` for the explicit Ghidra scope (12.1.4, Java 21); `environment_healthy:false` includes unrelated missing engines/skill identity. No claim is made that all REA providers are healthy.

| Artifact | SHA-256 |
| --- | --- |
| `libil2cpp.so` | `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326` |
| `.research/dumper/dump.cs` | `8b659049aada5d5037f0c4d108d81e8ab9ff5e8127a11dd78f0a3954aeced27e` |
| `.research/dumper/script.json` | `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb` |
| `.research/ghidra-battle-completion.json` | `ba156c045d729511d5408f3de8ddad6c8facc9f34c36abf9141a025fc6b320c2` |

Run `wsl bash tools/research/ghidra-battle-completion.sh` for the bounded native pass. It imports a disposable project without whole-program analysis and checks the binary hash. Native RVAs below exclude Ghidra's `0x100000` image base. Managed parameter types are not imported. The native body reader sometimes includes adjacent exception/throw flows; conclusions use the normal branch and typed dump fields only. In particular, the long exception tails in reward application and enum conversion are not additional gameplay behavior.

## Request and terminal outcomes

`NetworkBattleAPI.SelectMove` (`0x17882bc`) constructs `/session/battle/move` with the five anonymous-object fields `session_id`, `battle_id`, `type`, `owned_morty_id`, `move_id` (also indexed in `docs/protocol/native-transport.json`). `type` is `eMPBattleMoveType.ToString()`. There is no request nonce, turn index, or idempotency key in this constructor. Identical attacks on consecutive turns can therefore have identical bodies. A server must not infer durable deduplication from request-body equality alone. Cooldown timing can reject moves submitted too early, but does not establish whether a late identical request is a retry or a deliberate next turn.

`BattleTurnResultResponse` (`dump.cs:27081`) has `outcome`, `battle_abandoned`, `turn_datas`, `player_datas`. Its enum (`dump.cs:62272`) is:

| Outcome | Numeric value | Completion behavior in handler |
| --- | --- | --- |
| WIN | 2 | Ends battle; becomes ABANDONED (9) when `battle_abandoned` is true |
| LOSE | 3 | Ends battle |
| DRAW | 4 | Ends battle |
| CAUGHT | 5 | Ends battle; reward source BATTLE_CAPTURE (4) |
| RUN | 6 | Ends battle |
| ASK_SWITCH / FORCE_SWITCH | 7 / 8 | Continues battle |
| ABANDONED | 9 | Ends battle |

`NetworkBattleAPI.BattleTurnResultHandler` (`0x1788dc4`) performs these operations in order:

1. Deserialize the response, save previous outcome, reset timer/timeout fields, set new outcome.
2. Parse ordered `turn_datas`. The `type` string is converted to an act enum, then constructs ATTACK (1), ITEM (2), SWITCH (3), PARALYSED (5), or a generic act. Attack/switch `Persist` methods update battle analytics counters; their name does not establish HP/PP durability.
3. Construct `MPBattleTurnOpponentData` from `player_datas.player`, then `player_datas.opponent`. Use reward source BATTLE_CAPTURE for CAUGHT and BATTLE (3) otherwise.
4. For outcomes 2 through 6 inclusive or 9, call `EndBattle` (`0x1787b5c`), which disables in-battle event handlers and clears battle state.
5. If the player's rewards require a reward state, apply them to `MPPlayerData` immediately.
6. Invoke `TurnResultEvent` for the battle UI to animate the turn and transition.

This establishes why a terminal event must describe a committed result. The client can leave the battle and apply a new owned Morty before another gameplay request. The original server's database/SSE commit ordering is not observable here. A compatible server should commit the terminal marker, player mutations, capture record, and result before publishing `battle:turn-result`; a rollback must publish no success result. The completed battle must stop blocking future starts and must not accept a later mutation or publish/re-award a second terminal turn.

## `player_datas` and HP/PP

`MPBattleTurnOpponentData.SetFromDict` (`0x1585818`) recognizes `move_log`, `owned_items`, `player_xp_datas`, `xp_datas`, `attacks_to_learn`, `rewards`, `incentive`, `score`, and `rank`. `move_log` creates `MoveCooldowns`, whose dictionary includes `count`, `cooldown`, and `cooldown_next`. This object is not a general owned-Morty snapshot: adding arbitrary HP/PP keys to `player_datas.player` does not prove they are applied.

The attack-effect schema (`dump.cs:11459`) has `attacker_morty_datas` and `defender_morty_datas`; the base act also carries Morty dictionaries. These dictionaries are the authoritative animation/update mechanism. Server persistence must reflect the same already-computed HP, attack PP, status, and active-Morty changes returned in those dictionaries. Do not reconstruct damage or regenerate stats to persist a turn. Preserve other Morties and unrelated attack slots. XP, currency, item consumption, and reward totals must agree with the response wherever a supported turn already changes them. Empty rewards are preferable to fabricated XP/reward formulas.

The minimal terminal foundation is therefore: persist the turn's existing authoritative player HP/PP state; persist all supported terminal effects once; mark the battle completed for WIN/LOSE/RUN/CAUGHT; and publish only after successful persistence. Existing simplistic combat mechanics are not validated by this contract.

## Capture is an owned record

`MPBattleActItemData.SetFromDict` (`0x1584ff8`) reads `item_id`, `owned_morty_id`, `success`, `effect_value`, plus base act fields. It does not parse a capture reward from an extra arbitrary item field. The successful capture's owned record belongs in `player_datas.player.rewards`.

`MPRewardData.Cast` (`0x165e340`) recognizes `type`, `amount`, `amount_received`, `quantity`, `morty_id`, `level`, `variant`, `owned_morty_limit_reached`, `added_to_active_deck`, `owned_morty`, and `substitute` (plus item/avatar fields). `MPPlayerData.ApplyRewardData` (`0x1592464`) dispatches reward type 4 to `ApplyMortyRewardData(owned_morty, added_to_active_deck)`.

`ApplyMortyRewardData` (`0x15927ac`), on its normal path:

- Reads required `owned_morty_id` and `morty_id` from the owned dictionary.
- Feeds a single-element dictionary array to `MPOpponentData.SetMortiesFromDicts`, creating/updating the client owned-Morty model.
- Adds that owned ID to the active deck when `added_to_active_deck` is true.
- Updates seen/caught species lists.

Therefore a successful capture must create a durable record for the session's user and return that exact record's ID and owned-Morty dictionary. A random ID in a response without a database record creates client-only ownership. The owned record must describe the captured opponent using existing authoritative attributes; this evidence does not justify random replacement stats, a stat formula, or a guessed healing policy. Set `added_to_active_deck` only when the same ID is actually added to the server's deck; otherwise false. The species must be durably marked seen/caught wherever the server tracks those lists. Capture item consumption, battle completion, reward data, and the new record must succeed or fail together.

`"type":"MORTY"` is accepted. `MPRewardData.Cast` calls `ConvertExt.ToEnum<Int32Enum>` (`0x1b03958`), whose normal path converts the value to a string and calls `System.Enum.Parse` for the generic enum type. `eRewardType.MORTY` is 4 (`dump.cs:16519`). Thus both `"MORTY"` and numeric `4` identify this reward; numeric conversion is not a necessary compatibility fix. This conclusion is specific to rewards; it does not change the typed `BattleTurnResultResponse.outcome` contract.

## Remaining boundaries

No original-server capture probability, damage/stats, reward amounts, faint/blackout healing rules, or reliable cross-turn HTTP retry identity was recovered. Native evidence establishes the client consumption contract, not those formulas. Completing durable behavior for already-supported outcomes should not claim recovery of those mechanics. A full reconnect/replay protocol remains separate from preventing additional mutation of a completed battle.

## WIN with empty XP and rewards

A second bounded native pass, reproduced by the same script, writes `.research/ghidra-battle-empty-rewards.json` (SHA-256 `4e77243e3ed362b3d6009d723d1128a984203f8619da5805252682d41faf80fa`, 12 functions). It confirms that `xp_datas:[]` and `rewards:[]` are safe for a WIN whose supported behavior does not award XP or currency/items:

- `SetMortyXpDatasFromDicts` (`0x1586040`) allocates an array of the incoming length and skips construction for length zero. The constructor itself initializes cooldowns; it does not automatically create XP/reward entries.
- `MPBattleUI.<AwardXPDatas>d__104.MoveNext` (`0x15943dc`) returns immediately when its XP array is null. For an empty array, `FirstOrDefault` and `IndexOf` produce no selected entry, and the length check returns before any XP element dereference.
- `MPBattleUI.<StartTurn>d__86.MoveNext` (`0x159673c`) invokes that coroutine for both opponents' XP arrays without requiring an entry.
- `MPBattleUI.<FinishBattleWildMorty>d__83.MoveNext` (`0x15953e0`) uses the WIN branch for sound/dialogue and the defeated opponent's name; it does not require rewards or XP.
- `IsRewardStateRequired` (`0x1586248`) is false for null or zero-length rewards. `IsPlayerLevelStateRequired` (`0x1586214`) is false for null player XP. `IsAttacksToLearnStateRequired` (`0x15861b4`) is false for null attacks-to-learn data; `IsVideoRewardStateRequired` (`0x15862d4`) is false without an incentive.
- `MPBattleState.UIBattleFinishedHandler` (`0x15772d0`) checks the optional attacks, rewards, player-level and incentive predicates. If all are false, it takes the ordinary `StateController.Set` transition rather than requiring a reward/XP screen.

Thus removing fabricated, unpersisted WIN XP/stat/item rewards does not require inventing replacement XP entries. Keep the required `player_datas.player` and `.opponent` objects and the current supported cooldown/item state. Empty arrays avoid falsely promising authoritative rewards.

The request callback `NetworkBattleAPI.<>c__DisplayClass80_0.<SelectMove>b__0` (`0x1789eb4`) passes its request/response through `NetworkDefs.ParseHTTPError<eBattleMoveSelectError>` and dispatches the resulting enum to the move-selected event. Known failure enum values (`dump.cs:26652`) include `FAILED=9`, `NO_MOVE_PP=11`, `ITEM_UNUSABLE=14`, `COOLDOWN_NOT_EXPIRED=18`, `INVALID_MOVE=20`, and `FAILED_TO_LOAD_BATTLE=21`. The existing route's failure envelope should be preserved when disabling unsupported capture. This callback alone does not establish a new HTTP status/envelope mapping; follow the existing server mapping rather than inventing a new success-shaped capture result.

## Replacement server milestone

The current implementation supports ATTACK and RUN for the existing PvWM path. This is a durable gameplay foundation, not a reconstruction of combat formulas or completed Android acceptance. `session/battle-wild-morty/index.php` locks the user, validates the selected owned deck and a healthy active Morty, claims the WORLD spawn/player as BATTLE, and queues an initiator-private start snapshot in the transaction. A conflicting active battle or spawn claim rejects the start.

`session/battle/move/index.php` locks the session user and ACTIVE owned battle, then verifies the original private start snapshot, current room, and wild spawn state. ATTACK requires the battle's active Morty to have one unambiguous owned record and one matching attack with positive PP; its owned HP must match the battle HP. It decrements that selected owned attack's PP once and persists the exact player HP represented by the ordered action dictionaries. Unrelated Morties/attacks are not regenerated. Player damage remains the explicit legacy placeholder 20, AI damage remains random 1..3, and wild AI PP remains 1. These are unverified replacement mechanics, not recovered formulas. Switching is unsupported, so fainting of the sole active Morty currently produces LOSE.

Terminal behavior is:

| Outcome | Battle state and winner | Player/spawn effects |
| --- | --- | --- |
| RUN | CANCELLED, no winner | User WORLD; spawn WORLD; owned HP/PP unchanged |
| WIN | COMPLETED, initiating player winner | User WORLD; remove wild snapshot; persist selected PP/current HP; empty XP/rewards |
| LOSE | COMPLETED, opponent winner | User WORLD; spawn WORLD; persist fainted HP and selected PP |

The move queues the spawn removal/state event, user WORLD event, and one initiator-private `battle:turn-result` together with the state changes, then commits. `lib/events.php` persists the private recipient for the turn result; `sse/index.php` forwards its saved payload. A failed operation rolls back all mutations and queued notifications. A later request against the closed battle returns a conflict, without producing another terminal result. This establishes one terminal queue record per accepted terminal turn; it does not claim exactly-once SSE delivery, active-turn deduplication, cooldown enforcement, or reconnect replay.

The existing schema has no battle-room column and lacks indexes for several lock predicates. These queries can serialize unrelated activity; a database deadlock or lock timeout rolls back and returns 409 rather than reporting success. Other gameplay routes have not all adopted these locks. A second ACTIVE record claiming the same spawn blocks a move so an ambiguous legacy record cannot release or damage another battle's spawn.

Verified legacy RUN is permitted when the user and spawn still have WORLD state. It still requires consistent origin/room evidence and deliberately does not overwrite owned HP or PP from the legacy battle snapshot. Before a new start, `battle_reconcile_legacy_terminals` can close legacy ACTIVE rows only when their private start snapshot and explicit private terminal result agree. It accepts a single consistent RUN/WIN/LOSE/CAUGHT outcome, updates only the old battle state/winner, and never replays rewards or manufactures missing capture records. Ambiguous evidence remains unresolved and can continue blocking a start; reconciliation rolls back if the new start fails.

ITEM, including capture, returns HTTP 501 with `{"success":false,"error":{"code":"ITEM_UNUSABLE"}}`. It consumes no item, creates no owned Morty, and emits no success result. The capture-owned-record contract above defines the future implementation boundary. WIN now returns `xp_datas:[]` and `rewards:[]`, and awards no fabricated XP, stat growth, currency or CircuitBoard item. Native empty-array handling is established above.

The replacement move failure envelope is `{"success":false,"error":{"code":"FAILED"}}` except the ITEM_UNUSABLE case. HTTP 400 covers malformed input, unknown attacks and unsupported move types; 401 invalid session; 403 foreign battle/Morty/private spawn; 404 missing battle; 409 inactive or inconsistent battle/Morty/attack/origin/room/spawn state (including exhausted PP); 500 unexpected failure with rollback. These status choices are replacement-server behavior, not original-server error parity.

The Android capture on 2026-11-04 sent RUN with a valid active `owned_morty_id` and `move_id:null`. Initial string-only optional-field validation rejected it with 400. The repair accepts null optional values for RUN while ATTACK still requires both nonempty ID strings. An additive regression covers the captured shape and verifies null ATTACK identifiers reject without mutation.

`tests/protocol/test_battle_lifecycle.py` provides 24 additive UUID cases checking start claims/privacy, exact action HP/PP, terminal state/winner, spawn changes, empty WIN rewards, no-write rejections, unsupported capture, concurrent start/terminal requests, legacy recovery and two-account SSE delivery. It compares database/event snapshots on rejected requests and does not reseed shared accounts. Run it with the repository's protocol test environment (`python -m unittest discover -s tests/protocol -p test_battle_lifecycle.py`). [Android acceptance](android-battle-lifecycle.md) separately records native RUN and ATTACK/WIN, world return and the null RUN regression, using synthetic private starts. Live LOSE, natural encounter initiation and interrupted-battle reconnect remain outstanding.
