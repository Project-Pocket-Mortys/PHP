# World healing items

The previously empty `/session/use-item` handler now supports eight world HP
items: Serum, Great Serum, Sensational Serum, Pure Serum, Easter Egg, Pumpkin,
Spicy BBQ Pizza and Breakfast Medley. Exact IDs and amounts come from
[Android item metadata and descriptions](use-item-data.md); request/response
and merge behavior are recovered in [the client contract](use-item-contract.md).

Each successful request heals one owned, conscious Morty up to its maximum HP
and consumes one owned item. The transaction locks the account, target Morty
and item rows. The response contains the changed Morty, actual restored HP and
new inventory quantity, including zero when the last item is consumed. Other
Morties, attacks, inventory, decks and currencies are preserved. No migration
is required; the existing slashless Apache rewrite serves the client path.

Supported amounts are 20, 50 and 200 for the three ordinary serums; Pure Serum
restores all missing HP. Easter Egg and Pumpkin restore 30 each; Pizza and
Breakfast restore 200 each. HP restoration is capped at missing HP. These are
replacement-server rules consistent with client descriptions and UI checks;
they are not a recovered original multiplayer implementation.

## Validation and failure behavior

The route accepts only POST with three nonempty strings: `session_id`,
`owned_morty_id`, `item_id`. Invalid sessions, foreign/missing Morties,
unsupported items, missing/empty inventory, full HP and fainted targets fail
without consumption. Errors use the client's recognized `FAILED` enum envelope.
Exact HTTP status choices are replacement-server policy. Ambiguous duplicate
Morty/inventory records are rejected without mutation because the original
schema permits duplicate logical identifiers.

This implementation requires WORLD state and no existing ACTIVE battle. Party
healing must not silently diverge from the separate HP stored by battle turns.
These guards do not serialize concurrent battle creation, whose handlers do
not yet share the same locking protocol. Battle healing remains separate work.

Requests contain no idempotency token. Concurrent requests cannot overspend the
last item, and ineffective/full-HP retries do not consume anything. Identical
requests that each remain effective with stock available are separate uses;
the server cannot distinguish a delayed retry from another intentional use.
No time-based deduplication or original retry guarantee is invented.

```powershell
py -m unittest discover -s tests/protocol -p test_use_item.py -v
py tools/research/validate.py
```

The core regression failed against the empty handler because it returned no
JSON. All ten final tests pass: all eight healers and caps; complete typed
changed-Morty responses; inventory depletion; invalid/foreign input; failed
uses; battle guards; preservation of unrelated state; and two concurrent
requests competing for the last item. Both PHP files pass syntax checks.

## Android acceptance

Android 2.41.0 on the primary emulator used Serum through Your Mortys > select
Morty > Use Item. A scoped temporary fixture set HP to 5/20; the research client
was reloaded so its cached HP matched the fixture. The initial attempt with
cached full HP was correctly blocked locally before sending a request.

After reload, the real slashless POST returned 200 with `effect_value:15`,
Morty HP 20 and Serum quantity 0. The UI displayed ?You used the Serum on Morty?
and 20/20 HP. Server-side inspection confirmed HP and quantity persisted. The
original fixture was restored afterward: HP 20, Serum quantity 1, same active
deck; the client was returned to the world. Restored inventory will refresh in
client state on the next player-details load/login.

The sanitized [runtime capture](use-item-capture.json) includes request/response,
fixture values, database checks and raw screenshot hashes. Raw images and logs
remain ignored. These are replacement-server observations. Only Serum has a
live Android action capture here; all eight supported items have automated
contract/database tests. Five existing lock tests also pass after integration.

## Remaining item features

Revival, AP restoration, ailment cures, stat/level items, account/general items,
and in-battle items are not yet implemented here. `ItemFullRecover` must not be
treated as plain HP healing because its documented effect includes ailments.
The metadata/data notes distinguish known effects from unresolved percentage
rounding and the single-player arithmetic precedent. The next increment can
extend this endpoint with separately tested effects.
