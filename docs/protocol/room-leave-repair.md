# Atomic room departure

`/session/leave-room` previously returned success and queued `room:user-removed`
without clearing `users.room_id`. Concurrent retries produced duplicate departures.
The research UDP relay therefore continued delivering room traffic to a player
after a successful leave request.

## Repair and evidence

The handler now locks the account row within a transaction, clears its room to
NULL, and inserts the departure event for the previous room before committing.
An account already outside a room receives the existing success acknowledgement
without another event. Invalid-session status remains 404. If publishing fails,
membership rolls back and the endpoint returns a JSON 500 response.

The native request constructor is `NetworkRoomAPI.Leave`, ARM64 RVA `0x17ad678`,
with a `session_id` request field. It is indexed in `native-transport.json` and the
reviewed contract is in `contracts.json`. The room-removal event identity follows
the existing publisher and receiver contracts. The database-side effects and
retry behavior are replacement-server repairs, not original-server captures.

Before the repair, tests reproduced unchanged membership, two events from
concurrent retries, and continued UDP delivery after leave. After the repair:

- Five additive HTTP/database tests pass: membership/event correctness, concurrent
  retry deduplication, already-outside behavior, invalid sessions, and rollback.
- The rollback test creates a temporary trigger scoped to its synthetic player,
  forces event insertion to fail, then removes the trigger. No persistent schema
  change is made.
- A UDP integration test verifies that a departed recipient receives no subsequent
  movement packet. Four existing SSE membership tests still pass.

```powershell
py -m unittest discover -s tests/protocol -p test_leave_room.py -v
py -m unittest discover -s tests/protocol -p test_sse_membership.py -v
$env:PYTHONPATH = 'tests/protocol'
py -m unittest test_udp_relay.UdpRelayTests.test_http_leave_stops_recipient_delivery -v
Remove-Item Env:PYTHONPATH
```

The optional UDP profile must be running for the last test. These tests preserve
the emulator account and remove only their own fixtures.

## Limits and related work

The wire request has no request ID or room ID. A delayed leave arriving after a new
join cannot be distinguished from a new leave; the concurrency guarantee applies
to retries without an intervening join. Existing SSE streams still hold the room
selected at connection time; changing rooms within a live stream needs a separate
client-contract review. This repair establishes UDP delivery isolation after
leave, not complete SSE room-transition isolation.

The idle investigation also found that the client sends HTTP pings roughly every
30 seconds with `session_id` and `type`, but the existing ping endpoint simply
returns success. `users.last_seen` is updated by SSE delivery loops and general row
updates, so it is not reliable evidence of a recent client heartbeat. The relay's
120-second receive-idle policy is unchanged pending a verified liveness design.

A bounded 135-second capture while the emulator remained stationary in the world
recorded zero UDP-5055 packets and zero kernel drops. This confirms that a periodic
UDP heartbeat cannot be assumed for this observed state. The capture summary is
[udp-idle-results.json](udp-idle-results.json).

Targeted Ghidra analysis can be repeated with
`wsl -- bash tools/research/ghidra-room-lifecycle.sh`. It covers Leave
(`0x17ad678`), ClearRoom (`0x17af7a8`), CloseComs (`0x17af900`), the leave callback
(`0x17b36a4`) and SendPingCo.MoveNext (`0x17b79c4`). The candidate CloseComs trace
unsubscribes room event handlers and closes UDP, which makes continued session/SSE
room switching an explicit follow-up obligation. Raw pseudocode stays ignored
and must be checked against disassembly before extending that contract.
