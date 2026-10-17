# UDP adapter lifecycle verification

This follow-up separates a new game session from a new transport connection.
The adapter remains a local research workaround; original-server reconnect rules
and automatic recovery are not established by these replacement-server tests.

## Retained sessions and TCP reconnects

The opt-in live tests use four disposable accounts across two rooms. After one
TCP connection closes, the relay can still retain its old UDP endpoint. The
adapter keeps that UDP port reserved and drains packets addressed to it. New
connections in another room do not receive those updates.

A replacement connection carrying the same valid session and a newer sequence
(100 to 101) learns a fresh endpoint and receives the next peer packet. Resetting
100 to 0 is stale under the recovered modulo-256 comparison and does not learn
the new endpoint. Rotating the account session allows sequence zero on the new
session; packets using the revoked session are rejected. This does not mean every
sequence reset is rejected: wraparound and the previous sequence matter. No
sequence rule or game packet was changed to make these tests pass.

```powershell
# Requires the optional transport stack already running; see udp-stable-transport.md.
$env:PM_RUN_UDP_TUNNEL='1'
py -m unittest discover -s tests/protocol -p test_udp_tunnel_lifecycle.py -v
Remove-Item Env:PM_RUN_UDP_TUNNEL
```

These two tests verify complete translated payloads and clean up only their own
accounts, rooms and queued events. They do not wait for PHP's 120-second expiry
or reset the emulator accounts. Normal discovery skips them without the flag.

## Adapter accept failures

The adapter previously allowed an operating-system error during TCP accept or
per-peer UDP setup to terminate the helper. It now counts the error and preserves
existing connections. Partial TCP/UDP sockets and selector registrations are
released before consuming a peer slot. These endpoints have not processed any
payload, so PHP cannot have learned them; releasing them does not weaken the
quarantine rule for established peers.

Fault-injection tests cover accept, nonblocking setup, UDP socket allocation,
bind/connect, and selector registration failures, including a registration that
succeeds before the injected error. They verify descriptor cleanup, unchanged
capacity and continued forwarding through an existing connection. These are
controlled failure tests, not an observed operating-system outage.

## Limits

A same-session sequence reset remains an unproven client scenario; the
[native lifecycle review](udp-native-lifecycle.md) preserves the sender across
room and socket transitions. Application suspension, TCP
loss and process restart are different scenarios and must not be conflated.
The server adapter and PHP must still restart together to clear old registrations
before UDP port reservations are released. No database or gameplay changes are
part of this follow-up.

## Android restart and background observations

[Sanitized results](udp-lifecycle-results.json) record Android 2.41.0 with the
existing diagnostic multiplayer profile on the two API-30 emulators. These are
manual scenarios, not a claim of natural onboarding or automatic reconnection.

The primary was force-stopped and launched again, then Multiplayer was selected.
The stored account was reused, but the server session, process and UDP socket
changed. The peer retained its session and process. The restarted primary's first
new UDP identity used sequence zero; its placement body appears in the peer's
capture. Subsequent movement worked in both directions, with both accounts in
the same room and current matching heartbeats. Introductory multiplayer prompts
reappeared and were dismissed; their persistence remains a separate research gap.

In a separate Home/resume observation, the primary spent 78.792 seconds outside
the foreground. Its process/socket and both account sessions remained unchanged.
Three peer updates (sequences 28, 29 and 30) appeared in the primary's packet
capture during that interval, with no primary outbound packets in the same
window. After returning to the game, screenshots showed both players and fresh
movement was exchanged. Packet capture alone does not prove the game processed
updates while backgrounded; no syscall trace was collected for this scenario.

Capture clocks differ between emulators and the host, so the timestamps are not
latency measurements. The final primary sequence-10 packet lacks a peer match
near the capture boundary; the peer reported 26 captured packets versus 27 filter
matches, with zero kernel drops. This absence is not evidence of network loss.

To repeat, use the existing two WORLD accounts and landscape controls:

```powershell
$pmAdb='.research/emulator/sdk/platform-tools/adb.exe'
# In separate terminals, capture each device before starting; use distinct files.
& $pmAdb -P 5038 -s emulator-5556 shell timeout -s INT 300 /system/bin/tcpdump -i any -s 0 -U -w /data/local/tmp/restart-primary.pcap udp port 5055
& $pmAdb -P 5038 -s emulator-5558 shell timeout -s INT 300 /system/bin/tcpdump -i any -s 0 -U -w /data/local/tmp/restart-peer.pcap udp port 5055
# Control terminal:
& $pmAdb -P 5038 -s emulator-5556 shell am force-stop com.turner.pocketmorties
& $pmAdb -P 5038 -s emulator-5556 shell monkey -p com.turner.pocketmorties -c android.intent.category.LAUNCHER 1
# Wait for the menu; select Multiplayer and dismiss any introductory prompts.
# Move both players. For a separate background check:
& $pmAdb -P 5038 -s emulator-5556 shell input keyevent KEYCODE_HOME
# Record elapsed time, move the peer, then launch the primary again to resume.
```

Pull captures into `.research` and use `summarize_udp_pcap.py` for sanitized
summaries. Compare session identifiers only privately and export changed/unchanged
booleans. The recorded run used 240/225-second captures, not the longer suggested
300-second coverage above. Do not reinstall or clear saved data for this test.

## Natural long-idle boundary

The quiet probe now accepts 125 through 660 seconds while preserving its bounded
calls, scoped fixtures and refusal to overwrite reports. A 610.371-second natural
UDP silence was observed with 62 successful HTTP heartbeats. Both persisted rows
matched the current sessions/room, with ages 10 and 11 seconds at the end.

The first post-idle delivery timed out at 0.7 seconds. After the recipient sent
again, both subsequent deliveries matched the exact player-ID translation. The
Windows socket tuples were unchanged, and fixture cleanup succeeded. This is
consistent with the adapter's configured 600-second inactivity limit; it is not
an exact measurement of the expiration instant. No clock acceleration, shortened
timeout or database timestamp aging was used. No relay PCAP or per-connection
expiry trace was collected for this long run.

```powershell
py tools/research/probe_quiet_udp.py --seconds 610 --output .research/quiet-tunnel-610-report.json
```

This establishes a remaining limitation rather than fixing it: HTTP heartbeats
retain the PHP registration, but do not keep the transparent transport adapter
alive indefinitely. Fresh movement restores a path when sequence continuity is
preserved. The original game's intended long-idle policy remains unresolved.

The captures above used the previous adapter implementation (`535a604`). After
they finished, both server-side services were stopped/recreated together to load
`7dde299`; the host adapter remained running and learned new TCP paths on fresh
movement. All 53 research tests, both opt-in lifecycle tests and the 11 existing
relay tests pass. All 13 adapter tests also pass inside the Linux sidecar. The
normal-discovery skip gate was also checked. The evidence
validator and Compose checks pass. Transient operating-system failures are
covered by fault injection, not by deliberately disrupting the host network.

The subsequent [idle-retention experiment](udp-idle-retention.md) disables the
optional adapter timeout and verifies first delivery after 610 seconds. The
default-timeout observations above remain historical evidence.
