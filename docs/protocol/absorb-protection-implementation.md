# Absorption lock protection and durable donor accounting

The existing absorption endpoint could consume a locked Morty. Repeating a
donor ID also granted two points while deleting one record. The repair protects
consumed donors and accounts for each actual removal once, while retaining the
existing point-gain path and `removed`/`modified`/`decks` response. README's
completed evolution feature remains the project baseline.

[Native evidence](absorb-protection-contract.md) distinguishes the two roles:
ordinary locked targets can receive points, while locked donor cells are
disabled. Trade-locked targets are excluded by the client. Consumed trade-locked
or fight-pit-assigned donors also reject under an explicit conservative server
assignment-protection policy; those two donor checks were not present in the
inspected client predicate.

## Transaction and compatibility

The endpoint keeps its existing headers and request fields. The shared helper
locks the session user first, retains the existing unresolved-battle guard,
then locks global target/donor ID matches in deterministic order. An ambiguous
logical ID rejects before deleting attacks, which have no separate owner column.
Morty and point writes use the exact numeric row ID and owner, and deck writes
use the numeric deck row ID and owner rather than a possibly duplicated logical
deck ID.

Repeated donor IDs are deduplicated in request order. Missing, foreign and
self-target donor IDs retain the legacy filtering behavior; a foreign record
is never deleted. A protected or ambiguous record rejects the entire operation
without partially consuming other donors. Ordinary locked recipients remain
valid, while a trade-locked recipient rejects. Legacy boolean strings such as
`"false"` remain false; malformed protection flags reject conservatively.

Each unique accepted donor grants the existing one point. Legacy null points
start at zero. Negative/malformed points or PHP integer overflow reject before
mutation. This is defensive counter validation, not a recovered evolution
formula or level/species transition. No stats, XP, items or new Morty records
are generated.

Decks are read under locks. Valid JSON arrays, legacy escaped arrays and empty
arrays retain their memberships after removing consumed IDs. Invalid objects,
nulls, non-string IDs or malformed JSON reject instead of being overwritten
with an empty party. Every actual owner deck is returned in deterministic
`deck_id,id` order. Donor attacks/removal, deck cleanup and the point update
commit together; a failure at the final persistence step rolls them all back.

Existing legacy failures retain HTTP200 with `error.code` values
`INVALID_REQUEST`, `NOT_AUTHENTICATED`, `NOT_FOUND` or `NO_VALID_MORTYS`.
Omitted/null donor lists retain the legacy empty-list behavior. Malformed nested
lists/identifiers cannot produce PHP warnings in JSON. New protection or
inconsistent-state rejections use HTTP409 / `FAILED`; unexpected failures
retain HTTP500 / `SERVER_ERROR`. Original-server error/status parity remains
unknown.

The Lock and Absorb paths serialize on the user lock. If Lock wins, consumption
rejects; if consumption wins, a later Lock cannot find the removed donor.
Concurrent absorption or a repeated request cannot award the same removed
record again. This is durable donor accounting, not a general request nonce.

## Checks and reproduction

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_morty_absorb_protection.py -v
& $researchPython -X utf8 tools/research/validate.py
wsl -- bash tools/research/ghidra-absorb-protection.sh
```

The new UUID-only regressions demonstrated both locked-donor consumption and
duplicate point inflation before the repair. They cover protected mixed
batches, duplicate/retry behavior, global ambiguity, owner isolation, locked
recipients, trade protection, flags/decks/points, legacy failures, active battle
guards, Lock/Absorb concurrency and a connection-local late persistence fault.
No existing account is reseeded. [Android checks](android-absorb-protection.md)
use fresh synthetic storage records and restore original accounts exactly.

The 12 new cases passed across the initial ten-case run (98.402 seconds) and
two added cases (19.356 seconds). The affected input case also passed after
retaining omitted/null donor compatibility. All 23 existing lock/release/world
guard cases passed in 196.231 seconds, for 35 distinct regression cases. PHP 8.3
lint passed for all 29 changed/new PHP files including prerequisites; protocol
validation and the complete REA/Ghidra/Capstone reproduction passed. The reviewed
integration runner includes the new suite and excludes global reseeding tests.

Android 2.41.0 verified the storage partial-absorption path with synthetic
same-species records: the padlocked donor remained disabled with no request
or state change, while the unlocked donor produced one successful native
request, one point and its actual removal. The target displayed 1/3 EVO and
the locked donor survived. Full evolution was not exercised. Guarded cleanup
restored the original two-account state; see the Android record for exact
screens, requests and synthetic-stat provenance.

## Scope and remaining evidence gaps

The follow-up [donor eligibility repair](absorb-eligibility-implementation.md)
now enforces the recovered same-species/variant checks. The scope below records
the original protection milestone; conditional party checks and full evolution
remain separate.

This branch starts from main `9ff1a11` with pending prerequisite PR #33 at
`b0bac01`, including its dependency history. No new database migration is
required. Existing completed README claims and attribution are preserved.

Native research additionally recovered same-species/variant eligibility,
threshold-dependent active-party checks, and the optional `created` response
used for a full evolution. Those are documented research obligations, outside
this protection repair. The current point path does not implement a full
species/stat transformation, and this milestone does not claim one was tested.
It also does not add an unconditional donor-deck ban: native code permits deck
donors and treats the threshold cases differently. Remaining server validation
and complete evolution handling require a separate contract-backed change.

Release's existing protections remain; this work does not establish universal
lock enforcement in trade or every destructive interface. No public deployment
or real purchase is included.
