# Quiet UDP mapping isolation

A Windows-only socket probe reproduces the Android idle-delivery failure without
an emulator. Two additive synthetic accounts register UDP endpoints on the
isolated Compose relay, keep HTTP heartbeats current, then send no UDP for at
least 125 seconds. The first delivery to the quiet recipient times out. Sending
from that recipient restores subsequent delivery while its bound local socket
address stays unchanged.

This isolates a sufficient failure path to Windows localhost through Docker's
published UDP port. It does not identify the exact component or expiration
threshold, rule out additional Android translation problems, or establish any
original-server heartbeat policy. No gameplay packet or relay behavior is changed.

## Reproduce

Start the existing isolated stack with its UDP profile. Install the capture tool
in the running research container if needed, as documented in
[Android peer verification](android-peer-verification.md). Use two terminals:

```powershell
# Terminal 1; let this finish before beginning another probe.
docker compose -f compose.research.yaml exec -T udp timeout -s INT 155 tcpdump -i any -y LINUX_SLL -s 0 -U -w /tmp/quiet-localhost.pcap udp port 5055
# Terminal 2, promptly after tcpdump starts:
py tools/research/probe_quiet_udp.py --seconds 125 --output .research/quiet-localhost-report.json
# After both commands finish:
docker compose -f compose.research.yaml cp udp:/tmp/quiet-localhost.pcap .research/quiet-localhost.pcap
py tools/research/summarize_quiet_udp.py .research/quiet-localhost.pcap --output .research/quiet-localhost-summary.json
```

Keep other UDP probes and clients stopped during this capture. The summary
requires fixed probe coordinates and consistent session identities; captures
containing multiple runs must not be combined. Raw PCAPs include session
credentials and remain ignored. The exported report omits identifiers, addresses,
ports and payload bytes.

The probe refuses report overwrites and output paths outside `.research`, accepts
125–180 seconds, creates its own room/accounts, and removes only those fixtures.
It checks heartbeat session/room/state matches and age in the database before and
after UDP silence. HTTP success alone is insufficient because invalid sessions
also receive a success acknowledgement. Delivery checks compare the complete
expected player-ID translation, with a 0.7-second receive timeout. Socket receipt
is separate evidence from relay egress in the PCAP.

## Recorded result

[Sanitized results](udp-quiet-mapping-results.json) record the verified Windows
run against Docker Engine 29.8.2 and PHP 8.3.35, based on commit `79c0ff5`.
The quiet interval lasted 125.399 seconds. Heartbeat ages were 5 and 6 seconds
at its end. The relay capture contains five ingress and four egress packets,
with zero kernel drops. Role 0 changed its relay-visible source endpoint once;
role 1 did not. Both Windows bound socket tuples stayed unchanged. The first
post-idle receipt timed out, and both recovery receipts matched the exact
translated packet. Scoped fixture cleanup succeeded.

An earlier exploratory run had the same socket-level outcome, but its capture
overlapped the next run's registration. That mixed capture and summary are not
published. The parser now rejects such changes of fixture identity instead of
counting them as mapping changes. Forty research tests pass, including five
quiet-capture parser tests; the evidence validator also passes.

## Remaining work

Test a research transport configuration that avoids the expiring published-port
mapping, then repeat both this quiet probe and the two-emulator scenario. Retain
room/session/privacy checks. Do not add guessed heartbeat datagrams to the game
protocol. Exact timeout, Docker/backend attribution, app suspension, sequence
reset on reconnect, and original server liveness behavior remain unresolved.
