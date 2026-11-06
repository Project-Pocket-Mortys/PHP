# Shared battle startup boundary

This records a bounded Android 2.41.0 ARM64 native review and the proposed internal startup policy. It does not enable public acceptance, native event publication, human turns, or playable friend battles. The [start contract](friend-battle-start-contract.md), [invite contract](friend-battle-invite-contract.md), and [private views](private-battle-start-views.md) remain prerequisites. Replacement-server storage and cleanup rules below are design choices, not recovered original-server behavior.

## Reproduction and evidence

Run `wsl bash tools/research/ghidra-shared-battle-startup.sh` from the repository. It uses default WSL, REA 6.8.0 artifact inspection, the existing targeted Ghidra 12.1.4 toolchain without whole-program analysis, and the explicit Windows Python executable `C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe`. Generated evidence stays under ignored `.research/` with the `shared-battle-startup` prefix. This pass first reviewed existing start, invite and timeout outputs, then exported only the session/disconnect/ready methods needed for the remaining question. No database, emulator, credentials or runtime calls were used.

The pinned ELF SHA-256 is `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; metadata version is 31, metadata SHA-256 is `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`, and script mapping SHA-256 is `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`.

The wrapper verifies 14 bounded native methods, including two generic ready constructors, and produces `ghidra-shared-battle-startup.json`, `shared-battle-startup-methods.json`, `shared-battle-startup-arm64.txt`, and `rea-shared-battle-startup-6.8.0-artifact.json`. The manifest records signatures, actual next-method bounds and SHA-256 values for each body. REA establishes artifact identity only. Ghidra may follow exception fallthrough beyond actual method boundaries; the bounded ARM64 export and normal return paths constrain the conclusions.

| Method | Native RVA | Bounded bytes | Relevant behavior |
| --- | --- | --- | --- |
| `NetworkBattleAPI.Disconnected` | `0x1786f34` | 92 | Calls `Leave`. |
| `NetworkBattleAPI.Leave` | `0x1786fbc` | 532 | Unregisters battle start, move-timer and result handlers; clears local timer, flags, battle ID/type and enemy. |
| `NetworkBattleAPI.UpdateTimeOut` | `0x1787204` | 156 | On watchdog expiry, calls session disconnect reason 11. |
| `NetworkBattleAPI.SelectingMove` | `0x1788078` | 580 | Sends ready with session and current battle ID. |
| `NetworkBattleAPI.<SelectingMove>b__79_0` | `0x1789814` | 240 | Success starts the 180-second watchdog; any other result disconnects reason 10. |
| `NetworkSessionAPI.Disconnect` | `0x17b37ac` | 252 | Records reason and closes the event source. |
| `NetworkSessionAPI.ESStartHandler` | `0x17b5fec` | 688 | Parses session configuration and requests player details. |
| `NetworkSessionAPI.ESClosedHandler` | `0x17b6a88` | 192 | Removes event-source handlers, stops coroutines, emits disconnected event. |
| `NetworkSessionAPI.ESEndedHandler` | `0x17b6b48` | 12 | Sets disconnect reason 5. |

Check exact bounds against the generated manifest when reproducing; Ghidra presentation hashes can vary.

This run's output SHA-256 values are `04ee5076059220c7a72c986b0a651ec6cbdf974132822bbe20895e5661cfc3d7` for Ghidra JSON, `66f66bb1dea0c6b090b81a8f207dc793521c8e08dd6d8c7266d9dff27b594ac0` for the method manifest, and `4fa124d9cda8c0a2a691430ee360549a7dd043765343bc79607eba94d2d3910a` for bounded ARM64 disassembly.

## Ready and transport loss

Ready remains exactly `/session/battle/ready` with `session_id` and `battle_id`. The callback uses `ParseHTTPError<eBattleReadyError>`: NONE (4) writes float 180 to the watchdog; every other result disconnects the session with numeric reason 10. It does not parse a timer, phase number, opponent, acknowledgement ID, or battle snapshot from the success body. The watchdog's eventual reason 11 disconnect is distinct from server gameplay expiry. Neither 180 seconds nor the event-source connection coroutine's 15-second timeout establishes a server startup deadline.

Initial animation completion invokes selecting-move, and later animation/menu transitions can invoke it again. There is no ready nonce or turn number available to distinguish a delayed initial retry from a later phase. An internal startup implementation may record the first ready per persisted participant idempotently and transition STARTING to READY when both exist. It must not use repeated ready requests to advance another turn or renew the fixed deadline. READY here is a startup barrier, not permission to resolve moves or publish a timer.

Session `Connect` submits account/consent identity, and its successful HTTP callback (`0x17b73d4`) opens the event source using the returned URL. `ConnectToEventSourceCo.MoveNext` (`0x17b7614`) waits for session start, bounded by 15 seconds. `ESStartHandler` stores the session ID, configures world/pings/keepalive and requests player details. The examined methods establish no battle-resume request, persisted battle cursor, cancellation HTTP call, or replacement terminal result.

On close, the session broadcasts disconnect; the battle API's disconnect handling calls `Leave`, which clears battle identity and subscriptions. This does not demonstrate automatic return to a world UI, successful battle reconstruction, or a human forfeit. It also does not prove that these are the only reconnect paths in the whole client. A future publisher must test when start handlers become active after a fresh connection and after transport interruption. Replaying a start immediately on transport opening could precede registration or restart an already-running intro. Duplicate-start safety and client cancellation presentation remain blockers to public startup.

Invitation revoke/decline removes invitation UI state, and invitation `battle:start` handling clears pending invitations. Accepted notification alone does not enter battle. These handlers do not establish a post-start human abort event. Do not invent a `battle:cancelled` event or disguise administrative abort as a win/loss, ABANDONED result, reward, or wild timeout.

## Internal startup policy

Activation must lock both users in deterministic order, then invitation/session and associated claims/storage in the established common order. Authenticate the actor and revalidate ownership after waiting. Require exact participant identity, both exact claims, live preparation lease, eligible friendship/invitation and WORLD users, no legacy active battle on either participant side, complete immutable party snapshots, and both frozen private views/context with intact hashes and current profile/resource comparisons. Do not regenerate a missing or changed snapshot/view to rescue activation.

One transaction changes both users to BATTLE, invitation to ACCEPTED, session to STARTING, fixes a bounded startup deadline once, and writes exactly two durable recipient start INTENTS bound to the same battle and each recipient's immutable view identity/hash. A failure at any write must roll back the entire activation. These intents are internal durable records, not event_queue rows, SSE publication, evidence of delivery, or native acknowledgements. A retry validates the persisted activation and returns its identities; it never extends either deadline or creates another intent pair. Revalidation appropriate to WORLD preparation must not accidentally reject a valid STARTING replay merely because activation already changed both users to BATTLE.

The internal ready operation authenticates either persisted participant, verifies exact claims and active session identity, checks the fixed deadline before accepting a signal, and records that participant once. Both recorded signals move STARTING to READY atomically. Duplicate ready is an unchanged success while valid. It cannot release claims, create turns, update PP/HP/items, adjudicate outcomes, or publish timers/results. A client request supplies no recipient role; derive it from the authenticated persisted participant. Terminal, foreign, expired and malformed identities fail closed. Public ready routing remains a separate future integration.

Internal recovery selects only the authenticated participant's intent/view under shared lifecycle validation. It must not depend on the room event cursor, copy both perspectives into a response, expose opponent owner resources or recover another player's view by a caller-supplied role. Preserve battle identity across account session rotation, but reauthenticate current ownership on every read. An internal recovery read is not transport publication or proof that the native client can resume.

Abort and startup expiry lock the same participant pair and shared lifecycle rows, verify the exact original claims, atomically restore both BATTLE users to WORLD, release only those exact claims, mark the shared session CANCELLED with a reason, and retire both intents. Replays preserve the terminal state and newer claims. Missing/redirected/extra claims or incompatible user state fail closed; never restore a user now belonging to another battle. Retain private snapshots/views as inert historical preparation records unless a separately specified retention policy removes them. An ACCEPTED invitation need not be rewritten into an invented native invitation outcome: it remains history, while the session records cancellation.

The fixed startup deadline continues to bound READY until a separately implemented gameplay handoff exists. Thus a one-sided ready, a recovered internal view, duplicate activation/ready, and reaching READY cannot create an indefinite occupied session. A bounded expiry worker must cover both STARTING and READY independently of whether either client retains SSE. Preparation cleanup restricted to PREPARING cannot provide that guarantee.

## Current guard audit and disabled work

`battle_has_shared_membership` checks any claim by player ID without filtering session state. Orphan and malformed claims block actions too. Keeping both claims throughout STARTING and READY therefore preserves existing world, party and resource exclusion without changing the guard's phase vocabulary.

`world_action_has_active_battle` checks the shared claim before legacy terminal repair. Its guarded heal, join-room, leave-room, shiny-potion and absorption callers remain blocked for both roles. Wild battle start also checks membership while holding the user row lock. Invitation creation and stream eligibility check either participant's claim; WORLD checks additionally reject BATTLE users. Existing deck/party, trade and preparation resource/profile writer guards similarly consult membership after user locks. Source review confirms the state-independent mechanism; it is not a substitute for regression tests of both new phases and both participant roles.

`session/state/index.php` only echoes a supplied state and does not write users. Room join writes WORLD only after the shared world-action guard. SSE updates cursor/liveness, and currently invokes separate legacy battle timeout and PREPARING cleanup. It has no shared STARTING/READY recovery or expiry integration. Retaining a claim prevents world writers from treating startup as an ordinary world session; its future recovery/expiry work must preserve that invariant.

The existing public `session/battle/ready` uses owner-only legacy `battles` lookup, current-room validation and direct `battle:move-timer-started` publication. Existing moves and timeout cleanup likewise use legacy owner/spawn state. They cannot implement human readiness, both-user restoration or shared claim release. Keep internal startup identities out of those paths. Public invitation acceptance stays HTTP 501 FAILED, with no publisher or public shared ready/recovery/abort route.

Before native publication, resolve authenticated delivery and recipient recovery ordering, duplicate-start handling, transport loss presentation, safe client abort behavior and phase-aware ready retry rules. Human turn pairing, deadlines, move resolution, surrender, terminal rewards and ranking remain independent unimplemented contracts. Internal startup bookkeeping alone establishes none of them.
