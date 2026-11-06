# World Morty release

The two missing collection routes now implement release preview and confirmation:

- `POST /session/owned_morties/attempt-release-multiple` validates without changing
  persistent state and returns the existing complete deck list and active ID.
- `POST /session/owned_morties/release-multiple` independently repeats validation,
  then releases the entire requested batch in one transaction.

Both accept `session_id` and a nonempty JSON list of distinct `owned_morty_ids`.
Single-Morty release uses a one-element list. Both success responses contain
`active_deck_id` and `decks`, with integer deck IDs and ordered Morty ID arrays.
The [native client contract](morty-release-contract.md) establishes that success
removes every requested ID locally, making partial batch success incompatible.
Stats confirmation can be called directly, without a prior preview.

## Persistence and protections

Confirmation prunes the released IDs from every caller-owned deck, preserves
remaining order and empty inactive deck rows, and deletes only the selected
Morty rows and their attacks. It retains the active deck ID. No reward, item,
currency, species collection, historical trade or room-event mutation is added.

Both paths reject an unsafe batch before deletion:

- Invalid session, malformed/empty/duplicate IDs, foreign ownership or globally
  ambiguous owned IDs. Global ambiguity matters because attacks have no owner
  column and the schema has no unique owned-ID constraint.
- Either lock flag, a fight-pit assignment, an outstanding trade request or
  offer, or an ACTIVE battle referencing a selected Morty. Trade existence is
  checked independently because existing trade writers do not set lock flags.
- Loss of the last actual owned member of the active party, or removal of all
  its known living members when it previously had a living member.
- Missing/ambiguous active decks, malformed owner deck data, or loss of the
  final owned Morty. Valid JSON and legacy backslash-escaped JSON are supported.

Ordinary party members can be released when the remaining party is safe. A
blanket prohibition on all deck membership would block the client's Stats flow.
Stale foreign IDs in a deck cannot count as owned survivors. String `"false"`
is parsed as false instead of PHP's boolean cast; unknown lock values fail
conservatively. Fight-pit NULL, empty and literal `null` are treated as absent.

WORLD state is required. The active-party and lock checks have client evidence;
the stronger last-living-member rule, trade/battle guards and exact error statuses
are replacement-server policy. Malformed HP is not counted as known living HP.
Errors use the recognized `FAILED` or `OWNED_MORTY_ID_INVALID` enum envelope.
Original-server validation/status parity is not claimed.

## Transactions and remaining limits

Account, targets, dependencies and decks are checked inside the transaction.
Preview rolls back without update/delete operations; it reserves nothing.
Confirmation never trusts a prior preview, so a subsequently locked or
transferred Morty is rejected. Repeated confirmation after deletion returns an
error without further mutation; there is no tombstone or request-id protocol.

Existing trade, battle, absorb and deck writers do not all use the same locking
protocol. These routes therefore do not claim complete cross-endpoint race
protection. Text columns without lookup indexes can also make row-lock scans
broad; large live deployments need an additive indexing/constraint review.
No migration or deployment is included here.

Lock enforcement in the existing absorb handler is separate outstanding work.
Pending orphan trade offers can conservatively block release until cleaned up;
this feature does not silently delete them. Completed trade history is retained.

## Reproduction

```powershell
py -m unittest discover -s tests/protocol -p test_morty_release.py -v
py tools/research/validate.py
```

Fixtures are UUID-scoped accounts, decks, Morties and dependencies. The original
core test failed while preview was an absent route. Tests exercise read-only
preview, direct confirmation, all-deck cleanup, ownership, locks, party
protections, malformed decks, trade/battle dependencies, state changes after
preview and duplicate confirmations. No existing emulator accounts are reseeded.

For a reversible extra-Morty Android scenario, the existing
`full_restore_fixture.py prepare` helper adds a temporary level-6 Morty alongside
the real healthy party member. Release only that extra Morty. The helper's
`restore` action accepts the already restored original deck and removes the
unused fixture items; reload the client afterward. Raw fixture IDs and captures
remain under ignored `.research`.


## Acceptance results

All 15 release tests pass. An additional malformed-batch run includes rejection
of JSON objects with numeric keys, preserving the distinction from a JSON list.
All three PHP files pass PHP 8.3 syntax checks and protocol validation passes.

Android 2.41.0 selected the temporary level-6 Morty in Your Mortys > Stats >
Release. Cancel preserved its row, attacks and deck, with no confirmation HTTP
request. Reopening and confirming sent one successful slashless POST, removed
only that Morty and its attacks, and returned to the party screen containing the
original healthy Morty. The active deck ID and original Morty were preserved.

A separately labeled synthetic preview request against that same fixture also
returned 200 while preserving the Morty. This is not a claim that Android's
storage preview/multi-select UI was exercised; that UI still needs a live capture.
Both routes have recovered native contracts and integration coverage. See
[the sanitized capture](morty-release-capture.json).

Unused fixture items were removed, the original deck verified restored, and the
primary client reloaded afterward. Raw screenshots, IDs and logs remain ignored.
These are replacement-server results, not surviving original-server captures.
