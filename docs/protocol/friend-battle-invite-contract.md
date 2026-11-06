# Native friend battle invitation contract

This is Android 2.41.0 ARM64 client evidence, not recovered original-server storage, authorization, token generation, or matchmaking policy. Reproduce in default WSL with `bash tools/research/ghidra-friend-battle-invites.sh`. The exporter uses REA 6.8.0 artifact inspection, targeted Ghidra, and Capstone over actual ELF bytes bounded by the next metadata method entry. Ghidra can follow exception fallthrough past that boundary; the bounded instructions are authoritative. Generated evidence stays under ignored `.research/`.

Binary SHA-256: `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; metadata version 31; metadata SHA-256: `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`; dumper script SHA-256: `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`. The generated `friend-battle-invites-methods.json` also records each selected native RVA, signature, body bound, and body hash.

This run verified 74 bounded methods. Evidence files and SHA-256 values: `.research/ghidra-friend-battle-invites.json` `9a3947b3231d3a44106b53d69f30c77cce30a2bb9f62212ffda2e6f6b16acf0b`; `.research/friend-battle-invites-arm64.txt` `4c45889407ac80a30dd754be28ebc3dbbe08274f432bdfcc516c903031ee6f3e`; `.research/friend-battle-invites-methods.json` `0a29fe33e67e73528dde1b7bc63c74aa3b6c278be5913e5d96b4c45e75131aba`. REA artifact identity is `.research/rea-friend-battle-invites-6.8.0-artifact.json`. The manifest also preserves exact path/event/type string values with script addresses. Ghidra presentation hashes can vary between runs.

## HTTP requests and callbacks

Paths and event names below are exact `ScriptString.Value` values. Sanitized Ghidra labels replace punctuation with underscores and must not be used to reconstruct paths. The three path literals occur at script addresses `51034168`, `51034176`, and `51034184` respectively.

| Native producer | Exact route | Exact JSON body |
| --- | --- | --- |
| `SendInviteUser`, `0x178b110` | `/session/battle-invite/create` | `session_id`, `opponent_player_id`, `battle_type`, all strings |
| `RespondToReceivedInvite`, `0x178b440` | `/session/battle-invite/response` | `session_id`, `token` strings; `accept` boolean |
| `CancelPendingSentInvite`, `0x178c548` | `/session/battle-invite/revoke` | `session_id`, `token` strings |

The session is the active session; opponent ID comes from the selected `MPUserData.player_id`. Anonymous constructor 5 at `0x1cef788` establishes the create field names and order; producer instruction `0x178b388` calls it. Constructor 12 at `0x1cbe088`, called at `0x178b6c8`, establishes response fields and stores `accept` as a byte. The producer compares source to `ACCEPTED=2`; only that source yields `true`. Constructor 11 at `0x1cbd2f4`, called at `0x178c728`, establishes revoke fields. Neither response nor revoke sends `battle_invite_id`, opponent ID, battle type, or the numeric reply-source enum.

`MPFriendState.UIBattleHandler` at `0x15a0ec0` passes exact `PvF` (script string address `51104328`) to `SendInviteUser`. `InviteQueueChanged` also tests received invite type equality with `PvF` to set `friendInvitePending`. Do not substitute `PvP` for this friend route. The generic producer accepts a string; that is not proof of an exhaustive allowed server type list.

Create callback `0x178d698` uses typed `ParseHTTPResponse` and checks `eSendInviteError.NONE=16` and a nonnull response. `SendInviteResponse` fields are `battle_invite_id:string` (`+0x10`), `battle_type:string` (`+0x18`), `battle_invite_ttl:float` (`+0x20`), `token:string` (`+0x28`). It creates the local `sentInvite` with these fields and the selected opponent. A failed/nonobject result clears `sentInvitePending`; successful typed handling leaves it pending until later lifecycle handling. The DTO has no opponent dictionary.

Response callback `0x178e1c0` and revoke callback `0x178e130` call `ParseHTTPError` only: successful response bodies are ignored. Acceptance does not deserialize a battle or directly start one from its HTTP body. The response callback reports the native error to its optional caller; revoke has no external success callback. Specific errors use an unsuccessful HTTP status and `{"error":{"code":"TOKEN_EXPIRED"}}`, with an exact enum name. See the [friend lifecycle contract](friend-lifecycle-contract.md) for the common `ParseHTTPError`/`ParseHTTPResponse` implementation, also bounded in this export.

## Session events

`Connected` (`0x178a698`) resets incoming queue, pending flags, and sent invite, then registers these handlers through `NetworkSessionAPI.On`. Exact event strings are `battle-invite:accepted` (`51141208`), `battle-invite:declined` (`51141216`), `battle-invite:received` (`51141224`), `battle-invite:revoked` (`51141232`), and `battle:start`. The handler deserializes the JSON text in `NetworkEventSourceResponse.data`; there is no required inner `data` wrapper in the DTO.

| Event / native handler | JSON DTO | Client behavior and audience implied by consumer |
| --- | --- | --- |
| `battle-invite:received`, `0x178c888` | `battle_invite_id:string`, `battle_type:string`, `battle_invite_ttl:float`, `from_player:object`, `token:string` | Recipient adds incoming invite and updates queue. `from_player.player_id` is directly indexed, then converted to string. Reuses a room user by that ID or constructs `MPUserData` from the dictionary. |
| `battle-invite:declined`, `0x178cb98` | `battle_invite_id:string` | Sender compares it with current sent invite ID; a matching ID clears sent invite/pending and invokes local declined event. No pending sent invite or a different ID has no effect. |
| `battle-invite:revoked`, `0x178cd68` | `battle_invite_id:string` | Recipient finds the first incoming invite with equal ID, removes it, updates queue. No match has no effect. |
| `battle-invite:accepted`, `0x178cc6c` | `battle_invite_id:string`, `battle_type:string`, `opponent:object` | Deserializes, creates a temporary invite with zero TTL/null token, copies existing sent countdown into temporary total, returns. No ID comparison, persisted assignment, pending clear, callback, or battle start appears in the bounded body. |

The accepted behavior is unusual but directly checked against all 252 bytes from `0x178cc6c` to `0x178cd68`: `0x178cd34` calls `MPBattleInviteData.ctor`; `0x178cd38` reads the existing sent invite; `0x178cd40` reads its countdown; `0x178cd48` writes that value to the temporary object's total; `0x178cd60` returns. Do not infer an unseen battle transition from the event name. `opponent` is consumed through `MPUserData`, but this handler does not establish an enforced sender-only audience. Audience descriptions above describe useful state consumers, not proof of original server delivery rules.

The separate invitation `BattleStartHandler` (`0x178ced8`) clears sent invite/pending and auto-declines every remaining received invite. Battle transport has its own `battle:start` handling; this invitation handler does not parse the battle payload. See [friend battle start contract](friend-battle-start-contract.md) for that separately recovered boundary when available.

## Lifetime, tokens, correlation, and ordering

`MPBattleInviteData.ctor` (`0x1584024`) copies server float TTL into both `expirationTimeTotal` (`+0x28`) and `expirationCountdown` (`+0x2c`), and stores ID/type/user/token. `ManualUpdateExpiration` (`0x1584078`) subtracts Unity `deltaTime` and clamps at zero. The units are seconds of client update time, not an absolute Unix expiration timestamp. No hardcoded invitation TTL or server expiry policy is recovered here. The expiry checks only update initially positive countdowns; an initial zero does not itself trigger automatic expiry.

`Update` (`0x178af08`) checks received then sent expirations. Received expiry (`0x178af20`) responds with `TIMED_OUT=5`, which sends `accept:false`. Sent expiry (`0x178b040`) revokes with `TIMED_OUT=5` and invokes local expired event. Tokens are opaque strings copied from the create response or received event and echoed with the acting session. The client proves no token format, signature, claims, shared-versus-participant-specific construction, server TTL, or replay policy. A replacement server must authenticate the actor and authorize the token's operation, but those are implementation invariants, not decoded original-server policy.

Response removes the selected incoming invite and updates queue before the HTTP result. Acceptance recursively auto-declines every other incoming invite before submitting its own acceptance request. Send rejects locally with `SENT_INVITE_PENDING` when a send is pending; otherwise it auto-declines received invites of the same `battle_type` before creating the outgoing invite. Cancel does nothing without a populated sent invite; when present, it copies its token into the request, clears local sent/pending state, then issues HTTP. A cancellation during an unresolved create cannot revoke an invite whose token has not yet arrived.

Create HTTP completion must establish the local sent ID before a matching decline can clear it; an earlier decline sees no sent invite. This is a client-observable ordering constraint, not evidence of an original server transport barrier. Preserve invite IDs across response/event correlation and avoid delivering obsolete terminal events as if they belonged to a newer invitation. No incoming deduplication or sequence number is visible: received appends, revoked removes the first ID match. Network reconnect clears local invitation state and registers handlers anew; no invitation-list refresh endpoint is established by these methods.

## Native errors and reply sources

Exact spellings and numeric values from metadata:

| Enum | Values |
| --- | --- |
| `eSendInviteError` | `UNKOWN=0`, `NO_RESPONSE=1`, `INVALID_RESPONSE=2`, `SENT_INVITE_PENDING=3`, `SESSION_ID_INVALID=4`, `SESSION_NOT_FOUND=5`, `OPPONENT_SESSION_INVALID=6`, `OPPONENT_STATE_INVALID=7`, `OPPONENT_PLAYER_ID_INVALID=8`, `WILD_MORTY_ID_INVALID=9`, `BOT_ID_INVALID=10`, `FAILED=11`, `NOT_ENOUGH_ENERGY=12`, `NOT_ENOUGH_COUPONS=13`, `ARENA_NOT_ACTIVE=14`, `ARENA_MAINTENANCE=15`, `NONE=16` |
| `eRespondToSentInviteError` | `UNKOWN=0`, `NO_RESPONSE=1`, `INVALID_RESPONSE=2`, `TOKEN_INVALID=3`, `TOKEN_EXPIRED=4`, `TOKEN_NOTVALID=5`, `FAILED=6`, `NONE=7` |
| `eRespondToReceivedInviteError` | `UNKOWN=0`, `NO_RESPONSE=1`, `INVALID_RESPONSE=2`, `TOKEN_INVALID=3`, `TOKEN_EXPIRED=4`, `TOKEN_NOTVALID=5`, `ACCEPT_INVALID=6`, `FAILED=7`, `NONE=8` |
| `eInviteSentReplySource` | `NONE=0`, `CANCELED=1`, `OPPONENT_ACCEPTED=2`, `OPPONENT_DECLINED=3`, `OPPONENT_LEFT_ROOM=4`, `TIMED_OUT=5` |
| `eInviteReceivedReplySource` | `NONE=0`, `OPPONENT_CANCELED=1`, `ACCEPTED=2`, `DECLINED=3`, `AUTO_DECLINED=4`, `TIMED_OUT=5` |

These enum names establish compatible error vocabulary; they do not establish every original server validation trigger. No live accounts, database writes, emulator actions, or deployed runtime changes were used for this native contract.
