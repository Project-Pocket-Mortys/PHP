# Android portal leave and rejoin

Android 2.41.0 can leave and rejoin the existing world-1 room through the portal
while retaining its session and process. This is a same-room round trip against
the isolated replacement backend using the optional stable transport; it does
not establish distinct-room isolation or original-server behavior.

## Observations

[Sanitized evidence](android-portal-results.json) records the bounded 60-second
capture and hashes of ignored raw artifacts on 2026-10-17. Both API30 emulators
used the existing ARM32 diagnostic multiplayer client and accounts.

- Opening the portal sent `POST /session/leave-room` at 19:26:29 UTC, returning
  `success`. A database sample found the primary outside a room and the peer
  still in its original room; both session identifiers were unchanged.
- Selecting Mortyland opened a confirmation screen; pressing Teleport sent
  `POST /session/join-room` with `world_id: "1"` at 19:26:45 UTC. The response
  contained the existing room, transport, world/zone and entity collections.
  Subsequent samples found both players back in the original room.
- Primary process 7153 retained descriptor number 93 but its socket inode changed
  from 150578 to 151143. The peer's process/socket/descriptor remained unchanged.
  Descriptor reuse means all calls on FD 93 cannot be treated as UDP throughout
  the capture; non-24-byte gap traffic is excluded from the exported syscall list.
- Primary sequences 40 and 41 appeared at the peer with the exact expected
  player-ID prefix and unchanged remaining packet bytes. Peer sequences 53, 54
  and 55 similarly appeared at the primary. Both processes recorded corresponding
  successful 24-byte receive calls after rejoin. Sequence checks were unchanged.
- Earlier peer sequences 51 and 52 are absent from the primary capture. The first
  was sent while the primary was outside the room; the second preceded its first
  captured new registration. Absence is scoped to these captures, not a claim
  about arbitrary packet loss. Captures contain five/seven packets respectively,
  with zero kernel drops.

The sender resumed with a nonzero sequence on the same session. Together with
[native lifecycle evidence](udp-native-lifecycle.md), this supplies an actual
client leave/rejoin scenario that does not require weakening sequence checks.

## Visual and instrumentation limits

The exploratory pass showed the primary avatar disappearing from the peer's
screen when the portal menu opened, and the primary had no owned relay UDP
socket then. The main capture used packet capture and raw-argument strace on
both clients. Intermediate primary screenshots were black despite HTTP and
packet activity. Their cause was not established, so they do not certify visible
transition success. A post-capture screenshot returned to the world with tutorial
popups still displayed; fixed-timeline dismiss taps had not reliably cleared
them. Manual dismissal restored normal controls. The tutorial repeats on rejoin
and is a separate unresolved onboarding/progression issue.

There was no relay PCAP or raw SSE capture in this run. Syscall, PCAP and host
clocks have different origins; no latency measurements are inferred. Reusing an
FD and observing its inode only before/after is not continuous ownership proof.

## Reproduce

Use the [existing two-client setup](android-peer-verification.md) and
[optional adapter](udp-stable-transport.md). Preserve accounts and do not reseed.
Both clients must be in world 1 with 1280x720 landscape displays. Position the
primary directly in front of the plaza portal, facing upward, with no dialogue
or menu open; leave the peer in the world. The A button is at approximately
(1054,535). Opening the portal itself leaves the room before a destination is
chosen. At level 1 only Mortyland is selectable.

```powershell
py tools/research/probe_android_portal.py --output-dir .research/emulator/portal-roundtrip-next
```

The runner checks AVD identity, root/tool availability, display size, shared
membership and initial owned UDP sockets. It requires a new ignored directory.
It records scheduled actions, membership comparisons, captures and screenshots;
`complete` means acquisition finished, not that every UI action succeeded.
Review images and HTTP logs after each run. The recorded experiment used the
hashed `.research/run-portal-roundtrip.py` prototype; the checked-in runner uses
the same action schedule with output arguments and additional preflight checks.
Do not run concurrent captures that use the same remote filenames.

The schedule opens the portal at 3 seconds, samples at 8, moves the peer at 11,
selects Mortyland at 15, confirms Teleport at 19, samples at 29, attempts dialogue
dismissal at 32/35, moves primary/peer at 39/43, and samples again at 49. Captures
stop at 60 seconds. If dialogs remain afterward, inspect and dismiss them
manually before further gameplay tests. Fixed coordinates are specific to this
layout and diagnostic profile.

Use `summarize_udp_pcap.py` on each PCAP and `summarize_udp_syscalls.py --fd FD`
on each trace, with FD from metadata. Raw captures stay ignored because they
contain session credentials. HTTP exchanges are recorded by the isolated image
at `/tmp/pocket-research-http.jsonl`; export only the relevant allowlisted fields.

## Distinct-room acceptance still pending

SSE advertises minimum levels 1, 5, 15, 30, 5, 10 and 15 for worlds 1 through 7.
The client independently checks level eligibility; dimension ownership alone does
not unlock them. The research seed supplies only world 1. Join chooses the first
room for a world (`LIMIT 1`) and accepts no client room selection, so adding a
second world-1 row does not provide deterministic switching.

A distinct-room UI test needs an explicit synthetic higher-level test profile
and a destination world fixture whose zone/assets are verified, followed by
leave/join captures, old-room silence, destination delivery and return. No player
level or persistent gameplay progression was changed for this experiment.
