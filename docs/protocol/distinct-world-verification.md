# Distinct-world Android verification

This follow-up uses two Android 2.41.0 diagnostic clients, the isolated PHP
backend and optional stable UDP adapter. World 2 is an explicitly synthetic
empty room; this does not recover spawning, combat, progression or original
server authority. Asset provenance is recorded in [world2-fixture-evidence.md](world2-fixture-evidence.md).

## Recorded result

[Sanitized results](distinct-world-results.json) retain phase timestamps, packet
counts, translation checks and hashes of ignored raw artifacts. The initial
attempt stopped at the dialogue exception; after restoring, restarting and
retrying with visually checked dismissal, both clients loaded world 2 normally.
No tutorial flag, client binary or response schema was changed to bypass it.

| Phase | Primary / peer worlds | Primary sent / received | Peer sent / received |
|---|---|---|---|
| Split after primary departure | 2 / 1 | 3 / 0 | 3 / 0 |
| Both in destination | 2 / 2 | 5 / 4 | 4 / 5 |
| Split after primary return | 1 / 2 | 3 / 0 | 4 / 0 |

All three captures passed their defined checks with zero kernel drops and
unchanged membership, sessions and owned UDP socket identities within each
capture. Every destination-phase outgoing packet matched its expected translated
payload in the other guest capture. Both destination screenshots show the other
player's name/avatar. After the primary returned, the peer's screenshot no longer
shows the primary. The probes bracket transitions rather than continuously
capture them; races during leave/join and raw SSE ordering remain untested.
Initial and post-restoration same-room movement checks are recorded separately.

## Reversible fixture

`seed-world-transition.php --apply` requires the isolated web environment,
exactly two selected level-1 accounts, no existing world-2 room and no conflicting
recovery snapshot. It transactionally raises their levels to 5 and creates one
UUID world-2 room using the existing emulator transport. This enables the
client's level check for Plumbubo Prime 51b. Zone `[1,1]` is required opaque
schema fixture data; the recovered Android response model has no `zone_id`.

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/seed-world-transition.php --apply
docker compose -f compose.research.yaml cp web:/tmp/pm-world-transition.json .research/world-transition-recovery.json
```

Defaults select PMResearch01/02. `--players=name1,name2` is for separate synthetic
fixtures. The snapshot stores original account identities/levels and the exact
created room, not login credentials. Keep its ignored host backup and do not
recreate the web container while the fixture is active: container `/tmp` is
transient. If recreation is unavoidable, restore the matching backup to its
original `/tmp/pm-world-transition.json` path before invoking `--restore`.

Restart each research client and select Multiplayer to load the temporary
eligibility. Inspect/dismiss the introductory popup and running dialogue before
movement; waiting for one to close before tapping the next worked on the retry.
This timing is an observed workaround, not an established fix for the intermittent
[dialogue exception](fast-shoes-dialogue-evidence.md).

Move to the portal, face it and press A. Select Plumbubo Prime 51b, then Teleport.
Selecting a portal menu leaves the current room; selecting the world alone is
not the final confirmation. Confirm membership in the database and the visible
world before collecting each phase.

## Bounded capture commands

```powershell
# Both clients initially in world 1:
py tools/research/probe_android_world_rooms.py --expect same --output-dir .research/emulator/world-rooms-baseline-next
# Primary has moved to world 2, peer remains in world 1:
py tools/research/probe_android_world_rooms.py --expect different --output-dir .research/emulator/world-rooms-split-next
# Peer joins primary in world 2:
py tools/research/probe_android_world_rooms.py --expect same --output-dir .research/emulator/world-rooms-destination-next
# Primary returns to world 1 while peer remains in world 2:
py tools/research/probe_android_world_rooms.py --expect different --output-dir .research/emulator/world-rooms-return-split-next
```

The probe does not change worlds or seed/reset accounts. It validates device and
room preconditions, captures UDP for 16 seconds, moves each client right then
left, and compares complete expected translated payloads using identities only
in memory. Results omit credentials, packet bytes and endpoints. Raw captures
remain ignored. Each same-room phase requires actual outbound traffic and a
matching translated packet received in each direction; each separate-room phase
requires actual outbound traffic from both and no inbound UDP-5055 packets.
Both scenarios also require unchanged membership/sessions/socket identities
and zero reported kernel capture drops. Exit status 1 means acceptance failed.

This is packet delivery evidence. It does not prove that the game applied every
packet, nor raw SSE event order or privacy for every event type. No syscall trace
is attached in these phases. Screenshots are additional visual evidence, and
scheduled movement does not guarantee exact reversal of position near obstacles.

## Restore

Return both clients to Mortyland/world 1 through their portals before restoring:

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/seed-world-transition.php --restore
```

Restore refuses occupied rooms, changed room configuration, different identities
or unexpected levels. It restores the original level 1, removes only queued
events for the owned fixture room and deletes that empty room. It does not reset
accounts, sessions, XP, currency, inventories or client saves. Restart the clients
and select Multiplayer again so their cached level matches the restored database.

Two additive fixture tests cover repeated apply/restore, occupied-room refusal,
existing-world/level guards, preserved account data and scoped queue cleanup.
They use unique accounts, skip when another fixture is active, and never reseed.

```powershell
py -m unittest discover -s tests/protocol -p test_world_transition_fixture.py -v
```
