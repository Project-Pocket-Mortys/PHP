# Full revival and AP restoration

`POST /session/use-item` now supports two more world items in addition to the
eight HP healers:

| Item | Eligibility | Result | `effect_value` |
|---|---|---|---|
| `ItemPureHalzinger` | Fainted Morty (`hp=0`), positive maximum HP | HP becomes maximum HP; attacks unchanged | `100` |
| `ItemPurePlutonicRock` | Living Morty, at least one attack below its maximum | All attacks regain full AP; HP unchanged | `100` |

Both values are percentages for the client's item result text. HP healers still
report the absolute amount restored. Exact IDs and descriptions are in
[item data](use-item-data.md); response merges and display logic are in
[the use-item contract](use-item-contract.md).

Full HP does not prevent AP restoration. Full AP, no attacks, a living revival
target or a fainted AP target fail without consuming inventory. Invalid HP/AP,
unknown attack IDs and the unlimited `AttackStruggle` sentinel also fail without
consumption. Missing, null, negative or stale **saved maximum AP** can be repaired
from known static metadata on a successful AP use. Current AP must remain valid.
Pure revival is independent of AP data and preserves it exactly.

## Correct maximum AP

The client derives maximum AP from MP `AttackInfo.pp_stat`. Its owned-attack
response parser ignores `pp_stat`. Existing saved maxima can be wrong because
learn-attacks initializes every attack to 8. Using that value would leave some
AP bars partially empty after a nominal full restore.

The new route uses [the pinned lookup](../../config/attack_max_ap.json), exported
from the inspected Android MP AttackInfo TextAsset, and synchronizes saved
`pp_stat` when restoring AP. Outburst therefore restores to 12, Lick to 18, and
Flail to 10. It repairs affected rows only as part of a successful use; a stale
maximum alone is not a reason to charge an already full-AP Morty. Existing heal
and learn-attacks handlers are unchanged. The direct native call sites and
extraction provenance are documented in [AP maxima](ap-maxima-contract.md).

```powershell
py tools/research/export_attack_max_ap.py --check
py -m unittest discover -s tests/protocol -p test_full_restore_items.py -v
py -m unittest discover -s tests/protocol -p test_use_item.py -v
py tools/research/validate.py
```

The catalog contains 690 records, including the nonpositive Struggle sentinel.
Its exporter requires the expected TextAsset SHA-256 before producing data.
The current workspace MP bundle differs from the preserved bundle but this
AttackInfo TextAsset has the same hash in both.

## Transactions and scope

The existing account/Morty/inventory locks and WORLD/active-battle guards remain.
AP restoration also locks the target's attack rows. HP/AP/maxima updates and one
item decrement commit together; the response contains the changed Morty and
item quantity, including zero. Failed or ineffective uses do not charge. There
is no new schema migration. The JSON AP catalog must accompany the PHP files.

The protocol still lacks a request identity. Concurrent last-item requests cannot
overspend stock, but repeat effective requests with stock are separate uses.
Concurrent battle creation does not yet share this locking protocol. Original
HTTP status and consumption semantics remain replacement-server policy, with
the client's recognized `FAILED` error code.

Ordinary Halzinger and Plutonic Rock have 50% descriptions, but multiplayer
rounding and minimum revived HP remain unconfirmed. Single-player truncation is
documented as precedent, not original multiplayer behavior. Those variants,
ailment cures, stat/level items, general items and battle items remain pending.

## Reproduce the Android fixture

With the primary research account in WORLD, one original Morty in its active
deck, and no existing full-restore items:

```powershell
py tools/research/full_restore_fixture.py prepare
# Reload Android, open Your Mortys, and select the extra level-6 Morty.
# Use Pure Halzinger, then Pure Plutonic Rock.
py tools/research/full_restore_fixture.py restore
# Reload Android to discard the removed fixture from its local cache.
```

The helper checks the isolated backend, preserves recovery state in ignored
`.research/emulator/full-restore-fixture.json`, adds a UUID Morty with zero HP
and zero Outburst AP, and adds one of each item. Its deliberately stale saved
maximum of 8 tests the static maximum repair. The real Morty remains healthy.
Restore checks the expected deck and stock before removing fixture records and
restoring the original deck. Changes outside the expected fixture require review
instead of an automatic overwrite. Raw captures and account identifiers remain
outside tracked source.


## Acceptance results

The new full-revive baseline failed with unsupported-item HTTP 400 before
implementation. All 12 new tests and 10 existing healing tests now pass (22 total),
including stale/static maxima, mixed AP caps, ownership, invalid data, ineffective
uses and simultaneous last-item requests. Both PHP files pass syntax checks;
export verification and protocol validation pass.

Android 2.41.0 exercised both items through Your Mortys > the extra level-6 Morty
> Use Item. Pure Halzinger changed HP from 0/20 to 20/20 without changing AP 0 or
its saved maximum 8. Pure Plutonic Rock then changed AP from 0/12 to 12/12 in
Stats, preserved HP 20 and synchronized saved maximum to 12. Each item went from
quantity 1 to 0; both HTTP responses returned 200 and percentage 100. The real
Morty was unchanged. See [sanitized runtime capture](full-restore-capture.json).

The fixture was restored and verified absent from Morties, attacks and inventory;
the original deck was restored. Its prepare/restore commands were exercised a
second time to verify repeatability. The primary client was reloaded afterward
to discard removed fixture data. Original-server behavior is not claimed.
