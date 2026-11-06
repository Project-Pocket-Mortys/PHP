# Native friend lifecycle contract

This records Android 2.41.0 ARM64 client behavior, not a reconstruction of the original server's database policy. Binary SHA-256: `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; IL2CPP metadata version 31. Reproduce in default WSL with `bash tools/research/ghidra-friend-lifecycle.sh`. REA 6.8.0 records root artifact identity; targeted Ghidra and actual ELF instructions decoded with Capstone establish behavior. Ignored raw evidence: `.research/rea-friend-lifecycle-6.8.0-artifact.json`, `.research/ghidra-friend-lifecycle.json`, `.research/friend-lifecycle-methods.json`, `.research/friend-lifecycle-arm64.txt`. The method manifest includes metadata/script hashes, RVAs, next-entry bounds, signatures and body hashes. Ghidra can follow exception fallthrough beyond a method: the Capstone next-metadata-entry boundary is authoritative.

The reproduced run verified 102 bounded methods. Metadata SHA-256: `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`; dumper script SHA-256: `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`. Evidence SHA-256: Ghidra JSON `38e18c9cc684859919a03a37c7ea8453deff3ab08fd0eaa2b269db9e112c812d`, bounded disassembly `706807b87d6fe63422a82708a2fd7e184a156f00295631ddc8f3b211a8132e56`, method manifest `8a3bb7eb2b36e0e387ae28191a95ebf5c9f0ddbd486ee343b4ffc5e4eaba29b7`. These hashes identify this run; Ghidra presentation may vary between runs.

## Requests and successful responses

All routes are HTTP requests built by `NetworkFriendAPI`; the session ID comes from the active session. The selected player ID is the other user's public `player_id`, never a relationship-row ID.

| Route under `/session/friend/` | Native producer RVA | JSON request fields | Successful body consumer |
| --- | --- | --- | --- |
| `list` | `RefreshData`, `0x178f68c` | `session_id` string | `FriendRefreshDataResponse` |
| `search` | `SearchForUser`, `0x178fe50` | `session_id`, `query` strings | `FriendSearchForUserResponse` |
| `request` | `SendRequest`, `0x1790070` | `session_id`, `player_id` strings | Error parser only; body ignored |
| `response` | `RespondToRequest`, `0x17902f0` | `session_id`, `player_id` strings; `approve` JSON boolean | Error parser only; success causes `list` refresh |
| `remove` | `Remove`, `0x1790880` | `session_id`, `player_id` strings | Error parser only; success causes `list` refresh |

The constructor metadata provides the exact names: anonymous type 0 (`session_id`), 13 (`session_id`, `query`), 14 (`session_id`, `player_id`), 15 (`session_id`, `player_id`, `approve`). Actual type-13/14/15 constructors are at `0x1cbf368`, `0x1cc00f4`, `0x1cc0e88`; the bool is stored as a byte, not an alternate response/status parameter. The producer bodies call those constructors. `approve:true` accepts, `approve:false` rejects: UI handlers at `0x15a0fb4` and `0x15a11d4` pass 1 and 0 respectively.

Callbacks `0x1793320` (request), `0x17933cc` (response), and `0x1793644` (remove) call `ParseHTTPError`, not typed response deserialization. The existing request's raw relationship row, response's JSON scalar `1`, and remove's success object are therefore compatible successful bodies. Changing those bodies is not a native defect fix. Response/remove success schedules an immediate refresh, then reports success after that refresh; a failed refresh reports operation `FAILED`.

Search DTO (`0x17964a0` constructor): `player_id`, `username`, `player_avatar_id` strings and `level` int. Callback `0x17931fc` creates an `MPFriendData` only when the parsed DTO is nonnull; its displayed username comes from the submitted query. Explicit JSON `null` reaches the nullable-result path. The current empty HTTP200 body is not a well-formed JSON document; its exact JsonFx empty-string behavior has not been established here. Do not claim the client requires an invented `USER_NOT_FOUND` error. The native enum has no such name.

## List shape and direction

`FriendRefreshDataResponse` fields and offsets:

| Field | Native type / contract |
| --- | --- |
| `donation_request` (`+0x10`) | Nonnull `DonationRequestResponse` object |
| `requests_received` (`+0x18`) | Array of other-user dictionaries; incoming senders |
| `requests_sent` (`+0x20`) | Array of other-user dictionaries; outgoing recipients |
| `friends` (`+0x28`) | Array of other-user dictionaries; accepted friends |
| `limit_friends` (`+0x30`) | Int32, server-provided capacity |
| `poll_period` (`+0x34`) | Int32, seconds between UI refreshes |

The response constructor `0x1796428` initializes the three arrays empty. Emit explicit arrays, including when empty; null arrays cause the refresh path to throw. `RefreshDataFromResponse` at `0x178f88c` clears both client lists, adds received rows to `friendRequests`, accepted rows to `friends` with `isPending=false`, and sent rows to `friends` with `isPending=true`. Capstone directly shows the sent loop passing `w2=1` at `0x178f9e4`, versus accepted `w2=0` at `0x178f9a4`. Pending is inferred from the enclosing array, not read from a `pending` row key. Incoming and outgoing dictionaries must describe the other user; swapping their direction changes who can be accepted in the UI.

`UpdateFriendRequestFromDict` (`0x178fa18`) and `UpdateFriendFromDict` (`0x178fc2c`) directly index `player_id` before constructing/updating rows: this key is required. The ordinary display projection is `player_id`, `username`, `player_avatar_id`, `level`, and, for accepted rows, `wins`, `losses`, `online`. Other display keys are parsed by enumeration, so absence leaves defaults rather than failing on a dictionary index. Supply useful display values consistently rather than treating every recognized key as mandatory.

`MPFriendData.SetFromDict` (`0x1588130`) delegates to `MPUserData.SetFromDict` (`0x165f694`) and `MPOpponentData.SetFromDict` (`0x1589ab8`):

- `player_id`, `username`, `player_avatar_id`: `Convert.ToString`.
- `level`, `wins`, `losses` (and optional `streak`): `Convert.ToInt32`.
- `online`: `Convert.ToBoolean`, not direct bool unboxing. Existing `"true"`/`"false"` strings are compatible, including .NET's case-insensitive True/False spelling. JSON booleans are also compatible. Do not report string booleans as a proven breakage.
- `donation_request` exists as a metadata key constant but has no branch in this build's friend dictionary parser. A per-friend SQL JSON string/null is ignored here; it does not justify expanding this task into donations.

Top-level donation fields are distinct: `DonationRequestResponse` is `morty_id` string/null, `next_countdown` float, `donation` nullable `MPFriendData`. The refresh method dereferences the object unconditionally, so preserve an object such as `{"morty_id":null,"next_countdown":0,"donation":null}` even without donation support.

The client has no knowledge of `player_id_a`/`player_id_b`, reciprocal rows, SQL pending strings, uniqueness indexes, row ownership, or transactions. Using one row with A=sender and B=recipient is a replacement-server policy. Enforce only the recipient can approve/reject an incoming pending request, and only participants can remove their relationship; those are server authorization invariants that implement the UI direction, not recovered native SQL rules. Accepted friendship appears for both participants regardless of row orientation. Sent requests appear as pending friends and can use the remove flow; receiving a request does not authorize accepting an outgoing one.

The remove confirmation handler `0x15a1938` forwards the selected friend data to `Remove` without testing `isPending`; the HTTP producer likewise has no pending/accepted branch. There is no distinct native cancel-request endpoint in this contract. Cancellation can remove an outgoing pending relationship through `remove`; incoming rejection uses `response` with `approve:false`.

## Capacity and updates

`IsFriendListFull` (`0x1791ef0`) compares `friends.Count >= friendListLimit`; refresh assigns `friendListLimit` from `limit_friends` at `0x178fa00`. Because sent requests live in `friends`, this UI count includes sent pending rows. There is no hardcoded native 30 established by these methods. Returning/enforcing 30 retains the replacement server's existing advertised policy; do not label 30 as an independently recovered original-server constant, or infer original server pending-count rules from the UI check.

`MPFriendState.NetFriendRefreshDataSuccessHandler` (`0x15a1afc`) cancels the previous `RefreshFriendData` invocation and calls `InvokeRepeating` with delay and repeat interval equal to response `poll_period`. `RefreshFriendData` (`0x15a0538`) calls `NetworkFriendAPI.RefreshData`. The existing period 5 therefore gives five-second UI polling. Response/remove also refresh immediately. `NetworkFriendAPI.Connected` (`0x178ee00`) registers SSE handlers for donation/trade events, not friend request/accept/reject/remove events. No new friendship SSE event is required by these recovered lifecycle methods. Battle invitation/combat transport is a separate contract and is not implemented or inferred here.

## Errors

`ParseHTTPError<Int32Enum>` (`0x1b569d8`) tests HTTP-response success before inspecting a body. On an unsuccessful response it reads dictionary `error`, then string `code`, checks `Enum.IsDefined`, and parses the matching enum name. Compatible shape: `{"error":{"code":"PLAYER_ID_INVALID"}}` with an unsuccessful HTTP status. A flat error string, numeric code, or made-up name does not select the intended friend error. Exact native typo: `UNKOWN`, not `UNKNOWN`. Missing/malformed error data does not provide a useful specific UI error.

| Enum | Exact values |
| --- | --- |
| `eFriendRefreshDataError` | `UNKOWN=0`, `FAILED=1`, `NONE=2` |
| `eFriendSearchForUserError` | `UNKOWN=0`, `FAILED=1`, `QUERY_INVALID=2`, `NONE=3` |
| `eFriendSendRequestError` | `UNKOWN=0`, `FAILED=1`, `PLAYER_ID_INVALID=2`, `FRIEND_DUPLICATE=3`, `FRIEND_LIMIT_SELF=4`, `FRIEND_LIMIT_OTHER=5`, `NONE=6` |
| `eFriendRespondToRequestError` | `UNKOWN=0`, `FAILED=1`, `PLAYER_ID_INVALID=2`, `APPROVE_INVALID=3`, `FRIEND_LIMIT_SELF=4`, `NONE=5` |
| `eFriendRemoveError` | `UNKOWN=0`, `FAILED=1`, `PLAYER_ID_INVALID=2`, `NONE=3` |

`ParseHTTPResponse<Int32Enum,object>` (`0x1b572a4`) first invokes that error parser, then deserializes a successful body into the requested DTO. List/search require that typed path; request/response/remove do not. Friend enums lack `NO_RESPONSE` and `INVALID_RESPONSE`; parser fallback behavior must not be represented as newly discovered endpoint-specific error names.

## Implementation boundaries

Confirmed compatibility requirements are request field spelling/types, direction of list projection, nonnull top-level donation object, poll period, and structured native error codes. Correcting relationship races, ownership, duplicate handling, and atomic limits requires ordinary server-side consistency work; native evidence establishes visible outcomes, not a particular SQL implementation. Preserve working ConspiracyRick account behavior and existing successful bodies. No account writes, live relationship mutation, runtime deployment, or friend-battle combat behavior was used to obtain this contract.
