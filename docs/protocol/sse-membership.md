# Room membership event repair

The replacement server's `room:user-added` and `room:user-removed` events used the
SSE subscriber's account instead of the event's subject. Two-account HTTP stream
tests reproduced this before the repair: Observer received its own player ID,
name and level when Visitor joined, and its own ID when Visitor left.

## Evidence and scope

- `session/join-room/index.php` publishes the joining player's `player_id`, room
  and `WORLD` state through `lib/events.php`, which stores these in `event_queue`.
- `session/leave-room/index.php` publishes the departing player's `player_id`.
- `sse/index.php` previously reconstructed both payloads from `$user`, the
  authenticated subscriber. The repair uses the queued player ID. Arrival profile
  and active deck are fetched for that player; departure requires no account lookup.
- A deleted arrival subject is skipped while advancing the stream cursor, because
  the queue does not retain a complete historical profile. Departure still carries
  the queued ID even if the account no longer exists.

These are source-established replacement-server defects and synthetic runtime
observations, not surviving original-server captures. The wire field names and
types are retained. No database changes or original cursor semantics are asserted.

## Repeatable verification

With the isolated Compose stack running:

```powershell
py -m unittest discover -s tests/protocol -p test_sse_membership.py -v
docker compose -f compose.research.yaml exec -T web php -l /var/www/html/sse/index.php
```

The tests create two temporary accounts in a unique room and delete only their own
rows. They preserve the emulator account and never run the destructive global seed.
Three regression tests failed before the fix; all four tests pass after it:

1. Session start identifies the subscriber; arrival identifies the other player.
2. Departure retains the subject ID even after that account is deleted.
3. An explicit `since` cursor emits session start and only the later membership event.
4. A deleted arrival subject does not produce an event impersonating the subscriber.

## Remaining gaps

The client does not receive event IDs from this implementation; explicit `since`
replay tests do not establish automatic Android reconnect behavior. Historical
arrival profile/deck snapshots are not stored. Room changes on an existing stream,
snapshot/live-event races, null-recipient battle delivery and two-emulator movement
remain separate research tasks. This repair does not implement UDP.
