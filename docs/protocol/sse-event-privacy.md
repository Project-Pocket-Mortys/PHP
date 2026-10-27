# SSE recipient privacy

This repair establishes replacement-server behavior from existing producers and
recipient columns, not original-server traffic. Client battle formulas and
participant-specific multiplayer battle payloads remain unresolved.

## Evidence and policy

`lib/events.php` persists `only_show_to_player_id`. The existing
`session/battle-wild-morty`, `session/battle/ready`, and `session/battle/move`
producers pass the initiating player as recipient. Start payloads include
inventory/currency and turn results include rewards. An opponent mentioned in
JSON is therefore not evidence that they may receive that entire payload.

Previously SSE ignored the explicit recipient column. Its legacy private-event
fallback inspected an empty payload before decoding the stored event. Fresh SSE,
join-room and room-details entity snapshots also ignored explicit recipients.

`lib/event_visibility.php` now applies one policy across those readers:

| Metadata | Visibility |
|---|---|
| Nonempty explicit recipient | Only that player; overrides conflicting legacy target |
| Null/empty explicit recipient on the three private battle types | Only nonempty legacy `player_id` |
| Neither recipient on a private battle event | Nobody; ambiguous private data is withheld |
| Other events without explicit recipient | Public within the room; `player_id` is the subject |

The three private types are `battle:start`, `battle:turn-result`, and
`battle:move-timer-started`. The producer now writes explicit recipients for all
three. Payload participant IDs never grant access. Snapshot filtering covers
pickups, wild Morties and bots. Event names, response shapes and payloads are
unchanged. Filtered queue rows still advance the subscriber cursor.

## Reproduction

With the isolated Compose backend running and migrations applied:

```powershell
py -m unittest discover -s tests/protocol -p test_sse_event_privacy.py -v
```

The original four regression scenarios failed before repair. All five final
tests pass after integration with the membership-generation repair:

- All three battle types, explicit/legacy/empty/conflicting/missing recipients,
  incidental payload participants, public subjects and restricted public events.
- Fresh SSE entity snapshots for two players in one room.
- Join-room and room-details snapshots for those players.
- Producer recipient metadata for all three private types.
- Cursor progress past 205 hidden events, exceeding the 200-row poll limit.

Fixtures use random accounts and rooms and remove only their own records. These
are HTTP/SSE replacement-server tests, not Android battle captures. Existing
membership tests (four) and join snapshot ownership test (one) also pass.

## Remaining limits

This does not prove every future event type's audience. New private event types
need explicit metadata and tests. Missing legacy recipients cannot be recovered
from incidental JSON references. Unused `lib/room_entities*.php` helpers are not
active snapshot consumers and were not changed. Snapshot/publication races,
shared session cursors and original reconnect semantics remain open. See
[membership generations](sse-rejoin-generation.md) for the separate rejoin repair.
