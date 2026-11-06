# Absorption donor species and variants

The absorption endpoint previously consumed any unlocked owned donor, including
different species and incompatible shiny/pulsing variants. It now checks each
resolved donor against the target before any attack, Morty, deck or point write.
An incompatible donor rejects the entire batch with HTTP 409 and
`error.code: ABSORB_INVALID_MORTY`, a member of the native absorption error enum.
The exact original server status and error assignment are unknown.

[Native evidence](absorb-eligibility-contract.md) requires identical species IDs
and this directional variant matrix:

| Target | Compatible donors |
| --- | --- |
| Normal | Normal, Shiny, Pulsing |
| Shiny | Normal, Shiny |
| Pulsing | Normal, Pulsing |

Species comparison is exact and case sensitive. Missing/empty species and
unknown variant strings reject conservatively. Legacy NULL variants continue
to mean Normal, matching the existing player-details response. No stored row
is normalized or migrated. Ordinary locked targets can still receive points;
all existing donor protection, ownership, deduplication and transaction guards
remain in effect. Missing/foreign/self donor IDs retain existing filtering.

The accepted path still adds one point per actual consumed donor and returns
the existing `removed`, `modified` and complete `decks` response. No species
catalog, evolution requirement, stat formula or new `created` object is inferred
by this change. The [point-only active-party guard](absorb-active-party-implementation.md) now
preserves a living active party; full evolution remains separate work. README-completed evolution and attribution remain the baseline.

## Reproduction

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_morty_absorb_eligibility.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_morty_absorb_protection.py -v
& $researchPython -X utf8 tools/research/validate.py
```

Fixtures use fresh UUID accounts and clean up only their own rows. They compare
database state after rejected batches, including points, attacks and decks.
The initial nine-case run took 122.672 seconds: five unsafe batches failed both
the rejection and unchanged-state checks, while four compatible/null/locked-target
cases passed. After repair, all 14 final eligibility cases passed in 136.313
seconds. They cover all nine directed canonical variant pairs, SQL NULL defaults,
species mismatch/case, missing/blank species and malformed target/donor variants.
The 12 existing absorption-protection cases and three world-action battle-guard
cases also passed in 122.382 seconds, for 29 distinct regression cases. Coverage
retains duplicate/retry behavior, concurrent consumption, Lock/Absorb ordering,
foreign/ambiguous IDs, malformed decks, protected donors and late-write rollback.
PHP 8.3 lint passed for all 37 changed/new PHP files including prerequisites;
protocol/source validation, evidence reproduction and shell syntax checks passed.

[Android acceptance](android-absorb-eligibility.md) uses guarded synthetic
storage records to verify the compatible partial-absorption path separately.
Android 2.41.0 kept the locked donor disabled without sending a request. A
compatible Normal-to-Normal blend returned HTTP 200, consumed only the selected
fresh donor and showed the synthetic target at 1/3 EVO. Cleanup matched the
reconstructed point/deletion effects and removed only the surviving fresh
clones, restoring both original account snapshots. The full variant matrix
is established by static/HTTP evidence; it was not exercised through Android.
After a fresh app restart, multiplayer WORLD loaded normally. The absorption
fixture guard, independent two-account gameplay guard and complete save/friend
guard all passed, including an independent integrator check after reload.
Only documented connection fields are excluded from save comparisons.

Based on main `9ff1a11` with pending prerequisite PR #36 at `757749f` and its
dependency history. No database migration or deployment is included.
