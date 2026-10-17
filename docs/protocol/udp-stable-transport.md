# Optional stable UDP transport for local research

The Windows/Docker published UDP path loses delivery after a quiet interval
([isolation evidence](udp-quiet-mapping.md)). This optional adapter carries the
same 24-byte packets over a persistent TCP connection across that boundary.
The Windows listener and PHP relay still use UDP. There are no injected game
heartbeats, cached movement replays, or changes to the PHP relay's authentication,
room checks, sequence handling, or packet translation.

Each Windows UDP source gets its own TCP connection and each TCP connection gets
its own container-loopback UDP socket. Two-byte lengths delimit packets on TCP;
these lengths never reach the game or PHP. The adapter accepts only the current
research relay's single-record 24-byte packets, not the client's more general
multi-record receive capability.

## Start and stop

The base Compose file retains the original direct UDP configuration. Opt in with
the overlay below. It removes the published UDP port and publishes only localhost
TCP 5056. The host adapter binds localhost UDP 5055. The pinned Python sidecar
shares the relay's network namespace; the web and database services stay running.
Compose 5.6.0 and the pinned Python 3.13 image were used for validation.

```powershell
# Stop any previously running host adapter with Ctrl+C first.
# Always stop/recreate BOTH server-side services together, including on recovery.
docker compose -f compose.research.yaml -f compose.research-udp-tunnel.yaml --profile udp stop udp-tunnel udp
docker compose -f compose.research.yaml -f compose.research-udp-tunnel.yaml --profile udp up -d --force-recreate --no-deps udp udp-tunnel
# Keep this terminal running:
py tools/research/udp_transport_tunnel.py host
```

Start the base web/database/migration stack first if it is not already running.
Clients need a fresh movement packet to register after any relay or tunnel restart.
Do not restart only the server adapter: its port reservations protect endpoints
retained by PHP, so PHP's registrations must be cleared before new server sockets
can be allocated. Neither service has an automatic restart policy.

To return to direct UDP, stop the host adapter and both server-side services, then:

```powershell
docker compose -f compose.research.yaml --profile udp up -d --force-recreate --no-deps udp
```

The stopped optional sidecar may remain present. Do not use `down -v`; research
accounts and database contents are not reset by this procedure.

## Bounds and tradeoffs

Connections expire after 600 seconds without packet activity in either direction.
HTTP pings do not reset this adapter timer. Longer fully quiet intervals still
require fresh client movement; this is not unlimited idle support. Connections
are capped at 256 and each outgoing userspace queue is capped at 256 frames.
Slow peers, invalid framing and disconnected peers fail independently. TCP changes
loss and ordering behavior and can delay later movement behind retransmissions;
this is a local research transport, not recovered original-server networking.

When a server TCP connection closes, its UDP socket remains bound and incoming
packets are discarded. This prevents an old PHP registration from being delivered
to a new connection that inherits the port. Active plus retired server sockets
count against a lifetime cap of 256; exhaustion refuses new connections until a
coordinated restart. No credentials, endpoints or packet bytes are logged.

## Verification

Run the quiet probe and Android peer capture commands from their respective docs
with the overlay active. The relay PCAP sees loopback UDP endpoints; existing
sanitized summaries still apply. Do not run unrelated packet tests during a
capture. The quiet probe reports the observed outcome; it does not itself assert
that the first post-idle delivery must pass, so inspect `peer_to_quiet_recipient`.

The adapter's unit/integration tests cover independent paths, partial writes,
fragmented/coalesced frames, invalid packets, bounded buffers, EOF, peer limits,
idle cleanup and retired-port isolation. Existing relay integration tests check
session rotation, deletion, room changes and invalid traffic through the adapter.
Their setup now verifies either initial delivery order because independent TCP
connections do not guarantee cross-client ordering.

## Recorded acceptance

[Sanitized results](udp-stable-transport-results.json) record two live runs on
2026-10-17. The host ran Python 3.14.5; the pinned sidecar ran Python 3.13.16.

- The synthetic probe stayed UDP-quiet for 125.351 seconds. Both persisted
  heartbeats were five seconds old afterward. Its first post-idle delivery
  succeeded with exact player-ID translation, followed by both later deliveries.
  Local socket tuples stayed unchanged, and the nine-packet relay capture showed
  no source endpoint changes. Fixture cleanup succeeded.
- The two existing Android clients completed the 170-second capture. The peer's
  sequence-17 movement arrived at the stationary primary after approximately
  128 seconds without UDP traffic. The primary's 24-byte `recvfrom` completion
  was at syscall-relative time 140.486286, before its next `sendto` at 150.984903.
  The 139/144-second screenshots show the remote avatar changing position while
  the primary remains stationary. Trace and PCAP time origins differ; these
  numbers are not a cross-capture latency measurement.
- All five relay egress packets matched the destination guest capture. Neither
  relay-visible endpoint changed. Both clients retained the same PID/socket
  inode/descriptor, with matching current HTTP heartbeats. Guest captures contain
  six/five packets and zero kernel drops; the relay contains eleven packets and
  zero kernel drops. Loopback filter counters were double captured counts.
- All 51 research tests and 11 existing UDP relay integration tests pass, as do
  the evidence validator and Compose configuration check. Three initial protocol
  setup checks timed out while requiring one registration order; the corrected
  setup validates either order and the full rerun passes.

This resolves the reproduced quiet-delivery failure for the tested local adapter
configuration. Direct published UDP remains affected. Natural onboarding,
longer silence, two-emulator room changes, app suspension, reconnect sequence
reset and original-server behavior remain outside this acceptance. The [lifecycle follow-up](udp-lifecycle.md) hardens transient server accept/setup
errors and records reconnect behavior. Recover from helper restarts with a
coordinated restart, not an independent sidecar restart.
