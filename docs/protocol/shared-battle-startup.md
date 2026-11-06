# Internal shared battle startup

Follow-up: [research delivery](shared-battle-stream-delivery.md) and
[Android startup captures](android-shared-startup.md) extend the original internal
scope below. Migration 013 now adds [first ATTACK storage/pairing](paired-selection-contract.md);
[two native inputs, waiting and expiry recovery](android-paired-selection-results.json)
are verified on the dedicated registration parties.

This adds atomic startup bookkeeping after the [private start views](private-battle-start-views.md).
It does not enable public acceptance or publish native events. The
[bounded Android review](shared-battle-startup-contract.md) establishes native
readiness and disconnect behavior; the storage, fixed lease and cleanup below
are explicit replacement-server policy. No original combat formulas, rewards or
disconnect adjudication are inferred.

## Lifecycle and privacy

`friend_battle_startup_activate` accepts the authenticated invitation recipient
only. Under ordered participant locks it checks the current session, accepted
friendship, live preparation/invitation, exact claims, absence of conflicting
legacy battles, stored view hashes/schema, current profile/inventory and current
party against the frozen source. Malformed or changed source fails without
recapturing it. Existing private-view capture retains its immutable replay policy;
the extra current-party check belongs to the activation boundary.

One transaction creates the startup record and two recipient-specific start
intents, marks both users BATTLE, marks the invitation ACCEPTED and moves the
shared session from PREPARING to STARTING. Both intents have stable unique
delivery IDs and hashed payloads identical to each recipient's stored view.
Failed insertion or either user transition rolls the entire operation back.
Preparation/invitation deadlines are checked again at the transition, so a lease
that expires during validation or insertion cannot produce a successful start.

Activation retries return the current STARTING/READY state and original deadline.
They do not recreate intents or renew the lease. The trusted internal
`friend_battle_startup_intent` getter returns only the authenticated participant's
delivery ID and payload. It rechecks claims, lease and record integrity; third
accounts, expired sessions and retired startups cannot retrieve it. This is not
a native reconnect route or an SSE replay implementation.

`friend_battle_startup_ready` records each participant's first animation-ready
signal once. The internal result's `ready` boolean describes the shared barrier:
false until both are recorded, then true with session state READY. Duplicates and
concurrent readies preserve the first timestamps and fixed deadline. The final
lease check occurs after writes, preventing a slow request from committing
readiness after expiry. No timer event or human turn is started. The public
legacy ready endpoint remains separate by default and rejects these shared
battle IDs. The opt-in research transport connects native initial ready handling.
After its own initial ready signal, each participant may submit one immutable
[first ATTACK selection](paired-selection-contract.md), including while the peer
intro is still running. A complete pair requires READY and both ready signals;
it leaves this fixed startup lifecycle in place without resolving a turn.

`PM_FRIEND_BATTLE_STARTUP_SECONDS` defaults to 30 and accepts only integers in
10..120. The database clock sets the lease. It remains bounded through READY
until a future gameplay handoff exists; reaching the barrier never creates an
indefinite reservation. The native 180-second watchdog is a separate client
behavior and does not establish this server policy. Nullable or contradictory
historical deadlines fail closed rather than being guessed or backfilled.

## Cancellation and expiry

Either participant can call internal `friend_battle_startup_cancel`. Under the
same locks it validates the active shared identity, restores both users to WORLD,
deletes exactly their matching claims, retires both start intents and marks the
session CANCELLED with STARTUP_CANCELLED. The accepted invite, frozen views and
party snapshots remain history. Both user transitions explicitly preserve
`last_seen`: startup and worker cleanup must not fabricate player activity.
Inventory, HP/AP, progression, currencies, room membership and wild spawns remain
unchanged. There is no invented native terminal outcome or reward.

A terminal retry authenticates the old participant but does not release newer
claims or rewrite current users. Corrupt/partial active claims or intents fail
closed. Cleanup failures roll back both state changes, both claim deletions and
intent retirement together. Migration 013 extends this same transaction to retire
any first selections and their pair, retaining their history. Selection retirement
also runs from the ordinary gate-off worker and fails atomically with cleanup.

The bounded keyset sweep covers STARTING and READY. Candidate IDs are hints;
ordered user/session locks and current identity/deadline checks decide expiry.
It uses STARTUP_TIMEOUT and the same atomic cleanup. Stale, duplicate, foreign,
future or malformed candidates cannot release unrelated or newer claims. The
cancelled record retains its deadline for history; CANCELLED is excluded from
all active sweeps and ready/intent operations.

The optional isolated CLI runs manually; no service is started automatically:

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/friend-battle-startups.php --once
```

Without `--once` it loops over bounded batches. It requires CLI and the isolated
research database environment; HTTP is denied by Apache (403) or its own PHP
guard (404). The existing preparation
worker still handles only PREPARING and cannot expire active startup records.

## Schema and reproduction

Migration 011 adds `friend_battle_startups` and `friend_battle_start_intents`.
The former has one row per shared battle; the latter enforces one recipient row
per battle and globally unique delivery IDs. Both are additive InnoDB tables.
The original SQL dump and existing save data are retained.

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/migrate.php
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_friend_battle_startup.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_friend_battle_start_views.py -v
```

Run database fixtures serially. These suites create and clean their own UUID
accounts and scoped fault triggers. Unrestricted discovery includes older save
reseeding fixtures and is unsuitable for retained emulator accounts.

Migration 011 passed twice on a schema-only copy before isolated application;
both primary keys and delivery-ID uniqueness were checked. Nineteen startup
scenarios passed: the full run completed 18 cases in 202.915 seconds, with the
remaining CLI/HTTP case passing in a focused 6.775-second rerun after its
expectation was corrected to the existing Apache 403/PHP 404 policy. The suite
covers both roles, privacy, replay, concurrency, malformed source and deadlines,
configuration bounds, slow-write expiry, newer claims, fault rollback and worker
cleanup. State-transition comparisons include the unchanged `last_seen` value.

The 46 existing start-view, reservation, preparation deadline/SSE and shared-guard
regressions also passed in 357.175 seconds, giving 65 distinct verified cases.
PHP 8.3 lint passed all 62 changed/new PHP files including prerequisites;
protocol/source hashes, Python syntax, bounded native evidence and whitespace
checks passed. Both original two-account guards passed, covering complete
save/friend/battle/event/invitation state and independent HP/AP/items/decks/
progression/membership. Final cleanup left zero sessions, claims, party snapshots,
private views, startups and intents. No original save was reset or reserved.

This branch starts from current main `9ff1a11`, explicitly fast-forwarding
prerequisite PR #43 at `900d598` and its dependency history. Public invitation
acceptance remains 501 FAILED; startup helpers have no HTTP route or SSE
dispatcher. No actual Android start, production deployment or playable human
battle is claimed.

## Next missing feature dependency

Authenticated delivery must recover the correct recipient start across rooms
and fresh connections without duplicate starts resetting the client. Native
disconnect clears local battle state; the reviewed client handlers do not
establish a human resume/cancellation protocol. Resolve safe transport-loss
presentation and abort delivery before publishing these intents. A private
startup ledger and ready barrier alone do not provide that client lifecycle.

First human selections now have an immutable research ledger. Later-phase ready
retry identity, turn resolution,
forced switches, surrender and rewards remain separate. Keep the existing
owner/spawn-specific wild handlers intact rather than relaxing their checks.
