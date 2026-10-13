# UDP movement and SSE interruption findings

Android 2.41.0 was exercised on the dedicated API30 emulator with the ARM32
diagnostic multiplayer profile and manifest 1013. All traffic targets the isolated
replacement backend. No original-server captures are available.

## Movement wire record

Targeted native analysis is indexed in [movement-native.json](movement-native.json).
The reviewed layout is in [contracts.json](contracts.json). Every record is 24 bytes:

| Offset | Size | Encoding |
|---|---|---|
| 0 | 16 | Canonical network-order GUID; client sends session ID |
| 16 | 1 | Sequence byte, wraps 255 to 0 |
| 17 | 2 | Unsigned x, big-endian |
| 19 | 2 | Unsigned y, big-endian |
| 21 | 2 | Little-endian history bit field |
| 23 | 1 | Direction: none 0, right 1, left 2, up 3, down 4 |

The receiver divides a positive datagram length by 24 and ignores nonmultiples.
History uses six two-bit steps in bits 0..11, newest first, with count in bits
12..15. The inverse steps are 0=x+1, 1=x-1, 2=y+1, 3=y-1. Counts above six produce
an empty history. Sequence comparison uses a 127 threshold, including the client's
asymmetric treatment of a difference of 128; the decoder tests preserve it.

The [sanitized fixture](../../tests/protocol/fixtures/udp-movement.json) contains
15 attempted movement sends while moving right, down, left and up. Session bytes
were checked against the active synthetic account inside the isolated database
and then replaced with a fixed synthetic GUID before export. The raw trace shows
EPERM/ECONNREFUSED: the current isolation firewall rejects these sends and no UDP
service is running. This is syscall-buffer evidence, not successful packet delivery.

All captured positions and prior-position histories agree with the decoder. The
receiver's GUID becomes a node identifier and is compared with the local player's
identity; the exact outbound-session to inbound-player mapping still needs a live
two-player test. An unmodified packet echo could leak a session credential and is
not a substitute for recovering that contract.

## SSE interruption and recovery

While the client was in the multiplayer world, the isolated Apache container was
restarted with a one-second shutdown timeout. The game returned to the multiplayer
login screen with `ES_CLOSED`; it did not reopen SSE in this observation. ARM64
`NetworkEventSource.OnRetryHandler` returns false (`mov w0,wzr` at RVA 0x17b9ffc).

Pressing Play performed a new `/user/login`, followed by `GET /sse/` without
`Last-Event-ID` or `since`. The captured stream emitted `session:start`, then
`room:user-added`; neither carried an SSE `id` field. The client reentered the
world. Sanitized summaries are [interruption](sse-interruption-capture.json) and
[Play recovery](sse-play-capture.json). Each reports packet timestamps, not capture
process lifetime; captures were bounded to 45 and 35 seconds respectively and had
zero kernel drops. Quiet time produces no timestamped records.

This is one replacement-server interruption mode. It does not establish behavior
for idle timeouts, radio loss, application suspension, in-progress battles, event
replay, or original-server cursors. No retry/cursor behavior was changed in PHP.

## Reproduction

```powershell
wsl -- bash tools/research/ghidra-movement.sh
py -m unittest discover -s tests/research -p test_udp_codec.py -v
py -m unittest discover -s tests/research -p test_local_pcap.py -v
```

Record a bounded trace while using the movement pad in the dedicated emulator:

```powershell
& .research/emulator/sdk/platform-tools/adb.exe -P 5038 -s emulator-5556 shell 'timeout 25 strace -f -p $(pidof com.turner.pocketmorties) -s 100 -xx -e trace=sendto,recvfrom,connect -o /data/local/tmp/udp.log'
& .research/emulator/sdk/platform-tools/adb.exe -P 5038 -s emulator-5556 pull /data/local/tmp/udp.log .research/emulator/udp.log
py tools/research/sanitize_udp_trace.py .research/emulator/udp.log .research/emulator/udp-sanitized.json
```

In another terminal, capture local HTTP before interrupting the isolated web
container. Restart affects all test streams; no production service is involved.

```powershell
& .research/emulator/sdk/platform-tools/adb.exe -P 5038 -s emulator-5556 shell 'timeout 45 tcpdump -i any -s 0 -w /data/local/tmp/reconnect.pcap tcp port 8087'
```

While that capture runs, restart from the other terminal:

```powershell
docker compose -f compose.research.yaml restart -t 1 web
```

After capture finishes:

```powershell
& .research/emulator/sdk/platform-tools/adb.exe -P 5038 -s emulator-5556 pull /data/local/tmp/reconnect.pcap .research/emulator/reconnect.pcap
py tools/research/summarize_local_pcap.py .research/emulator/reconnect.pcap --output .research/emulator/reconnect-summary.json
```

The summarizer supports bounded Linux-cooked IPv4 captures, deduplicates TCP
retransmissions and rejects gaps. It omits query strings, header values and bodies.
Raw captures contain credentials and remain ignored. Start a second capture before
pressing Play to inspect recovery. The first capture alone cannot verify that flow.

## Next dependencies

1. Provide a local-only UDP route/listener; ADB TCP reverse is not a UDP transport.
2. Verify incoming player IDs with a second synthetic player, plus room privacy,
   unknown/expired sessions and sequence ordering. Establish endpoint lifetime.
3. Establish movement validation and broadcast cadence separately; these are
   server responsibilities and are not recovered merely from client serialization.
4. Exercise SSE recovery during a battle and with pending private events before
   assigning replay guarantees or enabling emitted cursor IDs.
