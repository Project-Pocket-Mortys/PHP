# Fresh SSE snapshot publication boundary

The initial SSE snapshot queried pickups, wild Morties and bots separately, then
read the room's maximum event ID and used it as the streaming cursor. A pickup
or ordinary event committed after its snapshot query but before that final
maximum could be skipped permanently by that stream. This is a
replacement-server defect; original-server snapshot semantics remain unknown.

The repair captures the room's maximum visible event ID **before** querying any
snapshot entities. All three entity queries are bounded by that same ID. After
the snapshot, streaming starts above that boundary. New rows committed with
higher IDs during snapshot delivery therefore reach the ordinary queue path,
without also appearing in a later snapshot category. Existing recipient checks,
membership-generation checks, payload fields and resume behavior are preserved.
No new migration is required beyond the existing membership-generation migration.

## Reproduction and scope

```powershell
py -m unittest discover -s tests/protocol -p test_sse_snapshot_boundary.py -v
py -m unittest discover -s tests/protocol -p test_sse_event_privacy.py -v
py -m unittest discover -s tests/protocol -p test_sse_rejoin_generation.py -v
py -m unittest discover -s tests/protocol -p test_sse_rooms.py -v
py -m unittest discover -s tests/protocol -p test_sse_sessions.py -v
py tools/research/validate.py
```

The regression uses disposable synthetic fixtures and the real SSE handler in
a dedicated CLI PHP process. A wrapper pauses that process during its first
pickup snapshot output; the test commits new entities and a room event while it
is paused. It then resumes the handler and checks delivery. This is deterministic
handler/database coverage, not an Android capture or HTTP buffering test. The
separate privacy, room and session tests exercise HTTP SSE transport.

Before repair, the deterministic test received `seed-pickup`, `late-wild`,
`late-bot`, and `after-initialization-fence`, but missed `late-pickup` and
`mid-snapshot-marker`. After repair all six arrive once. The final fence makes
missing events fail without depending on a stream timeout; exact counts also
catch duplicates from an incomplete repair that leaves later categories unbounded.

All 15 focused tests in the commands above passed, as did PHP syntax and
protocol source-hash/JSON/native-boundary validation.

## Remaining limits

- This is an event-ID boundary, not a transactionally consistent state snapshot.
  Existing entity rows can still change while different categories are read.
- Auto-increment allocation is not commit order. A transaction that allocated a
  lower ID before the boundary but commits later can still escape an ID cursor.
  Solving that requires a separate producer/transaction-order audit; this repair
  does not claim general exactly-once delivery.
- Join-room HTTP snapshot construction and event publication remain separately
  audited work. This change is limited to initial fresh SSE connections.
- Shared session cursors, concurrent joins, and membership changes after a final
  visibility check remain subject to the limits in
  [membership generations](sse-rejoin-generation.md).
- Existing long-lived PHP streams retain their loaded code until reconnect.
  No emulator restart or production deployment is part of this verification.
