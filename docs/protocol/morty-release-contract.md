# Owned Morty release client contract

Static evidence from Android 2.41.0 ARM64 establishes the two list operations
below. This is not an original-server capture or an Android UI validation.
Original-server validation policy and HTTP status selection remain unknown.

## Reproduce and evidence

```powershell
wsl -- bash tools/research/ghidra-morty-release.sh
```

The wrapper uses the existing targeted Ghidra driver, which verifies
`libil2cpp.so` SHA-256
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.
Output: ignored `.research/ghidra-morty-release.json`. The completed pass
exported 24 functions without `error` properties. The wrapper passes `bash -n`.
Ghidra uses image base `0x100000`; addresses below are native RVAs.

Supporting sources are `.research/dumper/dump.cs`,
`docs/protocol/native-transport.json`, and the shared parser evidence in
`docs/protocol/morty-lock-contract.md`. Managed parameter types are not imported
into Ghidra. Some UI exception paths merge into adjacent bodies; the conclusions
below use normal paths, managed fields, and named calls, not those merged tails.

## Requests

| Operation | Method RVA | Endpoint |
|---|---|---|
| Preview / eligibility check | `0x17a3688` | `/session/owned_morties/attempt-release-multiple` |
| Confirm deletion | `0x17a38fc` | `/session/owned_morties/release-multiple` |

Both public methods accept `List<string> mortyNetIds` and
`Action<eReleaseMortyError> callback` (`dump.cs:31076`, `31079`). They construct
`AnonymousType38<string,List<string>>` and assign it to request `postData`.
AnonymousType38 has exactly `session_id` and `owned_morty_ids`
(`dump.cs:3643`). The constructor calls are at `0x17a3864` and `0x17a3a8c`;
specialization metadata appears at `0x17a3854` and `0x17a3a7c`.

```json
{"session_id":"<current session>","owned_morty_ids":["<owned Morty ID>"]}
```

The list contains instance/network IDs, not species IDs, and may contain one
element. There is no scalar `owned_morty_id` body in these two methods.
No preview token or returned selection is passed to confirmation.

## Responses and local effects

Both callbacks specialize
`NetworkDefs.ParseHTTPResponse<eReleaseMortyError,PlayerReleaseMortyResponse>`.
The metadata loads are at `0x17a8494` and `0x17a85c8`; shared parser calls are
at `0x17a84a4` and `0x17a85d8`. `PlayerReleaseMortyResponse`
(`dump.cs:31355`) has exactly:

| Field | Type | Managed offset |
|---|---|---|
| `active_deck_id` | `int` | `0x10` |
| `decks` | `Dictionary<string,object>[]` | `0x18` |

The shared parser deserializes the successful JSON directly using JsonFx.
A compatible response has the existing deck shape:

```json
{"active_deck_id":0,"decks":[{"deck_id":0,"owned_morty_ids":["<remaining ID>"]}]}
```

Zero and the shown list are examples. Return actual persisted deck IDs,
membership arrays, and the actual active index.

Preview callback `0x17a8410` parses the response and forwards the error to its
callback. It never reads the parsed response object and never changes Morties,
decks, or active deck. Its response contains no consumed allowed subset,
protected list, or IDs to delete. Supplying the common response shape is
compatible; those fields do not drive preview UI behavior.

Confirmation callback `0x17a8544` changes local state only when the parsed enum
equals `3` (`NONE`). Its normal success path is:

1. `MPOpponentData.RemoveMortys` at `0x17a8600`, receiving the closure's
   **original requested list** (`0x18`). This resolves every requested ID and
   removes its Morty object from the local owned list.
2. `MPPlayerData.SetDecks` at `0x17a8624`, receiving response `decks`.
3. Assign response `active_deck_id` to player `activeDeckIndex` (`0xd8`).
4. Invoke the player API change delegate when present, then the request callback.

The response must be nonnull on success. `SetDecks` (`0x1590e58`) clears local
decks and rebuilds them from `deck_id` and `owned_morty_ids`; an empty array
clears the local decks. Confirmation does not apply response `owned_morties`
or a returned deletion list. A success response for a partially deleted batch
would make the client remove the entire request locally. Atomic rejection of
an unsafe batch is therefore a replacement-server consistency requirement.

## Normal UI paths and protections

The single Release button uses the list API. In
`MPMortyStatsState.ReleaseConfirmButtonClickedHandler` (`0x15bfcb0`), confirming
button index `1` creates a one-element `List<string>` containing the selected
Morty's network ID and calls `ReleaseMortys` directly. This path does not call
preview first; confirmation must perform its own validation.

Storage's `ReleaseConfirmButtonClickedHandler` (`0x15f18b0`) calls
`AttemptReleaseMortys` with selected IDs. Its callback (`0x15f2034`) proceeds
only on `NONE`; the continuation (`0x15f219c`) calls confirmation immediately
for fewer than two selections, otherwise displays an additional confirmation.
`MPStorageEditDeckState.ReleaseMortys` (`0x15f1bec`) submits the selected IDs to
the list confirmation API.

Recovered UI checks must be distinguished from original-server policy:

* `MPOpponentMortyData.isLocked` is byte `0x6d`; `isTradeLocked` is `0x6e`
  (`dump.cs:12718`). Stats `Refresh` (`0x15bffe4`) enables Release button index
  `0` only when both are false (and release is allowed for that stats context).
  Storage `IsAllSelectedMortysUnlocked` (`0x15f5470`) requires a nonempty
  selection with both flags false on every selected Morty.
* `MPPlayerData.IsMortyInParty` (`0x15916f4`) checks ID membership in
  `decks[activeDeckIndex]`. It does not search
  every saved deck. `GetActiveDeckCount` delegates to the active deck's count.
* Stats `TryRelease` (`0x15c0c3c`) blocks when the selected Morty is in the
  active party and the active deck count equals one, displaying
  `MORTY_STATS_RELEASE_FAIL_LAST_MORTY`. It permits the event when the count is
  greater than one or the selected Morty is outside the active party. A further
  branch for an in-party selection with count at most zero permits fainted
  Morties and otherwise displays `...LAST_ALIVE_MORTY`; this is the observed
  branch, not evidence of a comprehensive last-alive check in this stats method.
* Storage `TryRelease` (`0x15f58f4`) counts selected active-party members and
  accumulates whether **all selected Morties** are fainted. It blocks when the
  selected party count equals the active deck count. Otherwise, if any selected
  Morty is in the active party, not all selected Morties are fainted, and active
  alive count is less than two, it displays `...LAST_ALIVE_MORTY`.
  `GetActiveDeckAliveCount` counts active-deck Morties with current HP greater
  than zero. This is not a calculation of the post-release alive count.
* Storage `IsAllMortyValidForRelease` (`0x15f5670`) checks selected active-party
  count is less than active deck count. The storage menu also doubles as an
  edit-deck removal control: single-selection index `1` removes a Morty already
  in the editing deck locally; actual multi-selection release requires all
  selected Morties in storage and unlocked. Do not interpret that control as
  proving a server-wide prohibition on releasing every saved-deck member.

These checks support preserving an active party and protecting both lock flags.
They do not establish the original server's exact validation, nor a universal
rule rejecting every Morty found in any deck. A stricter server-side rule
preserving at least one living active-party member is an implementation policy,
not an exact reconstruction of every UI branch.

## Errors and implementation boundary

The shared `eReleaseMortyError` (`dump.cs:30181`) is `UNKOWN=0` (client spelling),
`OWNED_MORTY_ID_INVALID=1`, `FAILED=2`, `NONE=3`. The shared error parser reads
`error.code` as an enum-name string from a non-success HTTP response:

```json
{"error":{"code":"OWNED_MORTY_ID_INVALID"}}
```

Preview and confirmation both forward this enum to their UI callbacks. No
separate locked/deck/last-Morty error enum is recovered. Owner scoping, malformed
list handling, duplicate handling, transactional deletion, deck cleanup, and
choice between `FAILED` and `OWNED_MORTY_ID_INVALID` are replacement-server
decisions. Preview should not mutate persistence; confirmation must independently
revalidate and return the complete post-deletion deck state.
