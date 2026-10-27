# Join snapshot Morty ownership

The join-room response previously resolved each active deck's Morty IDs without
checking the owner. A stale deck referencing another player's Morty could expose
that Morty's details under the wrong player in the join snapshot. The response
now scopes that lookup to the snapshot player's `player_id`, matching the
existing room-details query and active-deck helper. Paths and response fields are
unchanged; valid owned Morties retain their HP and optional-field encoding.

The additive regression creates two synthetic accounts whose active decks each
reference both Morties. Before the repair, both snapshot entries included a
foreign Morty (two failing subtests). Afterward, each contains only its owner's
Morty. The fixture removes only its own accounts, room, decks, Morties and events.

```powershell
py -m unittest discover -s tests/protocol -p test_join_room_ownership.py -v
py -m unittest discover -s tests/protocol -p test_sse_rooms.py -v
```

Both checks pass (one ownership test and three SSE room-transition tests), as do
PHP syntax and protocol evidence validation. No schema change is required.

This is a confirmed inconsistency between replacement-server snapshot handlers,
not original-server evidence. Normal deck editing already checks ownership; the
repair protects reads of stale or inconsistent deck contents rather than
asserting that the ordinary client can create such a deck.
