# Pure Curum: full HP and ailment recovery

`ItemFullRecover` (English name **Pure Curum**) now restores maximum HP and
clears poison and paralysis together on a living owned Morty. It works in
world party use and as an active/bench battle item. AP, attack slots, stats,
XP, locks and other Morties are preserved. It does not revive fainted targets.
The asset and animation names contain “Revive”; those names are not effect rules.

[Native eligibility and MP metadata](full-recover-contract.md) establish that
a living target is eligible when HP is below maximum or either ailment is
present. Full HP with an ailment is valid; full HP without an ailment is a
no-op even if AP is depleted. No percentage rounding or single-player formula
is required. Cure result text ignores the numeric magnitude; `effect_value:0`
retains the convention already used by the individual cures.

## Implementation and transactions

The existing shared item planner adds one explicit Pure Curum branch. It plans
HP at the stored maximum, both status flags false and no attack updates. The
world and battle allowlists include the existing metadata ID. Existing handlers
apply the combined plan and charge exactly one owned-item unit atomically.
No schema, endpoint, request field or response envelope is added.

World use retains `PlayerUseItemResponse` with `is_success:true`, the actual
updated owned-Morty snapshot and absolute remaining stock (including zero).
It remains unavailable while an unresolved battle is active. A rejected or
ineffective use returns the existing failure envelope without consumption.

Battle use retains the recovered ITEM target semantics: `owned_morty_id` is
the selected member of the immutable initial party, active or bench; `move_id`
is `ItemFullRecover`. Its ITEM action reports `success:true`, value0 and the
target's full HP with both flags explicitly false. Unchanged AP is omitted
from that partial action snapshot. A later, separate AI action reports damage
to the current active member. Healing the bench does not change active identity.

The existing replacement battle policy still applies: an effective ITEM uses
an action and the current placeholder AI counterattacks the active member for
1..3 damage. Pure Curum does not alter initiative, damage formulas or cooldowns.
Pending forced replacement, foreign/outside-party targets, ambiguous records,
invalid HP, missing/duplicate/invalid stock and expired selections retain their
existing guards. Any persistence/event insertion failure rolls back the whole
effect, charge, AI action and battle state.

The item preserves the existing retry boundary: a healthy target is a no-op;
another effective use can be another turn. The native request carries no turn
nonce, so request-body equality is not an idempotency key.

## Reproduction and scope

This branch starts from main `9ff1a11` with explicit pending prerequisite
PR #32 at `1f810f7`, including its dependency history. Apply the prerequisite
migrations through 004 for the integrated backend. This feature adds no new
migration. README-completed features and project attribution remain intact.

Use the installed interpreter directly to avoid Windows Store execution aliases:

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_full_recover.py -v
& $researchPython -X utf8 tools/research/validate.py
wsl -- bash tools/research/ghidra-full-recover.sh
```

The additive suite uses fresh UUID accounts and retains the existing accounts.
It covers combined and single deficits, living/fainted eligibility, AP
preservation, ownership/stock/state guards, concurrent last stock and rollback.
Native reproduction is recorded in [Android acceptance](android-full-recover.md).

The initial unsupported-item baseline failed the new suite. After the change,
all 13 new cases passed in 106.361 seconds. PHP 8.3 lint passed for all 28
changed/new PHP files including prerequisites; protocol evidence validation
and bounded research script syntax checks passed.

Percentage revival/AP items, stat/general/damage items, capture, original combat
and reward formulas, and complete interrupted-battle replay remain separate.
No public deployment or real purchase is included.
