# Android 2.41.0 trade listing eligibility and protection

Recovered 2026-11-06 from bounded ARM64 client methods. This establishes
client selection behavior and recognized creation errors, not the original
service's database, transaction ordering, HTTP status policy, or economics.
See [native trade creation](native-trade-creation-contract.md),
[trading locks](trade-lock-lifecycle-contract.md), and
[offer response](native-trade-response-contract.md).

## Reproduce and evidence boundary

From PowerShell, using the default WSL distribution:

```powershell
wsl.exe -- bash tools/research/ghidra-trade-listing-protection.sh
```

The wrapper requires REA 6.8.0, inspects the artifact, runs targeted Ghidra
12.1.4 in a disposable project, and exports instructions bounded by the next
IL2CPP metadata entry. It refuses an existing output directory. The bounded
export uses the explicit Windows Python executable
`C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe`; its WSL
path can be overridden by `POCKET_WINDOWS_PYTHON`.

Fresh ignored receipts are
`.research/trade-listing-protection-20261106T233431Z` (18 bounded methods)
and `.research/trade-listing-protection-20261106T233540Z` (19 bounded methods).
The latter uses the final wrapper's narrower method selection and includes
restriction reset and creation-result handlers. Each directory contains
`rea-version.txt`, `artifact.json`, `ghidra.json`, `ghidra.log`, `methods.json`,
and `arm64.txt`. The variant accessor and shared HTTP success accessor are
bounded instruction supplements: the shared Ghidra script skips accessors.
The HTTP supplement does not imply that inventory predicates perform HTTP.

ELF SHA-256 is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`;
metadata version is 31. Addresses below are native RVAs; Ghidra adds image
base `0x100000`. Managed names, field offsets, enums, and method boundaries
come from the matching `dump.cs` and `script.json`. Only instructions inside
the recorded bounds establish behavior. No device, database, or endpoint
mutation was required. Earlier creation receipts ending `210059Z`,
`210204Z`, and `210228Z` remain supporting evidence for request constructors,
callbacks, and slot UI.

## Owned instance protections

`MPTradeMortySelectState.GetTradeableMortys`
(`0x15f98d0..0x15f9ae0`) obtains the player's owned inventory and active
deck. Its `FindAll` predicate (`0x15fc240..0x15fc270`) accepts a record only
when both `isLocked` (`+0x6d`) and `isTradeLocked` (`+0x6e`) are false.
It then removes every object returned by `GetActiveDeck` from that filtered
list (`0x15f9a94..0x15f9ac4`). Both new own-request selection and new offer
selection use this owned-Morty list.

`MPPlayerData.GetActiveDeck` (`0x1591a1c`) forwards the current
`activeDeckIndex` (`+0xd8`) to `GetDeckMortyDatas`
(`0x1591a24..0x1591c58`). For each string in that deck, the latter resolves
the first owned record using `FirstOrDefault`. Its predicate
(`0x165d450..0x165d4ec`) compares the owned record's `netId` (`+0x18`)
with the deck slot string using `System.String.op_Equality` at
`0x165d4e4`. Thus protection follows owned instance identity, not species
identity. Another owned Morty of the same species remains eligible if it
passes the other checks. The path does not exclude membership solely in an
inactive saved deck.

No integer conversion, trimming, case folding, or species aliasing is present
in that instance comparison. A replacement server should compare the stored
instance ID strings, including when storage or database collation would
otherwise equate aliases. The native data model declares `decks`,
`active_deck_id`, `deck_id`, and `owned_morty_ids`; accepting escaped legacy
JSON in SQL storage is repository compatibility behavior, not a recovered
native wire format.

This bounded filter contains no check of trainer level, Morty level, HP,
ailments, attack count, or minimum owned-inventory count. It does not establish
an additional eligibility threshold for any of those fields.

## Requested species and variant

`MPTradeOfferCreateState.UISelectHandler`
(`0x16004f4..0x16006a4`) compares `trade.morty_request` with the literal
`any`. When equal, it skips setting both species and variant restrictions.
For a specific requested species it installs that species and
`trade.request_variant` on the selection state. Selection-state
`Deactivate` (`0x15fb108..0x15fb124`) clears the species restriction, so
ordinary navigation does not retain a previous specific-species restriction.

Owned-list `SetUp` (`0x15fb1ec`) passes the restrictions to
`MPTradeInfo.SetLimitedData` (`0x15e495c`). `SetCell` (`0x15fca18`)
only invokes the two restriction predicates when the species restriction is
nonnull. It removes records for which:

| Predicate | Rejected condition |
| --- | --- |
| `0x15fe0c4..0x15fe0f0` | `String.Compare(requestedSpecies, owned.id) != 0` |
| `0x15fe0f0..0x15fe120` | `owned.variant != requestedVariant` |

The species is `NodeData.id` (`+0x10`), exposed as `morty_id`, while the
instance ID above is exposed as `owned_morty_id`. The species comparison is
the client `String.Compare` call; byte-exact comparison of canonical server
species identifiers is a server validation policy, not proof of all .NET
culture-comparison edge cases.

For a specific species, the variant matrix is equality:

| Requested / offered | Normal | Shiny | Pulsing |
| --- | --- | --- | --- |
| Normal | allow | reject | reject |
| Shiny | reject | allow | reject |
| Pulsing | reject | reject | allow |

`MortyVariant` is `Normal=0`, `Shiny=1`, `Pulsing=2`. This is not the
directed compatibility rule used by absorption. For `any`, this compatibility
filter accepts all three variants regardless of the listing's requested
variant; the common ownership, lock, and active-deck protections still apply.
Bypassing compatibility does not establish that malformed serialized enum
names should be accepted.

The variant accessor (`0x158e478..0x158e508`) returns stored `_variant`
(`+0x68`) for ordinary owned records. The Shiny Potion override additionally
requires `isWildMorty` (`+0x58`), so it supplies no reason to reinterpret
an owned Morty's stored variant. SQL NULL serializes as `Normal` in the
existing player response; strict canonical storage validation and rejecting
malformed legacy variants are server policies. See
[owned variant storage](absorb-eligibility-contract.md).

## Creation errors and safe server checks

The native creation callbacks parse non-success HTTP bodies using the
endpoint's error enum. The supported names are:

| Endpoint | Error enum names |
| --- | --- |
| `/trading/request-morty` | `UNKNOWN=0`, `FAILED=1`, `TRADE_MORTY_LOCKED=2`, `TRADE_REQUEST_MORTY_DOES_NOT_BELONG_TO_PLAYER=3`, `NONE=4` |
| `/trading/offer-morty` | `UNKNOWN=0`, `FAILED=1`, `TRADE_NO_TRADE_EXISTS=2`, `TRADE_NO_SUCH_MORTY=3`, `TRADE_MORTY_NOT_MATCH_CRITERIA=4`, `TRADE_OFFER_MORTY_DOES_NOT_BELONG_TO_OFFERING_PLAYER=5`, `NONE=6` |

Fresh creation-result UI handlers (`0x160550c` for requests, `0x1600960`
for offers) return to the previous screen on their respective `NONE` value;
otherwise they format the enum name for a generic popup. There is no separate
offer-specific locked enum. Exact strings in `error.code` are required by the
parser; the observed names do not establish original HTTP status codes or
which particular error the service used for an active-deck rejection.

Server validation can safely enforce the authenticated owner's instance,
both locks, active-deck protection, and the species/variant compatibility
above before inserting a listing. Treating an existing request or offer
reference as a reservation even when its stored lock flag is stale follows
the repository's existing effective-lock policy. Serializing these checks
with the listing write, and rolling back every rejected attempt, are
replacement-server integrity requirements. They are not claims about original
service transactions or validation order.

These findings add no coupon price, premium charge, slot limit, level/HP
threshold, cooldown calculation, or other progression formula. Existing
creation-response bodies and successful reservation behavior remain described
in the linked creation and lock contracts. Static analysis here does not
claim a successful native create/cancel acceptance trace.
