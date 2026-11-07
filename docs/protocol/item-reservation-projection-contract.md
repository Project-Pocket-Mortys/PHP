# Morty mutation responses: boolean flags and durable reservations

Read-only investigation on 2026-11-07 of Android 2.41.0 ARM64 and the
replacement server. Successful item, healing and attack-edit responses can
supply a stored false trading flag despite a durable reservation, overwriting
the loaded client's true flag. Separately, attack-edit serialization casts the
stored string `'false'` to PHP boolean true, marking an unlocked Morty locked.
The repair scope is the three full-Morty response serializers used by
`/session/use-item`, `/session/heal`, and
`/session/owned_morties/learn-attacks`. This is static evidence of response
consumption, not a device reproduction or an original-service capture.

## Evidence and reproduction

Fresh ignored receipts are:

- `.research/mutation-reservation-audit-20261107`: REA version, artifact
  inspection, targeted Ghidra export/log, and metadata-bounded ARM64 export.
  Eight Ghidra entries have no `error`; nine bounded methods include the shared
  HTTP-success accessor.
- `.research/item-target-selection-audit-20261107`: the same artifacts for
  six selected UI/item methods, all without `error`. Twelve bounded methods
  include five explicitly selected party/deck helpers and that HTTP accessor.

Both receipts record REA 6.8.0. Artifact inspection identifies the input bytes;
function semantics come from targeted Ghidra 12.1.4 and independent Capstone
instructions within the next-entry bounds in `methods.json`. The driver uses
`-noanalysis`, not a broad analysis index. ELF SHA-256 is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`;
IL2CPP metadata version is 31. Addresses below are native RVAs; Ghidra displays
image base `0x100000`. Managed signatures and offsets come from the matching
`.research/dumper/{dump.cs,script.json}`. Exception paths that extend into
adjacent bodies are excluded from conclusions.

To reproduce into a fresh output directory, use default WSL from the repository
and the existing `tools/research/rea.sh`, `ghidra-targeted.sh`, and
`trade-cancellation-bounded.py` helpers. Record `rea.sh --version` and
`rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json`
as `rea-version.txt` and `artifact.json`. The mutation Ghidra selection is:

```text
NetworkPlayerAPI.*(HealActiveMortyDeck|EditMortyAttacks|<UseItem>b__52_0).*|MPPartyState\$\$NetUserUseItemsHandler|MPOpponentData\$\$SetMortiesFromDicts|MPOpponentMortyData\$\$SetFromDict
```

The selection Ghidra regex is:

```text
MPPartyUI\$\$(SetUpMortyScrollMenu|MortyCellSelectedHandler|RequestUseItem)|MPPartyState\$\$(UIItemHandler|CreateUI)|MPItemDefs\$\$CanItemBeApplyedToMorty
```

Export each receipt's bounded instructions using the explicit Windows Python:

```powershell
& 'C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe' -X utf8 -B tools/research/trade-cancellation-bounded.py <receipt-directory>
```

For the selection receipt, supply this optional supplemental regex as the next
argument:

```text
MPPlayerData\$\$(GetPartyMortyData|GetActiveDeckCount|GetActiveDeckIDs)|MPPartyUI\$\$SetUp|MPPlayerData.*<GetPartyMortyData>b__0
```

## An explicit response flag overwrites the loaded flag

The [use-item contract](use-item-contract.md) identifies callback
`NetworkPlayerAPI.<UseItem>b__52_0` (`0x17a6a20`), the response schema, and the
party event. The fresh bounded pass confirms the following merge chain:

| Method | Bounded evidence |
| --- | --- |
| `MPPartyState.NetUserUseItemsHandler`, `0x15c9aa0` | With the state active, not transitioning, and a nonnull response, `0x15c9b5c` loads response `owned_morties` at `+0x28`; `0x15c9b6c` calls `SetMortiesFromDicts(...,false,false)`. This merge precedes the success-enum check. |
| `<HealActiveMortyDeck>b__0`, `0x17a9508` | On `NONE=2`, `0x17a95d8` loads response `owned_morties` at `+0x18`; `0x17a95dc` calls `SetMortiesFromDicts(...,false,false)`. |
| `<EditMortyAttacks>b__0`, `0x17a7ff8` | On `NONE=4` and a nonnull response, `0x17a80f0` loads response `owned_morties` at `+0x18`; `0x17a8100` calls `SetMortiesFromDicts(...,false,true)`. Here `clearAttacks=true` clears attacks; it does not exclude flag updates. |
| `MPOpponentData.SetMortiesFromDicts`, `0x158c668` | Resolves each dictionary's `owned_morty_id`. For an existing object, `0x158c878` calls its `SetFromDict`; a newly constructed object uses `0x158c8b0`. |
| `MPOpponentMortyData.SetFromDict`, `0x158cb1c` | Recognizes `is_trading_locked`, converts the present value with `System.Convert.ToBoolean` at `0x158d4ac`, and writes the byte at `+0x6e` at `0x158d4b4`. Explicit false clears it. Absent keys retain the existing value. |

The separate manual/favorite lock is `+0x6d`. The
[reservation lifecycle contract](trade-lock-lifecycle-contract.md) establishes
that successful request and offer creation set `+0x6e` locally, and that
player-details must preserve durable reservations during later merges.

In the pre-repair server, `session/player-details/index.php` uses
`trade_reference_projection('m.owned_morty_id')` and combines its result with
the converted stored flag. In contrast, `lib/healing_items.php`'s
`item_updated_morty` serializes the stored `is_trading_locked` field only;
the heal and attack-edit serializers likewise omit the reference projection.
`session/use-item/index.php` calls this serializer after applying an applicable
item effect, includes that record in `owned_morties`, and changes no durable
trade reference. Thus stored false plus an extant request or offer reference
produces contradictory player-details and mutation responses. The merge chain
above establishes the resulting client write; response ordering and an actual
selector rebuild have not been observed on a device in this investigation.

## Attack edits must parse stored flag strings

The pre-repair `learn-attacks` serializer uses `(bool)$row[...]` for
`is_locked`, `is_trading_locked`, `is_poisoned`, and `is_paralysed`. In PHP,
`(bool)'false'` is true because it is a nonempty string other than `'0'`.
Thus an ordinary attack edit can return `is_locked:true` for a stored
`'false'`, independently of trade reservations or unusual active-party state.
The same error applies to each of those four fields when its stored value is
the string `'false'`; integer status storage does not normally trigger it.

The client applies all four keys through `SetFromDict`, using boolean
conversion and explicit byte writes. The fresh bounded body establishes:

| Key | Native field offset | Write RVA |
| --- | --- | --- |
| `is_poisoned` | `+0x50` | `0x158cdf4` |
| `is_paralysed` | `+0x51` | `0x158d350` |
| `is_locked` | `+0x6d` | `0x158d394` |
| `is_trading_locked` | `+0x6e` | `0x158d4b4` |

Normalize these four returned fields using player-details' existing truth
set: trim, lowercase, then compare strictly against
`['1', 'true', 'yes', 'y', 'on']`. Item, heal and attack-edit responses now use
this same interpretation. Stored `'false'` and `'0'` serialize as JSON false;
stored `'true'` and `'1'` serialize as JSON true. The existing `'y'` spelling,
including uppercase `'Y'`, also means true; plain `FILTER_VALIDATE_BOOLEAN`
would not preserve that convention. Combine only the trading flag with
durable references. This changes response interpretation, not stored values,
manual-lock eligibility, status effects or attack selection rules.

## Native target-selection boundary

The normal party item picker contains active-party members, rather than the
entire owned inventory. `MPPartyUI.SetUpMortyScrollMenu`
(`0x15cbbd8..0x15cbef8`) calls `GetActiveDeckCount` at `0x15cbc98` and obtains
party entries through virtual slot 5 at `0x15cbd74` and `0x15cbe00`.
`MPPlayerData.GetPartyMortyData` (`0x1591340`) uses predicate
`0x165d248..0x165d2e4`; that predicate reads `decks` at `+0xd0` and
`activeDeckIndex` at `+0xd8`, selects the requested slot, and compares its ID
with the owned Morty's `netId` at `+0x18`. `GetActiveDeckCount`
(`0x1591540..0x1591548`) also forwards the active-deck index.

Within that party, the inspected selection and item-eligibility bodies contain
no trading-lock-byte check. `MortyCellSelectedHandler` (`0x15ccb40`) calls
`CanItemBeApplyedToMorty` at `0x15cccc8`; `MPItemDefs.CanItemBeApplyedToMorty`
(`0x176a44c..0x176a6ec`) checks effect-specific HP, fainted, status and AP
conditions. Its HP branch accepts living Morties with HP below maximum.
The world branch of `MPPartyState.UIItemHandler` (`0x15cb498`) forwards the
selected instance ID and item ID to `NetworkPlayerAPI.UseItem` at
`0x15cb748`, without an additional reservation check.

Consequently a reserved Morty already in a loaded active party because of
legacy or inconsistent state can be an item target. A normal reserved spare is
not established as reachable through this picker: current listing creation
excludes active-party members, and current party-transition guards reject
reserved members. Do not claim a routine create-trade-then-use-Serum native UI
reproduction from these facts. The server endpoint itself accepts any unique
owned instance with an applicable supported effect; it has no active-deck or
reservation eligibility requirement. This projection repair does not introduce
one or assert the original service's policy on item use for reserved Morties.

## Narrow projection policy and transaction boundary

The repair uses the existing `trade_reference_projection` policy for every
returned Morty in the three mutation responses: its correctly converted
stored flag, OR any
`trades.morty_trade_id` reference, OR any `trade_offers.morty_offer_id`
reference. References remain global by instance ID, including orphan offers
and stale declared owners. The item target's separate projection query scopes
the physical source row by its `id`, logical owned ID and player ID, and a
missing match throws before commit. Heal and attack edits select the
projection alongside their existing owner-scoped Morty queries. No stored
flag repair, cancellation, lock eligibility rule or item calculation is
implied.

`/session/use-item` opens a transaction, locks the authenticated user, performs
ordinary battle/shared-membership reads, then locks the globally unique owned
instance and item stock. The serializer runs after item effects and before
commit. A plain projection `SELECT` there adds no reference-row lock order.
Its view follows the connection's isolation policy: under repeatable read the
earlier ordinary reads may already have established the transaction snapshot.
Do not describe this projection as an unconditional latest-current locking
read. Same-owner trade writers serialize on the user lock; a stale-owner or
orphan reference cancelled through another owner can race with this response.
Changing that concurrency policy would require separate analysis. The original
service's database isolation and ordering are unknown. Heal currently commits
the effect before loading its response Morties, whereas attack edits load the
response inside their transaction. Preserve these existing boundaries; a
response projection alone does not establish a new cross-endpoint ordering
guarantee.

## Other response paths remain separate

Heal targets the active party, so reservation-conflict reachability through
the normal healing UI has the same legacy-state qualification described for
items. The attack-edit `'false'`-string bug requires no reserved active-party
state. None of these serialization changes establishes new item eligibility,
healing effects, attack PP maxima, economy behavior or stat formulas.

The lock endpoint returns `active_deck_id` and `decks`; deck edit/activation
return decks without Morty dictionaries. They do not overwrite this byte through
an owned-Morty response. Absorb returns `modified` containing only the target
ID and evolution points, preserving omitted flags; it guards durable target
and donor references before mutation. It currently creates no evolved Morty.
No evolution formula or additional evolution response is inferred here.
