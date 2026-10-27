# Quiet connection retention and endpoint ownership

The optional local transport can retain quiet connections with `--idle-seconds 0`
on both host and server. The Compose overlay selects this policy; follow
[the setup commands](udp-stable-transport.md). Standalone CLI behavior defaults to
600 seconds. This is a replacement-server research policy, not recovered original
network behavior. No game heartbeat or cached movement is injected.

## Natural long-idle experiment

[Sanitized results](udp-idle-retention-results.json) record a natural 610.387-second
UDP-quiet interval on 2026-10-17. Both accounts continued HTTP heartbeats (62
successful responses); database checks found matching current session/room
heartbeats ten seconds old at the end. The first peer update reached the quiet
recipient with the exact expected player-ID translation before it sent again.
Both subsequent updates also passed. Local socket tuples were unchanged and
fixture cleanup succeeded. No relay capture was collected, so unchanged
relay-side endpoints are not claimed.

The earlier default-600 run missed its first delivery after 610.371 seconds and
recovered after fresh movement (`udp-lifecycle.md`). The new run used natural
elapsed time with no database timestamp manipulation or shortened timer. It
preceded the separate endpoint ownership repair below.

```powershell
py tools/research/probe_quiet_udp.py --seconds 610 --output .research/quiet-retained-610-report.json
```

Inspect `peer_to_quiet_recipient.received` and `expected_translation`; the probe
records outcomes without asserting that this delivery must succeed.

Resource limits remain: 256 active host peers, 256 active plus retired server
ports, and bounded outgoing queues. EOF, framing errors and socket errors still
close paths. Server ports stay quarantined until coordinated relay/adapter
restart. This does not provide unlimited idle or automatic reconnection.

## Confirmed endpoint ownership defect

Previously the PHP research relay retained two session registrations pointing at
one UDP address. An accepted session B in room 2 could reuse A's endpoint while
A's room-1 registration remained. C's next room-1 update then reached B's socket.
The new live regression failed on that exact 24-byte delivery before the repair;
its four rejected-registration controls passed.

After packet, authentication, WORLD/room and applicable sequence checks pass,
the relay removes other sessions registered at the sender endpoint before its
capacity check and registration. Only the last accepted session owns that
endpoint. All five tests now pass: accepted replacement prevents old-room
traffic while new-room delivery works; malformed, unknown-session, non-WORLD,
and stale-sequence attempts preserve the existing owner. These tests create and
clean up their own accounts and rooms without reseeding emulator data.

```powershell
py -m unittest discover -s tests/protocol -p test_udp_endpoint_ownership.py -v
```

This policy does not support multiplexing several sessions through one UDP
endpoint. Removing a registration also removes its sequence high-water record;
a later packet with that still-valid session can be accepted as a fresh
registration. Global replay prevention is not claimed. Before a new accepted
registration, another local process reusing a host UDP tuple can still receive
old replies. Use the adapter only in trusted local research; bounded identity
tombstones and transport authentication remain separate design work.

## Native evidence and remaining work

The [native lifecycle review](udp-native-lifecycle.md) shows the sender surviving
inspected room and socket transitions. Same-session sender recreation with a
zero sequence has not been demonstrated; the sequence acceptance rule remains
unchanged. Two-emulator room transitions, additional network interruption modes,
natural onboarding and original-server authority remain backlog items.

Validation includes 57 research tests (17 adapter tests also on Linux), five
ownership regressions, eleven existing relay tests and two opt-in tunnel
lifecycle tests. PHP syntax, evidence validation and Compose configuration are
checked separately. No schema or production deployment changes are included.
