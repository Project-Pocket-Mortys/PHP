# Room changes on a live SSE connection

The SSE handler previously captured one room and queried it for the lifetime of
the session. Three additive tests reproduced old-room delivery after HTTP leave
and missing destination events after HTTP join. The latter two cases timed out;
the leave case received an event when silence was expected.

The handler now reads current membership on each poll and before processing each
snapshot/queued event. Outside a room it keeps the session stream alive without
reading room events. On a room change it adopts the destination baseline stored
by `join-room`. Join now installs room membership and that baseline in one SQL
update. Cursor writes check both the session and room, preventing a previous
room's poll from overwriting the destination baseline. No schema change is needed.

The join HTTP response already contains users, pickups, wild Morties and bots.
Transitions therefore do not send another initial snapshot or another
`session:start`. Existing initial-connect and explicit resume handling remain.

## Client evidence

Android 2.41.0 ARM64 `libil2cpp.so` SHA-256:
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.

The reproducible targeted Ghidra pass is:

```powershell
wsl -- bash tools/research/ghidra-room-transitions.sh
```

Raw pseudocode is ignored at `.research/ghidra-room-transitions.json`; all five
methods exported without a decompiler error. Ghidra uses image base `0x100000`.
Independent ARM64 call mappings are in `native-transport.json`:

| Method | Native RVA | Relevant calls |
|---|---|---|
| `NetworkRoomAPI.Join` | `0x17ad988` | constructs `/session/join-room`, invokes `NetworkHTTP.Request` |
| join callback `<Join>b__0` | `0x17b34f8` | response parser, then `SetUpRoom` at call site `0x17b35bc` |
| `SetUpRoom` | `0x17adc00` | updates users/bots/wild Morties/pickups, then `OpenComs` at `0x17ae054` |
| `OpenComs` | `0x17aee64` | `NetworkSessionAPI.On`, clears receiver UDP sequence tracking (preserves sender sequence), `UdpChannel.Open` |
| `CloseComs` | `0x17af900` | `NetworkSessionAPI.Off`, then `UdpChannel.Close` at `0x17b0224` |

These static calls support room subscriptions on an existing session transport;
they are not an original-server capture. The repair's delivery behavior is
verified against the replacement server using synthetic accounts, not a new
Android UI room-transition capture.

## Regression checks

```powershell
py -m unittest discover -s tests/protocol -p test_sse_rooms.py -v
py -m unittest discover -s tests/protocol -p test_sse_sessions.py -v
py -m unittest discover -s tests/protocol -p test_sse_membership.py -v
py -m unittest discover -s tests/protocol -p test_leave_room.py -v
py tools/research/validate.py
```

All 16 focused tests pass. Both changed PHP handlers pass `php -l`. Fixtures use
random isolated rooms/accounts and preserve the emulator account. New scenarios
exercise leave/wait/join on one stream, direct room changes, and return to the
previous room without historical replay.

## Remaining limits

- A leave/rejoin to the same room entirely between polls can escape detection.
  A membership generation would distinguish successive joins; adding one needs
  a versioned migration and concurrent transition tests.
- An event already being written when membership changes cannot be recalled.
- Initial snapshots and join HTTP snapshots are not transactionally consistent
  with concurrent event publication. Snapshot/cursor races need a separate audit.
- Multiple simultaneous streams for the same session still share a stored cursor.
- Generic private-event filtering and original reconnect semantics remain open.
- A two-emulator same-world portal leave/rejoin now has HTTP, database and UDP evidence (`android-portal-transition.md`); distinct-world UDP isolation now also passes (`distinct-world-verification.md`); raw SSE event ordering and event-type privacy remain unverified.
