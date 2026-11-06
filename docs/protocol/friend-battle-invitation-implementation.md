# Friend battle invitations

This change implements invitation send, decline, revoke and expiry for accepted
friends. It does not implement a playable human battle. A recipient's valid
`accept:true` request returns HTTP 501 with `{"error":{"code":"FAILED"}}`.
It does not create a battle, reserve either player, publish `battle:start` or
`battle-invite:accepted`, change user state, or spend gameplay resources.

The [native invitation contract](friend-battle-invite-contract.md) establishes
the routes, request and response fields, event DTOs, `PvF` spelling, error enum
names, client countdown units and reconnect behavior. The
[battle start contract](friend-battle-start-contract.md) explains why an
accepted notification alone cannot start a safe human battle. Neither document
recovers the original server's token, storage, authorization, expiry, replay,
rate limit or matchmaking policies. The choices below are replacement policies.

## Required schema and configuration

Apply `tools/research/server/migrations/006-friend-battle-invitations.sql` before
running these routes or the SSE server. It adds the InnoDB
`friend_battle_invites` table with invitation identity, direction, two private
tokens, lifecycle state and microsecond UTC timestamps. It does not modify the
base battle schema or reserve player membership. The repository's base SQL dump
alone does not supply this table. A missing migration causes invitation HTTP
operations to fail with a generic error and invitation SSE polling to close the
connection; it does not fabricate successful delivery.

`PM_FRIEND_INVITE_TTL_SECONDS` defaults to 60 seconds when absent or empty. A
configured value must be an integer from 10 through 300 inclusive; an invalid
value fails creation rather than silently choosing another lifetime. Expiration
uses the database UTC clock. Wire `battle_invite_ttl` is a numeric number of
remaining seconds, suitable for the native relative countdown. The server does
not interpret it as an absolute timestamp or trust a client-supplied lifetime.

Terminal records are retained in the table. SSE's short delivery window is not a
database cleanup job. This change adds no background deletion or global quota.

## HTTP lifecycle and replacement policies

All three endpoints require POST and a JSON body. Responses use JSON and
`Cache-Control: no-store`.

| Route | Required fields | Successful result |
| --- | --- | --- |
| `/session/battle-invite/create` | String `session_id`, string `opponent_player_id`, exact string `battle_type:"PvF"` | HTTP 200 with `battle_invite_id`, `battle_type`, numeric `battle_invite_ttl`, sender `token` |
| `/session/battle-invite/response` | String `session_id`, string `token`, boolean `accept:false` | HTTP 200 with `{"success":true}` |
| `/session/battle-invite/revoke` | String `session_id`, string `token` | HTTP 200 with `{"success":true}` |

Creation requires one accepted friendship row in either orientation. Missing,
pending, duplicated or malformed relationships fail closed. Both players must
be `WORLD`, and neither may appear in either participant column of an `ACTIVE`
battle. This is an eligibility check, not a reservation: the invitation does
not prevent later world or battle actions. Co-location in a room is not
required.

Each sender may have one pending outgoing invitation. Repeating create for the
same recipient reuses its ID and sender token and returns its remaining TTL.
An outgoing invitation to a different recipient returns `SENT_INVITE_PENDING`.
Incoming invitations and crossed invitations are allowed by this server;
the native client separately auto-declines incoming invitations during some
send and response flows. Expired pending outgoing records are marked
`EXPIRED` when the sender creates again, allowing a new ID and tokens. A record
that has expired at the locked sender's pending lookup is also replaced; it is
not returned with an initial zero or negative countdown.

Each invitation uses a random version 4 UUID and independent sender and recipient tokens, generated from
32 random bytes and encoded as 64 hexadecimal characters. The create response
discloses only the sender token; the recipient event discloses only the recipient
token. A token alone grants no authority: the authenticated account must match
the persisted role, and the supplied token must equal that role's token.
Response is recipient-only; revoke is sender-only. Unknown tokens return
`TOKEN_INVALID`, while a known token used by the wrong account or role returns
`TOKEN_NOTVALID`. These are the exact native spellings.

Decline changes `PENDING` to `DECLINED`; revoke changes it to `REVOKED`.
Repeating the same terminal operation succeeds without updating the row again.
The opposite terminal operation fails with `TOKEN_NOTVALID`. An expired pending
invitation is persisted as `EXPIRED` and returns HTTP 410 `TOKEN_EXPIRED`;
already expired records return the same error. Matching decline/revoke retries
against their completed terminal state remain successful after the original
deadline. That idempotency is a replacement policy, not recovered server behavior.

Acceptance remains unavailable. After token and expiry checks, `accept:true`
against a pending invitation returns HTTP 501 `FAILED` without transitioning
the row. Against a declined or revoked invitation it returns HTTP 409
`TOKEN_NOTVALID`. The native response
callback consumes an error, not a playable battle from the HTTP response body.
The client removes its selected incoming invitation before sending the request,
so an unsuccessful acceptance need not leave that invitation visible locally;
a fresh session stream can reconstruct a still-pending invitation.

Session failures retain HTTP 401 and map to native enum members:
`SESSION_ID_INVALID` for create and `FAILED` for response/revoke. Invalid boolean
acceptance uses `ACCEPT_INVALID`. Unexpected exceptions roll back transactions
and return a generic `FAILED` without SQL details or tokens.

## Concurrency and friend removal

Invitation writers reuse `friend_lock_pair`: authenticate the session, lock both
user rows in sorted player-ID order, then revalidate authentication and read the
relationship. The token lookup before those locks is a hint; reply operations
lock and reread the invitation before applying a transition. Concurrent sends
from one sender therefore serialize even when their recipients differ. Same
recipient retries reuse one record, and decline/revoke races produce one terminal
result. These guarantees depend on cooperating writers using the same user locks.
Pending lookups avoid range/gap locks and transitions update exact invitation
IDs, allowing unrelated senders to create concurrently.

Friend removal calls `friend_battle_invite_remove_pair` in the same transaction
as deleting the relationship, while holding both user locks. It changes pending
invitations in both directions to `REVOKED`, or `EXPIRED` when their deadline
has already elapsed. Removing and re-adding friendship
does not reopen those records. A failure rolls back the relationship deletion
and invitation changes together. Reply operations permit authorized terminal
cleanup without requiring the friendship still to exist.

## Private global session events

`lib/friend_invite_stream.php` reads durable invitation records directly for the
authenticated subscriber. `sse/index.php` polls it after `session:start` and in
both roomless and room-attached loops. Invitation delivery does not depend on a
room cursor, enter the public room event queue, or advance room event IDs.
The invitation helper does not mutate invitation or gameplay state.

Only the recipient receives `battle-invite:received`. Its payload contains
`battle_invite_id`, `battle_type:"PvF"`, remaining `battle_invite_ttl`, the
recipient token and `from_player`. The public sender profile includes only
`player_id`, `username`, `player_avatar_id` and numeric `level`; it contains no
save, inventory, party, session or sender token. Third accounts receive no
invitation record. Authentication is checked before and after each poll, and
revoked or ambiguous sessions close the stream without a fabricated event.

Before emitting a pending received event, the helper checks both players'
`WORLD` state, absence of an active battle in either participant column, and the
single accepted friendship. Invalid eligibility suppresses new received delivery
without synthesizing a terminal event. Expired or persisted terminal invitations
produce ID-only removal events: `battle-invite:declined` for the sender and
`battle-invite:revoked` for the recipient. These event names clear the respective
native UI state; the payload does not disclose tokens or a terminal reason.

Native received handling appends without deduplicating. The server therefore
emits a pending received event once per connection and invitation ID. A fresh
connection starts a new deduplication map and reconstructs eligible pending
invitations with their remaining lifetime. This is connection-local delivery,
not an acknowledgement protocol or a durable replay cursor. Native reconnect
clears the client's local invitation state before registering handlers again.

Native create completion installs the sender's invitation ID asynchronously.
A terminal event can arrive before that callback and be ignored. To reduce that
race, ID-only terminal events repeat at most once per second per invitation
per connection. Delivery ends five seconds after the later of invitation
expiration or its most recent persisted update. This bounded repeat and
five-second grace period are replacement policies. Native terminal handlers
ignore IDs they no longer hold. There is no guaranteed HTTP/SSE acknowledgement
barrier; a callback delayed beyond the retained window remains a limitation.

Expiry on SSE is effective and read-only: an elapsed `PENDING` record produces
removal events without requiring a worker to persist `EXPIRED`. The HTTP paths
perform persistent expiry transitions when they encounter the record. Temporary
eligibility failures do not persist a terminal transition or clear an invitation
already delivered to a client. Delivery can resume when eligibility returns;
the once-per-connection received guard still applies. Friend removal persists
revocation, so re-adding the friendship cannot revive an old invitation.

## Verification

`tests/protocol/test_friend_battle_invites.py` covers HTTP lifecycle,
authorization, expiry, replay, eligibility and rollback with isolated UUID
fixtures. `tests/protocol/test_friend_invite_stream.py` covers private delivery,
reconnect, terminal repeat bounds, effective expiry, session checks and roomless
SSE. Eighteen distinct HTTP cases passed across the 13-case run (38.761 seconds),
five targeted checks including one repeated concurrency case (8.098 seconds),
and the slashless POST/GET case (2.458 seconds). Seven SSE cases passed in
34.184 seconds. Twenty-five existing friend/session/privacy/snapshot/rejoin
regressions passed in 108.690 seconds: 50 distinct checked cases in total.

Coverage includes both-role token isolation, unavailable acceptance, expiry,
replay, unrelated and same-sender concurrency, friend-removal races, and injected
insert/update failures. A late invitation-update failure rolls back both friend
removal and the invitation transition. Slashless native POSTs retain their JSON
body without a redirect, and GETs fail cleanly. Fixtures use only fresh UUIDs
and are cleaned after each test; no account reseeding is performed.

Migration 006 was applied twice to a separate schema-only copy of the current
research database, with columns and indexes verified, before application to
the isolated backend. The copy and original schema dump remain ignored for
inspection. PHP 8.3 lint passed for all 42 changed/new PHP files including
dependencies. Native UI results are recorded in
[Android invitation acceptance](android-friend-battle-invitations.md).
Both native flows passed: primary send → peer decline and primary send →
sender cancellation, with four HTTP 200 requests and corresponding waiting,
incoming, declined and cleared UI states. Separate authenticated observers
verified private role-specific events; these are explicitly additional session
streams, not captures of the apps' SSE sockets. No accepted or start event was
emitted. Guarded cleanup removed only the fresh friendship and two tracked
terminal invitation rows. After fresh reloads, both clients showed empty friend
lists and returned to WORLD. The companion, original friend/save and independent
gameplay guards passed again, including an integrator check.

This branch starts from main `9ff1a11` with pending prerequisite PR #38 at
`1d9ad66` and its dependency history. README-completed features and attribution
are retained. No deployment is included.
