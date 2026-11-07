# Morty mutation response flag repair

`/session/use-item`, `/session/heal`, and
`/session/owned_morties/learn-attacks` now retain durable trade reservations
in their full owned-Morty response dictionaries. A stored false flag plus an
existing request or offer previously produced `is_trading_locked:false`, which
could overwrite the loaded client's true reservation. Learn-attacks also
converted the stored string `'false'` through PHP `(bool)`, incorrectly returning
true for ordinary unlocked Morties and potentially for other string flags.

The [native merge contract](item-reservation-projection-contract.md) documents
fresh REA 6.8.0 bounded callback, dictionary-merge and selector evidence for
Android 2.41.0. No new Android interaction or original-service capture was made.
World item use and healing operate on the party; existing trade selectors
exclude active-party Morties. These backend regressions therefore do not claim
an ordinary reserved spare can be selected for world item use. The ordinary
learn-attacks string-false corruption is a separate confirmed serializer defect.

## Projection and preserved behavior

All four response flags use the existing player-details legacy truth set after
trimming and lowercasing: `1`, `true`, `yes`, `y`, and `on`. Other values convert
to false. JSON responses contain booleans. The effective trading flag is:

```text
canonical stored is_trading_locked
OR EXISTS trades.morty_trade_id = owned_morty_id
OR EXISTS trade_offers.morty_offer_id = owned_morty_id
```

References count globally by owned-instance ID under the database's existing
collation. Orphan offers, stale declared owners and collating aliases retain
the reservation. Removing one reference retains any remaining contribution;
removing the last releases the derived contribution, while stored true remains
true. The existing `trade_reference_projection` supplies the SQL predicate.
The item helper also binds its physical row ID, instance ID and owner and rejects
a mismatched row before returning a dictionary.

This is response projection only. No stored flags, eligibility, inventory,
HP/AP/status effects, manual locks, prices or attack-learning rules change.
The existing learn-attacks PP value of 8 remains a placeholder; this work does
not establish an authoritative AP-learning formula. Existing item failures
retain their status/error behavior and do not consume stock or modify HP.

Item and learn-attacks reads use their existing transaction view. Healing
projects after its existing commit. No new trade-reference locks or migration
were added. These views do not guarantee the latest wall-clock reservation if
another operation changes references concurrently. Immediate cancelling-actor
cache refresh and stored true-flag reconciliation remain separate.

## Validation

The two item baseline tests
`test_request_reservation_survives_item_response` and
`test_orphan_offer_reservation_survives_item_response` failed before the repair
because false was returned instead of true.
`test_learn_false_strings_are_json_false` and
`test_heal_projects_legacy_active_party_trade_reference` also failed before
their source repair.

All 76 tests passed in a serial run of the eight modules below: item projection
(9), heal/learn flags (5), existing item use (10), full restore (12), status cures
(9), full recovery (13), durable trade references (12), and party writer guards
(6). This includes the final `y`/`Y` subcases. Fixtures use additive disposable
UUIDs in the isolated Compose stack, never reseed accounts, and clean up their
own rows. The status-cure migration check uses a separate schema copy.
Item coverage includes all thirteen supported effects with complete fixture
state comparisons, legacy flags, stale-owner/collated references, actual
cancellations, identity mismatches, unauthorized requests, no-effect failures
and stock rollback. PHP lint and the research inventory validator pass.
Read-only checks preserve retained startup saves, original research and
invitation accounts, accepted trading swaps and terminal cancellation state.
No production database or devices were changed.

From the repository root with the isolated Compose stack running, reproduce
the eight modules serially using the explicit Windows interpreter:

```powershell
$modules = @(
    'test_item_reservation_projection',
    'test_mutation_morty_flags',
    'test_use_item',
    'test_full_restore_items',
    'test_status_cure_items',
    'test_full_recover',
    'test_trade_references',
    'test_party_writer_guards'
)
Push-Location (Join-Path $PWD 'tests/protocol')
try {
    foreach ($module in $modules) {
        & 'C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe' -B -m unittest $module -v
        if ($LASTEXITCODE -ne 0) { throw "Protocol regression failed: $module" }
    }
}
finally {
    Pop-Location
}
```
