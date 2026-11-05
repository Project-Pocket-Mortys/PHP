# Owned Morty lock client contract

This is static client evidence for implementing the missing
`/session/owned_morties/lock` handler. It is not an original-server capture or an
Android UI validation result. No gameplay handler or database row was changed
during this investigation.

## Reproduce

```powershell
wsl -- bash tools/research/ghidra-morty-lock.sh
```

The wrapper uses the existing targeted Ghidra driver in the default WSL
distribution. It verifies Android 2.41.0 ARM64 `libil2cpp.so` SHA-256
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`
before analysis. Output is ignored at `.research/ghidra-morty-lock.json`; the
pass exported seven entries without an `error` property, including two
`GetMortyData` overloads. Ghidra's image base is `0x100000`: the addresses below
are native RVAs, not Ghidra image addresses. The shell wrapper passes `bash -n`.

Independent bounded ARM64 inspection with Capstone confirmed the callback's
success comparison, requested lock-byte write, deck-array consumption, and
active-deck write. The existing driver does not import managed parameter types;
generic parser and deck-consumer pseudocode includes exception paths extending
into adjacent bodies. Conclusions below use their initial normal paths and
cross-check against managed fields and bounded callback instructions.

## Request and callback wiring

`NetworkPlayerAPI.LockMorty(string mortyNetId, bool isLocked,
Action<eReleaseMortyError> callback)` is at RVA `0x17a3444`.
`docs/protocol/native-transport.json` records:

| Evidence | Native RVA |
|---|---|
| Endpoint literal `/session/owned_morties/lock` | `0x17a3570` |
| `AnonymousType37<string,string,bool>` constructor metadata | `0x17a35d8` |
| Anonymous request object constructor call | `0x17a35ec` |
| `<LockMorty>b__0` callback metadata | `0x17a363c` |
| `NetworkHTTP.Request` call | `0x17a3678` |

The request object is assigned to `NetworkHTTPRequest.postData` at offset
`0x20`. AnonymousType37 fields in `.research/dumper/dump.cs:3542` and the
constructor's argument flow establish this body:

```json
{"session_id":"<current session>","owned_morty_id":"<mortyNetId>","is_locked":true}
```

`is_locked` is the requested boolean state, including `false` for unlock; this
is not a toggle request. Endpoint and request fields are high-confidence static
evidence, strengthened beyond the linear candidates in `parser-mapping.json`.

## Success response consumed by this operation

The callback is
`NetworkPlayerAPI.<>c__DisplayClass43_0.<LockMorty>b__0` at RVA `0x17a8234`.
It calls shared `NetworkDefs.ParseHTTPResponse<Int32Enum,object>` at
`0x17a82c8`, with specialized metadata loaded at `0x17a82b8` identifying
`ParseHTTPResponse<eReleaseMortyError,PlayerReleaseMortyResponse>`.

`PlayerReleaseMortyResponse` in `.research/dumper/dump.cs:31355` has exactly:

| Field | Type | Managed object offset |
|---|---|---|
| `active_deck_id` | `int` | `0x10` |
| `decks` | `Dictionary<string,object>[]` | `0x18` |

Its constructor is RVA `0x17ab114`. The shared response parser at RVA
`0x1b572a4` checks the operation's error enum and deserializes the response JSON
directly into the response type using JsonFx. A success response should therefore
have the following shape, with actual persisted values:

```json
{"active_deck_id":0,"decks":[{"deck_id":0,"owned_morty_ids":["<owned Morty ID>"]}]}
```

The example's slot zero is illustrative; return the account's actual active
deck ID and complete deck contents. Do not replace existing decks with the
example. Bounded ARM64 callback instructions establish the consequences:

| Instruction RVA | Effect |
|---|---|
| `0x17a82ec` | Compare parsed error enum with `3` (`NONE`) |
| `0x17a830c` | Find the owned Morty using the closure's requested ID |
| `0x17a8314` / `0x17a8318` | Copy requested `isLocked` byte to Morty `isLocked`, offset `0x6d` |
| `0x17a8334` / `0x17a833c` | Read response `decks`, call `MPPlayerData.SetDecks` |
| `0x17a8358` / `0x17a835c` | Copy response `active_deck_id` to player `activeDeckIndex`, offset `0xd8` |
| `0x17a8374` | Invoke the player API change delegate when present |

`MPPlayerData.SetDecks`, RVA `0x1590e58`, clears existing local deck entries,
then consumes each record's `deck_id` and `owned_morty_ids`. Returning an empty
array would clear the client's decks. Returning a missing/default
`active_deck_id` can reset its active index. The lock callback does not consume
an `owned_morties` response field: it applies the requested lock value locally
after successful parsing. These response requirements are high-confidence
static evidence.

## Error contract

The dumped `eReleaseMortyError` enum is:

| Literal | Numeric value |
|---|---|
| `UNKOWN` (client spelling) | `0` |
| `OWNED_MORTY_ID_INVALID` | `1` |
| `FAILED` | `2` |
| `NONE` | `3` |

On a non-success HTTP response, shared `ParseHTTPError<Int32Enum>` at RVA
`0x1b569d8` deserializes a dictionary and reads `error.code` as a string, then
checks/parses that enum name. The response object's `isSuccess` field is offset
`0x1c`, independently recorded in `NetworkHTTPResponse.cs`. An appropriate
client-recognized error shape is:

```json
{"error":{"code":"OWNED_MORTY_ID_INVALID"}}
```

Unrecognized enum names fall back to zero on the observed normal error path.
The original server's exact status codes, validation decisions, and distinctions
between malformed, unauthorized, missing, and foreign-owned IDs remain unknown.
Using a known enum error with suitable replacement-server HTTP status is an
implementation policy, not a recovered original-server rule.

## Minimal persistence implementation

Authenticate `session_id`, validate `owned_morty_id` and the boolean state,
and update only the Morty belonging to that session's player. Persist
`owned_morties.is_locked` as `'0'` or `'1'`: the existing column is
`varchar(255)` (`pocket_mortys.sql:514`), and those values work with both PHP
boolean casts and `FILTER_VALIDATE_BOOLEAN` serializers. No schema migration
is necessary. `lib/active_deck.php` already normalizes this field for snapshots;
the other read paths also expose it.

Return the account's actual `active_deck_id` and full deck list, decoding each
stored `owned_morty_ids` JSON array and retaining integer deck IDs. This operation
has no client-proven requirement to alter decks, change active deck, or emit an
SSE event. Owner scoping, validation, and preserving deck state are the minimal
consistent replacement-server implementation; exact original-server lock side
effects are not established by this inspection.

Persisting the lock is not universal lock enforcement. In particular,
`session/owned_morties/absorb/index.php` currently selects absorption candidates
by ownership without checking `is_locked`, then deletes them. Protecting locked
Morties from absorption, release, trade, and other destructive actions requires
separate implementation and tests. Do not claim those paths are protected by
adding this endpoint alone.
