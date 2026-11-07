# Absorption preserves a living active party

The absorption endpoint previously removed donors from every saved deck without
checking the remaining active party. A request could consume its last living
member, or the whole party, while only adding evolution points to a target in
storage. The native UI blocks partial absorption in that situation; see the
[bounded native review](absorb-active-party-contract.md).

The replacement endpoint must establish one unambiguous active deck and at least
one surviving, uniquely owned Morty with positive integer HP before deleting
donors, attacks or deck memberships, or changing points. Deck 0 is valid. A
missing active deck, an ambiguous instance ID, or foreign/missing/fainted members
cannot establish a living party. An ordinary locked target may remain a valid
survivor. Inactive-deck donors remain usable when the active party is safe.

This safeguard applies to the existing point-only path regardless of the point
counter. The native threshold branch can submit without its partial-absorption
party check, but this PHP handler does not return a newly evolved Morty. Treating
the counter as a replacement for a consumed party would invent evolution
behavior. This unconditional protection is replacement-server policy, not a
claim about the original server. Full evolution, stats and the README-completed
feature's broader compatibility remain separate.

Rejected unsafe requests return HTTP 409 with `error.code: FAILED` and leave
the batch unchanged. Successful responses retain `removed`, `modified` and
complete `decks`; point gain, donor filtering/deduplication and lock/species/
variant protection retain their existing behavior. No migration is required.

The authenticated user row is locked first, followed by owner deck rows and a
sorted global set of requested and active-party instance IDs. This establishes
one proposed party under the same user lock as donor consumption. Two requests
that each remove a different living donor cannot both pass using the old party.
Duplicate inactive deck IDs still update each actual row independently.

Deck validation now precedes target/donor resolution. An invalid active deck
or malformed saved membership therefore takes precedence over missing-target
or empty-donor errors when those defects occur together: validation returns
409 FAILED before resolving the target/donors. Valid-party requests retain the
existing missing-target and no-valid-donor envelopes. No invalid save is repaired
or normalized as a side effect of rejection.

## Validation

Run only additive fixture suites, serially, against the isolated research stack:

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_morty_absorb_active_party.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_morty_absorb_protection.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_morty_absorb_eligibility.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_battle_world_guards.py -v
& $researchPython -X utf8 tools/research/validate.py
```

The unchanged endpoint reproduced destructive HTTP 200 responses and actual
donor/deck changes in the initial regression run. Two concurrent requests
consuming different living donors both succeeded, leaving only a fainted member.
After the fix, all 49 cases passed serially: 20 active-party cases (187.904
seconds), 12 protection cases (117.702 seconds), 14 eligibility cases (139.385
seconds), and 3 battle/world guards (8.664 seconds). Rejection assertions compare
the complete fixture state; success assertions compare exact point, deletion,
attack and deck effects. The concurrent case now commits one consumption and
rejects the second.

PHP 8.3 lint passed for the changed helper. Protocol/source fingerprints, Python
syntax and whitespace checks passed. The narrow research wrapper passed shell
syntax validation and reviewed 18 native functions plus the fainted accessor.
Both original-account guards passed, covering saves, friends, battles,
invitations, HP/AP/items/decks/progression and membership. No retained account,
AVD data, or original archive was reset.

Native evidence, backend regression results and preservation checks are recorded
separately. This repair does not claim a new Android capture of an unsafe request:
the ordinary client prevents that submission.

Based on current main `9ff1a11` with explicit pending prerequisite PR #47 at
`04a0c0b`. The tested PHP repair is commit `2497749`. Full evolution, battle
resolution and deployment are outside this repair.
