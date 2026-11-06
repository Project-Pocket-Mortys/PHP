# Research-gated shared startup delivery

This connects [internal shared startup](shared-battle-startup.md) to an opt-in
SSE transport. Public invitation acceptance remains 501 on both servers. The
gate supports startup/initial readiness and safe interruption testing; it does
not implement human moves, combat timers, rewards or native battle resume.

## Native boundary

The [bounded native pass](shared-battle-stream-contract.md) verified 36 methods
and 12 relocation mappings using default WSL, REA 6.8.0 and targeted Ghidra.
The game disables automatic retry on the same EventSource. `session:end` with
nonempty `data: {}` selects SERVER_ENDED, but does not itself close the source.
Flush it and finish the HTTP stream. On closure, the client clears battle state,
uses its server-message/sign-in flow, starts a fresh connection, then returns to
the world after successful room join. Bare EOF uses a different reason and does
not itself select that automatic sign-in path.

These are statically established control paths. Real HTTP/SSE tests verify
framing, privacy and EOF; they are not an Android UI recovery capture. Neither
this path nor the new database records establish transparent human battle resume.

## Connection identity and attempts

`PM_RESEARCH_SHARED_BATTLE_STREAM=1` enables the bridge. Other values leave it
disabled. Disabled calls do not read or write transport tables; the normal server
retains its existing ready and SSE behavior. Migration 012 adds a per-player
stream registry, immutable per-battle participant bindings and durable per-intent
attempts. Only SHA-256 digests of sessions enter those records, never raw tokens.

An authenticated stream registers a fresh UUID under its user lock. Startup
activation holds both ordered user locks and requires two current authenticated
streams whose heartbeats are within ten seconds. It binds their identities in
the same transaction as both users, startup/intents and accepted invitation.
Failed binding or expired preparation rolls back everything. Bindings do not
follow a reconnect; a previously bound stream must be replaced before another
startup can use it.

Polling is global per recipient, independent of room cursor, fresh snapshots and
room placement. It validates both claims, startup/view/intent integrity, current
authentication and bound streams. One intent attempt is inserted and committed
before returning `battle:start`; repeated polls do not return it again. The
payload is exactly the stored recipient perspective. No start is inserted into
the room event queue. A third account receives neither participant's data.

This is **at-most-once send attempt**, not exactly-once delivery. A failure after
commit can lose the event. There is no native receipt nonce with which to prove
delivery. Initial ready is accepted only after that participant's attempt and
while both bound connections remain valid; retries do not renew the fixed lease
or publish a combat timer.

## Interruption policy

A new connection during active startup atomically cancels the old shared startup
before registering its new identity. It restores both database users to WORLD,
releases the exact claims and retires both intents. The replaced old connection
closes silently, so it cannot restart an old client or cancel a newer startup.
The other current bound connection receives `session:end {}` and EOF on its next
poll. Current streams also cancel/close on stale or revoked peers and startup
expiry. Raw authentication revocation or supersession closes the obsolete stream
without an automatic reconnect instruction.

Generation validation precedes cleanup; an old stream cannot drain a newer
intent or restore users from a newer reservation. Cancellation preserves save
resources, HP/AP, room membership, and `last_seen`. No fabricated human terminal
outcome, victory or reward is emitted. Corrupt active records fail closed; the
existing isolated startup worker remains available for disconnected expiry.

The stream profile does not start that scheduler. For interactive client tests,
run it in a separate terminal so expiry is handled even if both server streams
disappear. A single bounded cleanup pass uses the same command with `--once`:

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/friend-battle-startups.php
```

## Isolated reproduction

The standard localhost:8087 web service leaves the gate off. A separate localhost
service explicitly enables it, using the same isolated database and source tree:

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/migrate.php
docker compose -f compose.research.yaml --profile shared-battle-stream up -d --no-deps stream-web
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_friend_battle_transport.py -v
```

The sidecar listens only on `127.0.0.1:8089`. Tests use fresh UUID accounts and
scoped faults; they never activate the retained emulator accounts. Gate-enabled
CLI calls use `docker compose ... exec -T -e PM_RESEARCH_SHARED_BATTLE_STREAM=1
web php ...`; ordinary CLI and the primary service remain disabled. Run database
fixtures serially. The explicit integration runner adds the optional suite with
`--shared-battle-stream`; its default selection does not require the sidecar.

Migration 012 was applied twice against a schema-only copy, checking primary
and unique stream/delivery keys, before isolated application. All 16 new cases
passed in 120.259 seconds, including real cross-room delivery, third-account
privacy, primary-server exclusion, readiness, reconnect end/EOF, peer failure,
immutable bindings, superseded generations and attempt-insertion rollback.

The 53 existing startup, SSE session/membership/room/privacy/snapshot, invitation
and wild-ready regressions passed in 303.607 seconds: 69 distinct verified cases.
PHP 8.3 lint passed all 63 changed/new PHP files including prerequisites, and
protocol/source fingerprints, Python, native evidence and whitespace checks
passed. Both original two-account save guards passed. All nine shared
preparation/startup/transport tables were empty after scoped fixture cleanup.
The temporary stream-web service was stopped after verification; the normal
localhost:8087 service and emulator redirection were retained.

This branch starts at main `9ff1a11` with prerequisite PR #44 `b934313` explicitly
fast-forwarded. README-completed features and attribution are retained; no
production deployment or emulator redirection is included.

## Remaining acceptance work

Capture the actual Android intro, initial ready, `session:end` and fresh join on
dedicated test accounts before claiming native recovery works end to end.
Validate packet loss, slow startup/snapshots and missing-event behavior against
the client UI. Keep public approval disabled while human selections, later-phase
ready identity, resolution, forced switches and terminal behavior are incomplete.
