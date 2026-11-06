# Friend battle start and readiness contract

This records Android 2.41.0 ARM64 client consumption of human friend battle starts. It establishes the handoff and participant perspective; it does not establish human turn resolution, original server transactions, or readiness deadline policy. Invitation transport is covered separately in [friend-battle-invite-contract.md](friend-battle-invite-contract.md).

## Evidence and reproduction

Run `wsl bash tools/research/ghidra-friend-battle-start.sh` from the repository. The script uses default WSL, REA 6.8.0 artifact inspection, a disposable targeted Ghidra import, and the explicit Windows Python executable at `C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe`. New ignored outputs use `friend-battle-start`: Ghidra JSON, bounded Capstone disassembly, method bounds and body hashes, and REA artifact identity. It reuses the established battle research toolchain without whole-program analysis or runtime interaction.

The ELF SHA-256 is `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; metadata version is 31 and metadata SHA-256 is `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`. Script mapping SHA-256 is `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`. Native RVAs exclude Ghidra's image base. Conclusions use normal paths and actual next metadata method boundaries: Ghidra can follow failed-cast/throw flows into adjacent methods. REA artifact identity is not semantic evidence.

This run verified 50 bounded methods (48 Ghidra entries plus generic ready constructors). Output SHA-256 values: `.research/ghidra-friend-battle-start.json` `c7eb034fce8a28fa0a6530cc44ab633c42174c8f61108ad962ec53b95d6f42a7`; `.research/friend-battle-start-methods.json` `6975b78d69fb14a5195ad95e8f1b2c604238eae383127bd3683a84a69f328cdd`; `.research/friend-battle-start-arm64.txt` `571fe1763fa5508c2dc779e8bc661edcd948c7985f0db6a3faa320564ba5d01b`. Ghidra presentation hashes can vary on a rerun. The REA inspection reports artifact evidence ID `ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`.

## Friend UI and the decisive handoff

`MPFriendState.UIBattleHandler` (`0x15a0ec0`) displays the waiting popup and calls `SendInviteUser(friendData, "PvF", callback)`. The client wire battle type for friends is **`PvF`**. A server-internal `FRIEND` label must be translated before serializing client events. Its callback (`0x15a2108`) treats send error enum 16 as success, maps OPPONENT_STATE_INVALID (7) to declined-style popup text, and maps other errors to failure text; success does not itself enter a battle.

`BattleInviteReplyPopupHandler` (`0x15a18bc`) clears the selected invitation reference and calls `RespondToReceivedInvite`: popup button index 1 maps to response enum 2, other indices to enum 3. This is distinct from `UIAcceptHandler`, which accepts a friendship request. `WaitingForBattleInviteReplyPopupHandler` (`0x15a171c`) cancels the pending sent invitation and then considers received invitations or returns to the prior state.

The separate invite native pass establishes that `battle-invite:accepted` parses invitation metadata without calling the battle start API. The invitation API's `battle:start` handler clears invitation state. Consequently accepted notification alone cannot start play, and this client does not establish an accepted-before-start prerequisite. Delivering accepted before start can be a server presentation choice, but is not a recovered synchronization requirement. See the invite contract for those bounded handlers and limitations.

`NetworkBattleAPI.BattleStartHandler` (`0x1788674`) consumes **`battle:start`**, stores the battle ID/type, applies `player` to the existing local `MPPlayerData`, constructs cooldowns, constructs the enemy, and calls `StartBattle` (`0x17872d0`). `StartBattle` disables available handlers, enables in-battle handlers, stores enemy/meta/cooldowns, resets turn tracking, and invokes `StartEvent(battleType, enemyData)`.

For `PvF`, the battle-start type dispatch takes its ordinary human-user branch: it constructs `MPUserData(opponent)` and **overwrites its type with `USER` (2)**. `PvB` instead constructs `MPBotData` and sets BOT (3); PvWM sets WILD_MORTY (1). The parser has no `isBot` or `isFriend` start switch. Adding those booleans does not select a human battle path.

## Declared envelope versus operationally required data

`BattleStartResponse` (`dump.cs:27051`) declares `battle_id`, `battle_type`, `player`, `opponent`, `meta`. Declaration alone does not prove every key is directly indexed. On the `PvF` branch the base `MPBattleMetaData` has no fields and its `SetFromDict` (`0x1572888`) is a no-op; the handler constructs it without the envelope `meta`. An empty object is appropriate; arena metadata is not a requirement for friends.

The normal start path directly indexes `player["move_log"]`. `MoveCooldowns(dict)` (`0x1585e70`) then directly indexes `cooldown`, `cooldown_next`, and `count`. An empty outer object or array is therefore insufficient. For a battle with no history, use:

```json
{"move_log":{"cooldown":{},"cooldown_next":{},"count":{}}}
```

The setters initialize missing move-type entries to zero in these inner dictionaries. Preserve any authoritative nonzero cooldown/count state where applicable.

The participant model supplies the following data. These are consumed model fields and display/start dependencies, not proof that each field is an immediate dictionary index in the envelope handler.

| Data | Client consumption |
| --- | --- |
| `player_id` | `MPOpponentData.SetFromDict` (`0x1589ab8`) sets the participant's network ID; it is the real other user's player ID in `opponent`, never a fabricated bot ID. `bot_id` writes the same slot and should not accompany human data. |
| `username` | Human trainer intro and username bar consume the opponent's name. |
| `player_avatar_id` | Base parser resolves the trainer asset; `MPUserData.SetFromDict` (`0x165f694`) also stores the avatar ID. Supply an actual compatible avatar. |
| `level`, `streak` | Human subclass parses integer level and XP multiplier. |
| `owned_morties` | Parsed through `SetMortiesFromDicts` (`0x158c668`); identities, current HP/status, stats and owned attacks must describe that user's actual party. Reuse the established owned-Morty schema. |
| `active_owned_morty` | String owned-Morty ID selecting the initial battler. It must resolve within that participant's supplied Morties. The intro uses this for both sides. |
| `owned_items` | Base parser accepts item dictionaries. Keep local inventory authoritative; this evidence does not establish friend-battle item restrictions or a requirement to expose another user's entire inventory. |
| `type`, `state` | Base parser enum-parses present values. Opponent type is overwritten to USER by the PvF handler. `state` recognizes BATTLE (2). Do not substitute invented `FRIEND`/boolean values for typed fields. |

There is no evidence that `_meta.isControlledByAI`, `_meta.isPlayerInDB`, or arbitrary `isBot`/`isFriend` booleans replace these fields. Avoid copying a wild opponent's synthesized identity or Morties into a human payload.

`MPWorldState.NetBattleStartHandler` (`0x1648070`) constructs local `MPBattleOpponent` side 0 from the session's persistent local player, and enemy side 1 from the parsed enemy argument; it builds `MPBattleInfo`, pauses the room, and transitions to battle. Therefore each participant requires a separately serialized perspective: for A's event, `player=A` and `opponent=B`; for B's, `player=B` and `opponent=A`, with the same battle ID and `PvF` type. Reusing the same envelope for both recipients corrupts local-player state and enemy selection. This is a compatibility consequence of client consumption, not evidence of an original server storage layout.

`MPBattleUI.SetUp` (`0x1574db4`) consumes both trainer assets and shows the human opponent's username/avatar. The start coroutine (`0x1596324`) animates the trainer introduction, sends out the enemy's active Morty, then the local active Morty. Empty/mismatched party or active IDs are unsafe even if dictionary parsing succeeds. The dictionary constructor need not reject a missing key for the subsequent animation to dereference a missing model.

The enemy selection calls the `GetMortyData(MPOpponentData)` overload (`0x158daec`); its predicate (`0x158e42c`) compares each Morty's owned ID (`+0x18`) with `opponentData.battleStartMortyId` (`+0x40`). The local selection calls `GetMortyData(string)` (`0x158da10`) with that same active-ID field; its predicate is `0x158e408`. This confirms active-ID membership on both sides without relying on Ghidra's ambiguous overload labels.

## Readiness and timers

After both initial send-out animations, `MPBattleUI.<StartBattle>d__79.MoveNext` calls `SelectingMoveRequest` (`0x15756f0`). That opens the main menu and invokes the selecting-move event. `MPBattleState.UISelectingMoveHandler` (`0x1576e30`) calls `NetworkBattleAPI.SelectingMove` unless the battle outcome is ABANDONED (9).

`SelectingMove` (`0x1788078`) sends `/session/battle/ready` with exactly `session_id` and `battle_id` (anonymous type 3, `dump.cs:340`). It carries no opponent ID, invitation ID, player-side flag, or turn number. Readiness is a client animation completion signal, and can occur at different times for the two participants. It is also used when selecting moves again; it is not a unique once-per-battle handshake.

The callback (`0x1789814`) uses `ParseHTTPError<eBattleReadyError>`. NONE (4) sets the network timeout field to 180 seconds; any other result disconnects the session with reason enum 10. This is the client watchdog, not an original server ready deadline or turn duration. Preserve the existing ready success/error envelope mapping.

The exact timer event is **`battle:move-timer-started`** (`NetworkDefs.ES_BATTLE_MOVE_TIMER`, `dump.cs:34220`; exact string literal also present). `BattleMoveTimeResponse` declares integer `timeout`; `BattleMoveTimeHandler` (`0x1788d00`) converts it to float, constructs `MPBattleTimerData`, stores it, and fires the timer-start event. `battle:start` itself has no timeout field. Timer publication before the client has enabled in-battle handlers risks loss; the explicit ready requests provide a point at which each participant has entered the battle UI. Starting the human move timer only after both participants are ready is a sensible server design, but the client's parser does not prove the original server's exact barrier, deadlines, retries, or missing-participant policy.

## Implementation boundary

Safe implementation inputs now include the `PvF` wire label, perspective-specific human snapshots, required cooldown object shape, active-Morty identity consistency, ready request shape, and timer event name. Native evidence does not establish human simultaneous-move pairing, ordering/tie rules, server damage/XP formulas, shared readiness persistence, or disconnect adjudication. Those still need a deliberately specified shared-participant implementation; emitting apparently valid starts through the existing one-player wild-battle storage would not complete a human battle contract. No runtime or emulator verification was performed in this pass.
