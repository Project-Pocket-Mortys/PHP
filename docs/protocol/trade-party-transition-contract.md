# Android 2.41.0 trading reservations and party transitions

Recovered 2026-11-06 using REA 6.8.0 and bounded ARM64 client methods. This
establishes client predicates and wire consumption. It does not establish the
original service's database transactions, validation order, or HTTP status
mapping. See [listing eligibility](trade-listing-protection-contract.md),
[reservation flags](trade-lock-lifecycle-contract.md), and
[offer acceptance](native-trade-response-contract.md).

## Reproduction and evidence boundary

From repository PowerShell, using the default WSL distribution:

```powershell
wsl.exe -- bash tools/research/ghidra-trade-party-transitions.sh
```

The wrapper requires REA 6.8.0, inspects the ELF, and invokes targeted Ghidra
12.1.4 with `-noanalysis` in a disposable project. It does not build a full
analysis index. Each run refuses an existing output directory. Its bounded
instruction exporter uses the explicit Windows executable
`C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe`; override
its WSL path with `POCKET_WINDOWS_PYTHON` if needed.

The final ignored receipt is
`.research/trade-party-transitions-20261106T235331Z`, containing
`rea-version.txt`, `artifact.json`, `ghidra.log`, `ghidra.json`, `methods.json`,
and `arm64.txt`. It contains 24 methods, including the shared HTTP success
accessor as a bounded instruction supplement. Earlier successful receipts
ending `235054Z` and `235208Z` remain supporting evidence.

ELF SHA-256 is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`;
IL2CPP metadata version is 31, metadata SHA-256 is
`b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`.
Addresses below are native RVAs; Ghidra displays image base `0x100000`.
Matching `dump.cs` supplies field offsets, enums and managed signatures;
`script.json` supplies names and next-entry method bounds. Some decompiler
exception paths flow into adjacent methods despite the supplied body, so only
instructions within `methods.json` bounds establish behavior. No PHP, test,
database, emulator or endpoint mutation was needed for this research.

## Adding a Morty, saving a deck, and activating a saved deck

The two flags on `MPOpponentMortyData` are independent: manual/favorite
`isLocked` at `+0x6d`, and reservation `isTradeLocked` at `+0x6e`.

`MPStorageEditDeckUI.AddMortyToDeck` (`0x15f4254..0x15f4510`) first checks
that the candidate deck contains fewer than five Morties. Its exact reservation
check is:

```text
0x15f42d4: ldrb w8, [x19, #0x6e]
0x15f42d8: cbz w8, 0x15f4320
0x15f42e4: bl TextDefs.get_MORTY_STORAGE_EDIT_DECK_DIAL_WITHDRAW_FAIL_TRADE_LOCKED
```

The false branch appends the Morty object to `deckMorties` (`+0xa8`); the true
branch shows the trade-locked message and does not append it. This applies to
editing saved decks as well as the active deck. This method reads no manual
lock byte. The ordinary single-select action reaches it through menu action 0
in `HandleSingleSelectMenuInputs` (`0x15f5dd0..0x15f5de4`).

There is a separate UI nuance: `MortyCellSelectedHandler`
(`0x15f4c24..0x15f502c`) uses `IsAllSelectedMortysUnlocked`
(`0x15f5470..0x15f5670`) to enable menu buttons. That predicate requires a
nonempty selection and both flags false for every selected Morty. In
single-select mode it participates in enabling the withdraw/add button for a
Morty outside the edited party. Thus the normal menu can disable withdrawal
for a manual favorite, even though the lower-level add method has no manual
guard. This is not evidence for rejecting all server deck edits containing
favorites: the save and activation paths below have no such predicate, and an
existing party member can be retained or reordered.

`MPStorageEditDeckState.SaveDeck` (`0x15f09b0..0x15f0de0`) projects each
Morty's instance `netId` (`+0x18`, selector `0x15f28fc..0x15f2914`) and
compares the ordered IDs with the saved deck. An unchanged sequence returns
success without a network call. For a changed active deck, it requires at
least one non-fainted Morty (predicate `0x15f2914..0x15f293c`), then calls
`NetworkPlayerAPI.EditDeck`. It does not reread either lock flag. Its success
callback (`0x15f2c74..0x15f2cc8`) recognizes `NONE=5`.

`MPStorageDecksState.UIWithdrawHandler` (`0x15ee0d4..0x15ee300`) checks
nonempty deck count, at least one living Morty, and owned deck slot before
calling `NetworkPlayerAPI.SetActiveDeck` at `0x15ee2f8`. It contains no lock
predicate. Consequently the recovered activation path does not prevent
activating an inactive saved deck containing a Morty that became reserved
after that deck was saved. The direct request constructor adds no predicate.
The UI callback (`0x15ee4ac..0x15ee4d4`) recognizes `NONE=3`.

## Existing deck wire contract

The matching metadata contains no `NetworkDeckAPI` class. Both operations
belong to `NetworkPlayerAPI`:

| Operation | Constructor bounds | Path and post properties |
| --- | --- | --- |
| Edit deck | `0x17a2ce8..0x17a2f28` | `/session/deck/edit`: `session_id`, integer `deck_id`, `owned_morty_ids` |
| Activate deck | `0x17a3b24..0x17a3d70` | `/session/deck/set-active`: `session_id`, integer `deck_id` |

Edit invokes anonymous Type35's concrete constructor
(`0x1cd7050..0x1cd7090`) with the session, deck ID and string-list argument;
activation invokes Type39 (`0x1cdb65c..0x1cdb68c`) with session and deck ID.
Metadata names the properties above. No new reservation, actor or Morty flag
property is sent. The existing shared JSON request serialization is described
in the linked trade response contract.

| Error enum | Exact names and values |
| --- | --- |
| `eEditDeckError` | `UNKOWN=0`, `DECK_ID_INVALID=1`, `OWNED_MORTY_IDS_INVALID=2`, `OWNED_MORTY_IDS_LENGTH=3`, `FAILED=4`, `NONE=5` |
| `eSetActiveDeckError` | `UNKOWN=0`, `DECK_ID_INVALID=1`, `FAILED=2`, `NONE=3` |

`UNKOWN` is the native spelling. There is no deck-specific trade-lock error.
Both response callbacks (`0x17a7e60..0x17a7ff8` and
`0x17a86f8..0x17a8990`) use `NetworkDefs.ParseHTTPResponse`
(`0x1b572a4..0x1b57690`). Matching generic metadata identifies
`eEditDeckError, PlayerEditDeckResponse` and
`eSetActiveDeckError, PlayerSetActiveDeckResponse` respectively.

The shared parser first calls `ParseHTTPError<Int32Enum>`
(`0x1b569d8..0x1b56de0`). A failure body is decoded as dictionary `error`,
then string `code`, then validated by `Enum.IsDefined` and parsed. A compatible
generic rejection uses a non-success HTTP status and:

```json
{"error":{"code":"FAILED"}}
```

An HTTP success carrying this error body is not a rejection. A flat error
string is not this recovered format. This supports the new reservation
guard's envelope; it does not require changing unrelated existing endpoint
failure paths in this scoped repair. Their older flat forms remain a separate
compatibility gap. The original service's precise status mappings are unknown.

On `NONE`, `ParseHTTPResponse` deserializes the corresponding success class.
Both classes declare integer `active_deck_id` at `+0x10` and
`Dictionary<string, object>[] decks` at `+0x18`. Both callbacks call
`MPPlayerData.SetDecks(response.decks)`, assign `activeDeckIndex` from
`response.active_deck_id`, and emit the Morties-changed event. Preserve these
existing success fields and array shapes.

`SetDecks` (`0x1590e58..0x15910cc`) returns immediately for a null array;
otherwise it clears cached deck lists, then reads each dictionary's `deck_id`
and `owned_morty_ids` into that deck. This distinction matters: omission of
`decks` can leave stale cached decks, rather than necessarily failing parsing;
omission of `active_deck_id` defaults to integer zero and is still assigned.
An empty success body is therefore not an authoritative deck-update response.

## Replacement-server invariants and explicit policy boundary

The [listing selector](trade-listing-protection-contract.md) excludes active
party instances and both locks at creation. The addition method independently
excludes reserved instances. These support preserving the reservation when
editing decks. The replacement server also rejects activation of a saved deck
containing a reserved Morty to close the stale saved-deck transition described
above. That activation rejection is an integrity policy, not a recovered
original-service validation rule.

Use the established effective reservation predicate for submitted/activated
instance IDs: the existing stored flag conversion **or** a durable request
reference **or** a durable offer reference. Native party addition reads only
the local byte; it does not derive that byte by scanning trade caches. The
[lock contract](trade-lock-lifecycle-contract.md) proves that player-details
`is_trading_locked` independently overwrites the byte, while successful
creation sets it locally. Treating a durable reference as reserved when its
stored flag is false is replacement-server compatibility/integrity policy.
Removing the last reference removes only that derived contribution; stored
true remains true. This repair must not rewrite either stored flag.

Manual/favorite `is_locked` alone is not the server's reservation predicate.
Retain ordinary deck edits and activation for those records. The UI's broader
button gating above must not become a blanket server prohibition on retaining,
reordering, removing, or activating favorites.

At acceptance, recheck both participants' **current active party** using exact
owned instance IDs before transferring either Morty. A listing that was valid
at creation may now reference an active party member because of a stale client,
legacy data or a competing transition. Rejection preserves the creation-time
active-party exclusion as a replacement-server transfer invariant. The native
acceptance callback does not prove the original service revalidated this or
which error it used. Existing supported generic acceptance failure is `FAILED`;
do not invent a new enum or successful failure body.

Serialize reservation checks with deck writes, activation and transfer, and
make rejected operations leave the relevant state unchanged. Those locking,
rollback and race requirements belong to the replacement server. This static
research does not establish original transaction ordering, successful native
acceptance behavior, progression thresholds, prices or cooldown formulas.
