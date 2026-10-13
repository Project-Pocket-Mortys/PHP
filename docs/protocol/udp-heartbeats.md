# Stationary UDP recipients and HTTP heartbeats

The research relay originally expired every registration 120 seconds after the
last accepted UDP movement packet. The earlier Android capture recorded no UDP
packets during 135 seconds standing in the world, while separate HTTP logs showed
roughly 30-second pings (`udp-idle-results.json`). A new synthetic socket test
directly reproduced the resulting loss of delivery at 125 seconds even when the
stationary recipient kept sending HTTP pings. This is a defect in our research
policy, not recovered original-server behavior.

## Research-only repair

With `PM_RESEARCH_HEARTBEATS=1` and the isolated database settings, the ping handler
records a valid current session in WORLD with an existing room. Its existing POST
success acknowledgement remains unchanged, including for unknown sessions; those
requests do not refresh liveness. Normal deployments without the flag retain the
original handler behavior.

The relay retains an already learned UDP endpoint if its current session, player
and room match a heartbeat received within 120 seconds. A ping never learns an
endpoint or restores an expired one. A fresh UDP packet is still required after
expiry or relay restart. Existing recipient checks continue to reject rotated
sessions, deleted accounts, changed rooms and non-WORLD states. Sequence checks,
packet format, peer cap and lack of movement authority are unchanged.

The observed ping constructor is
`NetworkSessionAPI.<SendPingCo>d__35.MoveNext`, ARM64 RVA `0x17b79c4`, with
`session_id` and `type` fields. Repeating ping code at `0x17b7c10` references
`DEFAULT`. See `native-transport.json` and the existing room-lifecycle Ghidra
runner. This supports the request fields; it does not establish original UDP
liveness policy. We deliberately do not use `users.last_seen`, because SSE and
unrelated database updates refresh it without receiving a client heartbeat.

## Additive migration and startup

`tools/research/server/migrations/001-client-heartbeats.sql` creates
`research_client_heartbeats`, one row per account, containing its latest session,
room and server receive timestamp. A foreign key removes the row on account
deletion. The original SQL dump and existing tables are unchanged.

Compose now runs the isolated `research-init` migration service before web and
UDP. Migrations are ordered and repeatable; a migration failure blocks dependent
service startup. The migration runner refuses non-CLI and non-research database
settings. No production deployment or production migration was performed.

```powershell
docker compose -f compose.research.yaml --profile udp up -d --build
# Restart an already-running relay after editing its PHP source:
docker compose -f compose.research.yaml --profile udp restart udp
py -m unittest discover -s tests/protocol -p test_heartbeats.py -v
py -m unittest discover -s tests/protocol -p test_udp_relay.py -v
$env:PM_RUN_SLOW_UDP='1'
py -m unittest discover -s tests/protocol -p test_udp_idle.py -v
Remove-Item Env:PM_RUN_SLOW_UDP
```

The slow test uses the real 120-second policy, three disposable peers and a
125-second idle interval. One sender keeps moving, one stationary recipient
sends HTTP pings every approximately 20 seconds, and a second stationary
recipient sends neither. It checks continued delivery to the pinging peer,
expiry of the silent peer, lack of revival from HTTP alone, and recovery after a
new UDP packet. Default test discovery skips this slow test. All fixtures are
additive and preserve the emulator account.

Validation: five heartbeat/migration tests, eleven existing UDP relay tests and
the one slow test pass (17 checks total). The slow test completed in 128.268
seconds including setup/cleanup. PHP syntax, Compose configuration and evidence
hash validation also pass. The initial migration test fixture omitted a required
`zone_id`; the fixture was corrected before the successful run.

The migration test imports the checked-in schema into a random temporary database
inside the isolated MariaDB container, applies the migration twice, compares the
users table definition and verifies cascading deletion, then drops only that
temporary database.

## Limits

This is synthetic replacement-server verification. The Android emulator was not
connected during this repair; live Android idle delivery and two-emulator testing
remain outstanding. NAT mapping expiry, app background behavior, same-room
leave/rejoin generations, endpoint changes and restart recovery still need work.
The 120-second grace period and reuse of HTTP liveness are research policies.
The relay checks idle peers against the database; no performance/load claim is
made for the bounded 256-peer implementation.
