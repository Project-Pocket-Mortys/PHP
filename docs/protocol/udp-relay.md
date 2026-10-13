# Isolated PHP UDP relay

The optional `udp` Compose profile runs a PHP 8.3 CLI listener from
`tools/research/server/udp-relay.php`. Windows publishes it only at
`127.0.0.1:5055/udp`; the dedicated emulator reaches the host through `10.0.2.2`.
ADB reverse remains responsible for TCP HTTP/SSE only. No production service,
database schema or existing gameplay HTTP handler is changed.

## Verified behavior

- Exactly one 24-byte sender record is accepted per datagram, matching captures.
  Invalid size, direction or history count is discarded.
- The session GUID must resolve to a WORLD-state account in an existing room.
- The forwarded GUID is the sender's **player ID**, never its session credential.
  Remaining packet bytes are retained. The emulator displayed the corresponding
  synthetic player's avatar, confirming the receiver identity mapping.
- Only other registered peers in that room receive movement. Every recipient's
  session, player identity, room and WORLD state are checked against the database
  before delivery. Duplicate and old sequences are discarded; byte wrap is accepted.
- Runtime testing used one Android 2.41.0 ARM32 diagnostic-profile emulator and one
  synthetic socket peer. The probe sent 111 updates, received five emulator records,
  appeared in the world, and disappeared after its removal event. No Unity errors
  were logged during that probe. See [udp-relay-results.json](udp-relay-results.json).

Ten additive socket/database tests cover delivery, identity replacement, room
privacy, session rotation on both ends, deleted/inactive recipients, inactive
senders, malformed/unknown-session packets, duplicate ordering and wrap. The
emulator's account and save are preserved. The fixture repeatability test passes.

## Run and reproduce

```powershell
docker compose -f compose.research.yaml --profile udp up -d --build udp
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/seed-client.php --udp
py tools/research/install_research_client.py --sdk-network --udp
```

The seed option updates only the designated synthetic room's UDP destination.
Without `--udp`, seeding preserves an existing destination. The installer adds a
single UDP exception for `10.0.2.2:5055`, enables Wi-Fi and preserves saves. Start
the installed client, enter multiplayer, dismiss the tutorial dialogue and move.

```powershell
py -m unittest discover -s tests/protocol -p test_udp_relay.py -v
py tools/research/probe_udp_client.py --seconds 60 --output .research/emulator/udp-probe-results.json
```

While the probe runs, its `UDPProbe` player alternates between two nearby positions.
Move the emulator player to generate return packets. The probe deletes its account
on normal exit or Ctrl+C and retains a removal-event tombstone for SSE readers.
The JSON output omits player/session identifiers. A forced process kill cannot run
cleanup; inspect synthetic probe rows before repeating in that case.

Stop the optional service with:

```powershell
docker compose -f compose.research.yaml --profile udp stop udp
```

## Research policies and remaining work

The listener is an experimental relay, not recovered original server logic.
It stores no positions in MySQL, performs no collision/speed checks, emits no
cached-position snapshot, and provides no acknowledgement or delivery guarantee.
Its 256-peer cap and 120-second receive-idle expiry are local research choices.
An idle player loses UDP registration after that interval until it sends again;
idle recovery must be established before general gameplay use. Session ownership
is possession of the existing session credential; this is not an account/security
audit or a production anti-cheat implementation.

Tests establish one real client plus a synthetic peer, not two Android clients or
iOS compatibility. Follow-up work: two-emulator entry/movement, stationary players,
room transitions, listener restart, NAT/endpoint changes, reconnect sequence resets,
movement authority and initial position synchronization. Compare production UDP
infrastructure separately if another developer has an existing listener.
