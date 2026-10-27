# Two Android research clients

This follow-up exercises Android 2.41.0 using two independent API30 emulators,
the ARM32 diagnostic multiplayer APK, and the isolated replacement backend.
It does not establish natural onboarding, original-server behavior, iOS support,
or authoritative movement rules.

## Observed result

Both accounts enter the same room and see each other. Packet captures and
successful game-process UDP receive calls establish movement in both directions.
However, **Android idle delivery still fails** after a quiet interval despite
fresh matching HTTP heartbeats. See [sanitized results](android-peer-results.json).

Two 170-second runs reproduce this. The [relay comparison](android-peer-relay-hops.json)
exports role labels instead of credentials or network endpoints. In the second run, the relay receives the
peer's late movement and emits it to the primary's previously learned endpoint;
neither the primary PCAP nor its game-process trace records that packet. The
primary's next outbound movement reaches the relay from a different endpoint.
Its Android PID, socket inode and descriptor are unchanged. A short follow-up
capture then records three incoming peer movement packets, and the screenshot
shows the remote avatar updated again.

This demonstrates intermediate endpoint remapping; it does not identify which
emulator/host/container translation layer expired the mapping, nor its exact
timeout. Keeping a server-side registration alive through HTTP does not keep
every UDP mapping alive. The synthetic heartbeat repair remains valid within
its tested scope, but is insufficient for this live Android configuration.
No speculative UDP heartbeat or client modification was added to hide the gap.

## Devices and setup

| Role | Dedicated AVD | ADB serial | Account |
|---|---|---|---|
| Primary | `PocketMortys_API30` | `emulator-5556` | `PMResearch01` |
| Peer | `PocketMortys_API30_Peer` | `emulator-5558` | `PMResearch02` |

Both use ADB server port 5038, host graphics, and separate userdata directories.
Provisioning preserves existing saves and rejects a locator pointing at another
device's data. Defaults still select the primary. Optional explicit serial/port
arguments must match the selected AVD.

```powershell
docker compose -f compose.research.yaml --profile udp up -d --build
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/seed-client.php --udp
py tools/research/emulator_setup.py --avd PocketMortys_API30_Peer
./tools/research/emulator.ps1 -Headless
./tools/research/emulator.ps1 -Avd PocketMortys_API30_Peer -Headless
py tools/research/install_research_client.py --sdk-network --udp
py tools/research/install_research_client.py --avd PocketMortys_API30_Peer --sdk-network --udp
```

These installer commands require the already built/signed diagnostic APKs
described in `research-client.md`. Network rules expire on emulator reboot.
No account data is copied from the first emulator. Start the game on each serial
with `adb -P 5038 -s SERIAL shell monkey -p com.turner.pocketmorties 1`.
On the fresh peer, decline the optional Google Play Games installation, finish
the startup consent screen, choose Multiplayer, and register `PMResearch02`.
Confirm the keyboard's OK button before tapping Play. Dismiss the introductory
dialogues and position both clients in the world with the normal 1280x720 D-pad.

The initial screenshots from this follow-up show each client's named avatar on
the other's screen. This confirms same-room entry/visibility using distinct
accounts; it is not a full two-account gameplay acceptance run.

## Bounded idle-delivery capture

```powershell
py tools/research/probe_android_peers.py
```

The runner refuses unexpected AVDs, missing game processes, ambiguous UDP socket
mappings, wrong display dimensions, stale/mismatched heartbeats, or accounts
outside a shared WORLD room. It does not install, restart, reseed or log in clients.
It writes raw evidence only under an empty `.research` output directory.

The fixed 170-second run starts packet captures and raw-argument syscall traces
on both clients, moves both right at about 3 seconds, moves the peer left at 12
seconds, and leaves the primary stationary. At 140 seconds the peer moves right;
at 150 seconds the primary moves left. Screenshots at 139 and 144 seconds bracket
the peer's late movement. Database samples record heartbeat ages and matching
session/room booleans without exporting their identifiers.

Each game's connected UDP socket is mapped from `/proc/PID/net/udp` to its owned
file descriptor by socket inode. PID, inode and descriptor must match at the end.
`strace -e raw=all` avoids dumping packet buffers. PCAP files still contain session
credentials and remain ignored. Use the two summarizers to export allowlisted
timing, directions, sequences, coordinates and successful syscall byte counts:

```powershell
py tools/research/summarize_udp_pcap.py .research/emulator/peer-probe/primary.pcap --output .research/emulator/peer-probe/primary-packets.json
# Substitute the primary socket_before.fd from the local metadata.json:
py tools/research/summarize_udp_syscalls.py .research/emulator/peer-probe/primary.syscalls.log --fd FD --output .research/emulator/peer-probe/primary-receives.json
```

Repeat for `peer`. The two summaries use different relative origins (first PCAP
packet versus first timestamped syscall); compare elapsed intervals within each
capture, not raw offsets across the formats. Packet arrival, application receive
completion and visible avatar movement are distinct evidence layers.
Ordinary strace timestamps are syscall entry times; resumed lines use completion
times. Raw argument mode avoids the installed strace's ARM32 structure-decoding
limitation, which was reported during both captures.

## Relay-side follow-up

For the second run, `tcpdump` 4.99.5-2 was installed only in the running research
UDP container. It was not added to the application image or deployed elsewhere.
Start a relay capture before invoking the runner with a new output directory:

```powershell
docker compose -f compose.research.yaml exec -T udp sh -c 'apt-get update -qq && apt-get install -y -qq --no-install-recommends tcpdump=4.99.5-2'
docker compose -f compose.research.yaml exec -T udp timeout -s INT 185 tcpdump -i any -y LINUX_SLL -s 0 -U -w /tmp/peer-probe-relay.pcap udp port 5055
# In another terminal, promptly:
py tools/research/probe_android_peers.py --output-dir .research/emulator/peer-probe-relay-check
docker compose -f compose.research.yaml cp udp:/tmp/peer-probe-relay.pcap .research/emulator/peer-probe-relay-check/relay.pcap
py tools/research/compare_udp_hops.py .research/emulator/peer-probe-relay-check/relay.pcap .research/emulator/peer-probe-relay-check/primary.pcap .research/emulator/peer-probe-relay-check/peer.pcap --output .research/emulator/peer-probe-relay-check/hops.json
```

After the primary's scheduled 150-second movement, a separate 15-second primary
tcpdump capture and one manual peer left movement verified recovery. These are
additional steps, not part of the runner's fixed timeline. Raw files and screenshot
hashes are recorded in the results; raw credentials remain untracked.

## Limits and regression coverage

The capture investigates one foreground stationary recipient and movement in both
directions. It does not test app suspension, NAT expiry, room changes, packet
loss/reordering, reconnect sequence reset, rapid same-room rejoin, or relay restart.
Matching socket identity before/after does not rule out transient descriptor reuse
inside the interval. Trace instrumentation may affect timing.

Thirty-five research tests pass, including separate-device/saved-data guards and
sanitized PCAP/syscall parser tests. The strengthened opt-in UDP idle test also
passes in 129.264 seconds: after natural idle retention/expiry checks, it ages one
recorded heartbeat with a scoped database update and verifies that retained peer
expires while the recovered peer continues receiving. This final check uses
controlled timestamp aging, not another natural 120-second wait.
