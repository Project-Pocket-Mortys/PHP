# Friend battle preparation deadlines

This slice extends the [shared membership foundation](shared-battle-membership.md)
from prerequisite PR #40, based on main `9ff1a11` and its dependency history.
The prerequisite head is `16c0a76`.
Deadlines, cancellation reasons and worker behavior are replacement-server policy.
The [recovered client contract](friend-battle-start-contract.md) does not establish
an original-server preparation lifetime or storage layout.

Public invitation acceptance remains HTTP 501. These internal helpers do not
implement startup, immutable party snapshots, readiness, reconnect recovery or
human combat, and do not publish accepted or `battle:start` events.

## Schema and deployment

Apply `tools/research/server/migrations/008-friend-battle-preparation-deadline.sql`
after migrations 006 and 007 and before deploying this code. The base SQL dump
alone is insufficient. The migration adds `prepare_deadline DATETIME(6) NULL` and
`cancel_reason VARCHAR(32) NULL` to `friend_battle_sessions`, plus the
`prepare_due (state, prepare_deadline, battle_id)` index. It retains the existing
battle and invitation identities and the one-claim-per-player membership table.

Historical sessions retain a NULL deadline: the migration does not invent a lease
for an existing reservation. Automatic cleanup preserves these rows and their
claims. Reservation replay rejects an unknown deadline; explicit authenticated
internal cancellation remains available for a valid historical reservation.
Explicit cancellation records `USER_CANCELLED`; terminal replay preserves the
existing reason.

## Reservation and cancellation policy

New reservations persist a UTC database-clock deadline in the same transaction as
the session and its two membership claims. The default lifetime is 30 seconds.
`PM_FRIEND_BATTLE_PREPARE_SECONDS` accepts an integer from 10 through 120; invalid
configuration fails without committing a partial reservation.

Replay returns the existing battle identity only while its persisted deadline is
known and strictly in the future, and all existing eligibility, invitation and
exact-two-claim checks pass. It never extends the deadline. A due or NULL deadline
fails replay without implicitly deleting claims. A cancelled identity cannot be
reserved again through the same invitation.

Cleanup changes only the preparation session and its exact two matching claims.
It marks the session `CANCELLED`, records a durable reason and updates its timestamp
in the same transaction as claim deletion. It does not alter user state, invitation
state, legacy battles, wild spawns, inventories, parties, progression or event
queues. Repeated cancellation preserves the terminal result, including its reason,
and cannot release claims belonging to a newer reservation.

Only `PREPARING` sessions with a non-NULL deadline are eligible. Cancellation uses
`PREPARATION_TIMEOUT` when the persisted deadline is at or before the database
clock. Otherwise a closed, missing or expired invitation causes `INVITE_CLOSED`,
and an absent or no-longer-accepted friendship causes `FRIEND_REMOVED`. These last
two conditions can cancel a preparation before its own deadline. Ambiguous or
malformed friendship data preserves the reservation instead of guessing a reason.
The worker does not mark the invitation expired or revoked itself.

## Worker and locking boundary

`lib/friend_battle_preparations.php` exposes bounded global and per-player cleanup
operations. Candidate reads supply hints only. Each attempt owns its transaction,
locks both unambiguous user rows in sorted player-ID order, locks and revalidates
the exact session, then reads the invitation and validates exactly the expected
two claims before deleting either claim. Changed identities, duplicate users,
ambiguous friendship rows or missing, redirected or extra claims fail closed.
An invalid candidate is preserved rather than repaired speculatively.
The global sweep visits non-NULL preparations by battle ID with a continuation
cursor, including future deadlines so closed invitations and removed friendships
can be handled promptly. The per-player scan orders by deadline and battle ID.

All reservation, explicit cancellation and worker paths acquire both user locks
before locking or changing a session, invitation or claim. Reservation's invitation-before-
session lookup and cleanup's session-before-invitation lookup are serialized by
those common user locks for the same validated pair. A candidate must never
redirect work to another participant pair after acquiring its hinted locks.

The worker is standalone. It must not run inside a world-action guard or any
transaction already holding one user's lock: acquiring the second user there
could violate sorted pair order. Existing guards continue to treat every
unreleased claim as busy, including historical or malformed claims.

## Scheduling and remaining boundary

The optional isolated research CLI at
`tools/research/server/friend-battle-preparations.php` supports `--once` for one
bounded sweep. Its loop supports disconnected participants. A bounded invocation
is not proof that every eligible row has been processed; continued scheduling is
required.
The loop retains its cursor across batches; separate `--once` processes do not.
Use the continuous worker to cycle fairly past preserved corrupt candidates,
rather than assuming repeated one-page invocations cover every record.

```powershell
docker compose -f compose.research.yaml exec -T web php tools/research/server/migrate.php
docker compose -f compose.research.yaml exec -T web php tools/research/server/friend-battle-preparations.php --once
docker compose -f compose.research.yaml --profile friend-battle-preparations up -d friend-battle-preparations
```

The profile is disabled by default. No background service was deployed during
this milestone; the CLI test used a bounded invocation against UUID fixtures.

SSE performs bounded per-player cleanup at most once per second before its global
invitation event poll, including while waiting for a room. This occurs outside the
room/world transaction and does not introduce a preparation event. Cleanup errors
preserve claims; invitation delivery still applies its existing eligibility and
session checks. A reconnect or CLI sweep can retry preserved candidates.

Deadline cleanup removes one prerequisite for eventual acceptance. Authoritative
snapshots, incompatible-writer coverage, both participant transitions, private
start delivery, readiness and reconnect recovery still require separate work.
No native UI activation or playable friend battle follows from these internal
database operations.

## Verification

Thirteen deadline/cleanup cases passed in 69.374 seconds, and three SSE/CLI
integration cases passed in 16.683 seconds. Fifty-two existing membership,
shared-guard, invitation HTTP/SSE, session-revocation and privacy cases passed
in 187.833 seconds: 68 distinct checked cases in total. Fixtures use fresh UUIDs
and clean up their own records and fault triggers without reseeding accounts.

Coverage includes strict configuration bounds, unchanged replay deadlines,
legacy NULL preservation, stale candidate identities/deadlines, closed or missing
invitations, friendship removal, malformed claim preservation, rollback after
claim deletion, newer reservations and fair sweep pagination. The roomless SSE
test releases a due preparation before projecting its pending invitation; a
revoked stream cannot release a newer preparation, while the current stream can.
The CLI cleanup path and its HTTP non-CLI rejection were also checked.

Migration 008 passed twice on a schema-only copy of the current research
database, including an existing PREPARING row whose new fields remained NULL.
The index was verified before application to the isolated backend. PHP 8.3 lint
passed for all 46 changed/new PHP files including dependencies; Compose, Python,
protocol/source and whitespace checks passed.

Final cleanup left no shared sessions or memberships. The original two-account
save/friend/battle/event/invitation guard and independent HP/AP/item/deck/
progression guard passed. No real client was reserved, no new native battle UI
was activated, and public acceptance remains unavailable. No deployment is
included.
