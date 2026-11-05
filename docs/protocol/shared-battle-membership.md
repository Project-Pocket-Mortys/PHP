# Shared friend-battle membership foundation

This branch builds on main `9ff1a11`, prerequisite PR #39 at `e73b96e`, and its
dependency history.

This slice adds an internal database reservation foundation. It does not enable
friend-battle acceptance or playable human combat. The public invitation response
route still returns HTTP 501 for a valid pending acceptance. No route invokes the
new reserve/cancel helpers, changes either user to `BATTLE`, emits `battle:start`
or accepted events, or applies gameplay writes through this foundation.

The recovered [invitation contract](friend-battle-invite-contract.md) and
[start/readiness contract](friend-battle-start-contract.md) establish client
requirements, including `PvF`, separate participant perspectives, real owned
parties, readiness requests and private start delivery. This schema and its
reservation/cancellation behavior are replacement-server design choices. They
are not recovered original-server storage or policy.

## Storage and deployment dependency

Migration `007-shared-battle-membership.sql` is additive and follows migration
`006-friend-battle-invitations.sql`. The application requires the new tables before
deploying code that consults membership; a missing table fails closed through the
existing request error paths. The base SQL dump alone is insufficient.

`friend_battle_sessions` retains a durable battle identity, unique invitation
identity, the invitation's sender and recipient, and `PREPARING` or `CANCELLED`
state. `friend_battle_memberships` gives each player one primary-key claim pointing
to the shared battle. Both sides use the same table and invariant; uniqueness
prevents a player from occupying either side of two reservations. The session is
separate from legacy `battles` and does not create a playable battle there.

Cancelled session identity remains available for replay. Cancellation releases
only claims belonging to that session. Replaying an old cancellation must never
delete a participant's newer reservation. Orphaned or malformed membership rows
still block the guarded actions; the guard does not infer that a claim is safe to
ignore from a missing or terminal session.

## Locking and internal helper boundary

`lib/friend_battle_membership.php` provides standalone internal
`friend_battle_reserve` and `friend_battle_cancel_reservation` operations. Pair
locking reuses `friend_lock_pair`: authenticate an unambiguous session, lock both
user rows in sorted player-ID order, then revalidate session ownership after any
wait. An unlocked identity lookup supplies a lock target, never final authority.
Reserve binds the recipient's session and recipient token to the persisted
invitation role. Cancellation authenticates either persisted participant.

The common order is both users first, then the relevant invitation/session record,
then membership claims. Reservation must persist the session and both claims in
one transaction, and rollback leaves neither participant partially reserved.
Duplicate reservation returns the persisted identity rather than making another
session only while the invitation remains `PENDING` and unexpired, both users
remain eligible accepted friends in `WORLD`, and neither appears in either
participant column of an `ACTIVE` legacy battle. These checks run before returning
an existing `PREPARING` identity. Claim validation queries all rows for that battle
and requires exactly its two expected participants; missing, redirected or extra
third-party claims fail closed without speculative repair.

Reservation leaves invitation state unchanged. Invitation decline, revoke and
expiry therefore prevent reservation replay but do not themselves release an
existing preparation's claims. That preparation requires explicit internal
cancellation. Cancellation durably marks `CANCELLED` and releases matching claims
in one transaction. Its replay preserves the terminal result and future claims.
The helpers commit successful calls and roll back failed calls.

These helpers own their transaction boundary and are not public endpoint
handlers. A future acceptance integration must preserve their lock order while
adding all remaining lifecycle invariants; calling them from the current
invitation reply transaction is not a safe integration by itself.

## Guard coverage and limits

`battle_has_shared_membership` checks any player claim. The existing world action
guard consults it before legacy battle reconciliation, covering heal, join-room,
leave-room, shiny-potion use and Morty absorption. Wild-battle start checks it
while holding the user's row lock. Invitation creation treats either participant
as busy when claimed, and the invitation stream suppresses newly eligible pending
delivery while either participant is claimed. Stream suppression is read-only;
it does not durably cancel an invitation or promise a synchronized notification.

The mutating guard callers hold the user lock, which serializes them against
reservation and cancellation. This is bounded coverage, not a claim that all
roster, deck, trade, inventory or session writers are protected. Those writers
still need an audit before participant snapshots or public acceptance are safe.
Legacy wild battle access, readiness, turn resolution and terminal reconciliation
remain distinct from this new session storage.

## Work required before acceptance

There is no automatic preparation lease, deadline worker or reconnect recovery in
this slice. A committed internal `PREPARING` reservation can therefore persist
until explicit internal cancellation. This is acceptable only for an unexposed
foundation; public acceptance remains blocked.

Before acceptance can become available, implement and verify:

- A durable preparation/startup deadline and cleanup path that competes safely
  with startup, cancellation and retries under the same user locks.
- Authoritative immutable party snapshots, full incompatible-writer coverage,
  both user transitions and atomic private start views with the same battle ID.
- Participant-specific readiness, reconnect reconstruction and durable delivery
  recovery, including cross-room and third-account privacy checks.
- Shared cancellation and terminal cleanup for both users, without touching wild
  spawns or releasing claims belonging to a newer session.

Human turn pairing, combat rules, turn deadlines, surrender and reward behavior
remain subsequent work described in [server gaps](friend-battle-server-gaps.md).
Database fixture tests can establish reservation invariants; they cannot establish
native UI activation or a playable friend battle while the feature is unexposed.

## Verification

Thirteen internal reservation cases passed in 54.042 seconds; the corrected
claim-corruption case also passed independently in 5.371 seconds. Five shared
guard cases passed in 40.835 seconds. Fifty-two existing wild-battle lifecycle,
world guard, invitation HTTP and invitation SSE cases passed in 118.243 seconds:
70 distinct checked cases in total. All fixtures use fresh UUIDs, with no reseeding.

Checks include overlapping and duplicate reservations, role/session validation,
expired or revoked invitation replay, exact two-claim integrity, second-claim
insertion rollback, cancellation-update rollback, either participant cancellation,
and stale cancellation preserving a newer reservation. Both participants' guarded
world/wild/invitation actions are rejected without gameplay mutations; normal
actions work again after cancellation. Legacy opponent-side ACTIVE claims are
also respected. No public acceptance endpoint was enabled or exercised as success.

Migration 007 passed twice on a separate schema-only copy of the current research
database, with columns and indexes checked, before application to the isolated
backend. The dump and schema copy remain private. PHP 8.3 lint passed for all 44
changed/new PHP files including prerequisites; protocol/source/Python checks pass.
World guard and wild-start files use LF for reproducible source fingerprints;
the wild-start behavior diff is limited to the membership check and both-side
legacy claim lookup.

Final cleanup left no shared sessions or memberships. The existing two-account
save/friend/both-side battle/event/invitation guard and independent HP/AP/items/
deck/progression guard passed. No real client was reserved or given new battle
UI; prior native invitation evidence remains separate from these internal tests.
