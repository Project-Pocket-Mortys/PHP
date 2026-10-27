# Same-room rejoin membership generation

This follow-up repairs the rapid same-room rejoin limitation recorded in
[SSE room transitions](sse-room-transitions.md). The repair establishes consistent
replacement-server behavior; original-server rapid-rejoin delivery semantics
remain unknown. No event names, SSE framing, or HTTP response payload fields were
added by the generation repair.

## Failure and repair

Previously, the stream adopted `users.last_event_id` only when the observed room
changed. A leave and rejoin to the same room entirely between stream polls left
the local cursor on its previous baseline. The stream replayed events already
covered by the new join baseline. A stale cursor write could also overwrite that
baseline because its session and room predicates still matched.

`users.room_membership_generation` now identifies successive memberships. Join
increments it in the SQL statement that installs room membership and its event
baseline. An actual leave increments it in the existing transaction that clears
membership and publishes departure. Repeated leave outside a room does not
increment it. Every join increments it, including a direct join to the same room.

The stream captures generation when waiting for initial membership, checks room
and generation during each poll and before each snapshot/queued event, and
adopts the current baseline when either changes. Every cursor write, including
fresh-connect and explicit-resume initialization, includes generation in its
predicate. Generations are compared as decimal strings to preserve unsigned
BIGINT values above PHP's signed integer range.

## Migration and deployment order

Migration `002-room-membership-generation.sql` adds one column:

```sql
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS room_membership_generation BIGINT UNSIGNED NOT NULL DEFAULT 0;
```

Apply it **before deploying the updated PHP handlers**. Existing accounts start
at generation zero; existing account fields, session credentials, memberships,
and event cursors are preserved. The original `pocket_mortys.sql` dump is unchanged.
The existing research runner applies ordered migrations repeatedly:

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/migrate.php
```

The verified database is `10.11.19-MariaDB-ubu2204`; the Compose stack pins the
MariaDB 10.11 image. `ADD COLUMN IF NOT EXISTS` is MariaDB syntax used here for
repeatability. Portability to other database engines or MySQL versions is not
asserted; deployments outside this stack must provide an equivalent migration
through their own migration mechanism. The research runner intentionally refuses
non-research database configuration. No web restart was performed as part of
this repair; already-running SSE PHP requests continue executing their loaded
code until they end and clients reconnect.

## Reproduce migration validation

```powershell
py -m unittest discover -s tests/protocol -p test_room_membership_migration.py -v
```

The test opens a dedicated database connection and creates
`TEMPORARY TABLE generation_fixture LIKE users`. It drops the generation column
from that temporary copy if already installed, inserts only synthetic rows, and
substitutes the migration's single `ALTER TABLE users` target with
`ALTER TABLE generation_fixture`. The SQL column definition is otherwise the
checked-in migration. This is a temporary-copy validation, not an execution of
the unchanged migration against a temporary table named `users`.

It verifies generation zero on existing rows, the unsigned/non-null/default
column definition, and preservation of every prior synthetic row field. It then
sets a generation above `PHP_INT_MAX`, reapplies the migration, and verifies all
data including the nonzero generation are preserved. The live `users` column
metadata is compared before and after. The temporary table is dropped in
`finally`; no live account rows or production schema are changed by this test.
The initial ad hoc temporary-copy validation passed before the actual research
migration was applied through the runner; this test makes that procedure
repeatable after installation too.

## Regression evidence and scope

```powershell
py -m unittest discover -s tests/protocol -p test_sse_rejoin_generation.py -v
py -m unittest discover -s tests/protocol -p test_sse_rooms.py -v
py -m unittest discover -s tests/protocol -p test_sse_sessions.py -v
py -m unittest discover -s tests/protocol -p test_leave_room.py -v
```

Before the repair, the deterministic same-room test failed with:

```text
actual:   ['self-departure', 'while-away', 'self-arrival', 'live']
expected: ['self-arrival', 'live']
```

After the repair, both new rejoin/generation tests and the existing three room,
four session, and five leave tests passed: 14 focused tests. Syntax checks passed
for the three modified PHP handlers. The separate repeatable migration test also
passed, bringing the checks documented here to 15 tests. The same-room test now also exercises a
generation above `PHP_INT_MAX`; the other new test checks actual leave, repeated
leave, and repeated same-room join increments.

The deterministic test executes the real SSE handler in a dedicated CLI PHP
process against the research database and parses its stdout. It pauses only that
process with `SIGSTOP`, checking PID, process start time, exact CLI command, and
a random environment marker before signals. It verifies the process is stopped
while real HTTP leave and same-room join requests complete through Apache. It
then resumes the handler and checks delivery through a subsequent live marker.
Credentials are fed through stdin. Cleanup resumes the process, deletes only
the generated account, waits for its exit, and removes its generated room/events.
Post-failure inspection confirmed no fixture users or dedicated test processes
remained. No global/table locks or Apache/emulator process signals are used.

This provides deterministic SSE control-flow and database coverage plus real
HTTP membership transitions. It does not validate SSE over HTTP buffering,
browser/EventSource reconnection, original-server behavior, or Android UI event
ordering. Existing room/session tests separately exercise HTTP SSE streams.

## Remaining races and limits

- An event already being written when membership changes cannot be recalled.
  A transition can occur after the final membership check and before output.
- Initial SSE snapshots and join HTTP snapshots are not transactionally
  consistent with concurrent event publication; generation does not make them
  an atomic snapshot or resolve their event-baseline races.
- Concurrent joins/leaves may interleave with snapshot construction and arrival
  publication after the membership update. Generation rejects stale stream
  cursors; it does not serialize all join processing and event publication.
- Multiple simultaneous streams for one session still share a stored delivery
  cursor. Explicit resume behavior and its original-server contract remain a
  separate concern.
- Existing requests loaded before deployment need to end/reconnect before they
  execute the updated handler. This work does not force emulator reconnections.
